"""
run.py — 流A 入口：月度新增资金配置 → 输出报告到终端。

用法:
    python run.py report [--weights JSON] [--total N] [--demo]
    python run.py rebalance

参数:
    --weights JSON  当前组合各资产权重，如 '{"白酒ETF":0.08, ...}'
    --total N       当前总资产金额（默认 500,000）
    --demo          使用模拟数据演示系统（无需真实数据）
    -v, --verbose   详细输出

流A 步骤:
  1. 连接 SQLite DB
  2. 更新数据（AkShare，--demo 模式跳过）
  3. 计算所有因子
  4. 计算机会分
  5. 市场温度计（带持久化）
  6. 风险控制
  7. 组合约束
  8. 资金分配
  9. 生成并打印月报
"""
import json
import sys
import sqlite3
from datetime import date
from pathlib import Path

# 确保项目根在 path 中
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from config.settings import (
    ASSETS,
    WINDOW_PE_PERCENTILE_YEARS,
    KECHUANG_TREND_OFF_MULTIPLIER,
)
from src.store.schema import create_tables
from src.datasource.akshare_adapter import fetch_etf_price, fetch_index_valuation
from src.factors.value import pe_percentile, pb_percentile, compute_zscore
from src.factors.dividend import dividend_yield_percentile
from src.factors.momentum import momentum_120d, ma_trend_200d
from src.factors.risk import annualized_volatility
from src.scoring.engine import score_all
from src.regime.thermometer import equity_ratio, load_persistence, save_persistence
from src.risk.controller import all_effective_limits, reset_recovery_tracking
from src.constraints.portfolio import apply_constraints
from src.allocation.allocator import allocate
from src.rebalance.checker import check_rebalance
from src.reports.monthly import generate_report
from src.execution.bond_liquidity import BondAccumulator


DB_PATH = PROJECT_ROOT / "data" / "db" / "etf_data.db"


def get_db_connection() -> sqlite3.Connection:
    """获取数据库连接，自动建表。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn


def ensure_etf_seed_data(conn: sqlite3.Connection) -> None:
    """种子数据：如果 etf_info 表为空，写入配置的 ETF 元信息。"""
    existing = conn.execute("SELECT COUNT(*) FROM etf_info").fetchone()[0]
    if existing > 0:
        return

    from src.store.schema import insert_etf_info
    for name, cfg in ASSETS.items():
        insert_etf_info(
            conn,
            code=cfg["code"],
            name=name,
            asset_class=cfg["asset_class"],
            factor_group=cfg["factor_group"],
            tracking_index=cfg.get("tracking_index"),
            list_date=None,
        )
    print("[INFO] ETF 元信息已写入数据库。")


def update_data(conn: sqlite3.Connection, verbose: bool = False) -> None:
    """
    从 AkShare 拉取最新数据并入库。
    使用 INSERT OR UPDATE（幂等）。
    """
    from src.store.schema import insert_etf_price, insert_index_valuation

    for name, cfg in ASSETS.items():
        code = cfg["code"]
        tracking = cfg.get("tracking_index")

        # 拉取 ETF 价格
        if verbose:
            print(f"  拉取 {name}({code}) 价格...")
        df_price = fetch_etf_price(code)
        if not df_price.empty:
            for _, row in df_price.iterrows():
                insert_etf_price(
                    conn,
                    code=code,
                    trade_date=str(row["trade_date"]),
                    close_adj=float(row["close_adj"]),
                    volume=float(row["volume"]) if pd.notna(row.get("volume")) else None,
                )
            if verbose:
                print(f"    → 入库 {len(df_price)} 条价格记录")

        # 拉取指数估值
        if tracking:
            if verbose:
                print(f"  拉取 {name} 指数估值...")
            df_val = fetch_index_valuation(tracking)
            if not df_val.empty:
                for _, row in df_val.iterrows():
                    insert_index_valuation(
                        conn,
                        index_code=str(tracking),
                        trade_date=str(row["trade_date"]),
                        pe=float(row["pe"]) if pd.notna(row.get("pe")) else None,
                        pb=float(row["pb"]) if pd.notna(row.get("pb")) else None,
                        dividend_yield=float(row["dividend_yield"]) if pd.notna(
                            row.get("dividend_yield")
                        ) else None,
                        publish_date=str(row.get("publish_date", row["trade_date"])),
                    )
                if verbose:
                    print(f"    → 入库 {len(df_val)} 条估值记录")


def load_price_series(
    conn: sqlite3.Connection, etf_code: str
) -> pd.Series:
    """
    从数据库加载 ETF 后复权价格序列，按日期排序。
    """
    rows = conn.execute(
        "SELECT trade_date, close_adj FROM etf_price "
        "WHERE code = ? ORDER BY trade_date",
        (etf_code,),
    ).fetchall()

    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows, columns=["trade_date", "close_adj"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date")
    return pd.Series(df["close_adj"].values, index=df["trade_date"])


def load_valuation_series(
    conn: sqlite3.Connection, index_code: str, field: str, decision_date: date = None,
) -> pd.Series:
    """
    从数据库加载指数估值序列（pe / pb / dividend_yield）。
    """
    valid_fields = {"pe", "pb", "dividend_yield"}
    if field not in valid_fields:
        raise ValueError(f"field must be one of {valid_fields}")

    if decision_date is not None:
        from src.store.validator import get_available_valuations
        available = get_available_valuations(conn, decision_date, index_code)
        rows = [
            (item["trade_date"], item[field])
            for item in available if item.get(field) is not None
        ]
    else:
        query = (
            f"SELECT trade_date, {field} FROM index_valuation "
            f"WHERE index_code = ? AND {field} IS NOT NULL "
            f"ORDER BY trade_date"
        )
        rows = conn.execute(query, (index_code,)).fetchall()

    if not rows:
        return pd.Series(dtype=float)

    df = pd.DataFrame(rows, columns=["trade_date", field])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date")
    return pd.Series(df[field].values, index=df["trade_date"])


def get_latest_date(conn: sqlite3.Connection) -> date:
    """获取数据库中最新的交易日期。"""
    row = conn.execute("SELECT MAX(trade_date) FROM etf_price").fetchone()
    if row and row[0]:
        return pd.to_datetime(row[0]).date()
    return date.today()


def calculate_factors(conn: sqlite3.Connection, latest_date: date) -> dict:
    """
    计算所有资产的最新因子值。
    每个因子都用 expanding window，只用 latest_date 之前的数据。
    """
    factors = {}
    for name, cfg in ASSETS.items():
        code = cfg["code"]
        tracking = cfg.get("tracking_index")
        asset_factors = {}

        # 加载价格序列（用于动量/波动率，非估值）
        price_series = load_price_series(conn, code)
        if not price_series.empty:
            price_series = price_series[price_series.index <= pd.Timestamp(latest_date)]

        # 估值因子（通过 tracking index，独立于 ETF 价格）
        if tracking:
            pe_series = load_valuation_series(conn, tracking, "pe", latest_date)
            pb_series = load_valuation_series(conn, tracking, "pb", latest_date)
            dy_series = load_valuation_series(conn, tracking, "dividend_yield", latest_date)

            # 截断
            if not pe_series.empty:
                pe_series = pe_series[pe_series.index <= pd.Timestamp(latest_date)]
            if not pb_series.empty:
                pb_series = pb_series[pb_series.index <= pd.Timestamp(latest_date)]
            if not dy_series.empty:
                dy_series = dy_series[dy_series.index <= pd.Timestamp(latest_date)]

            # PE 分位
            if name in ("白酒ETF", "沪深300ETF"):
                asset_factors["pe_percentile"] = pe_percentile(
                    pe_series, max_window_years=WINDOW_PE_PERCENTILE_YEARS
                )
            # PB 分位（银行）—— PB 数据不足时不做回退，宁缺毋错
            if name == "银行ETF":
                asset_factors["pb_percentile"] = pb_percentile(
                    pb_series, max_window_years=WINDOW_PE_PERCENTILE_YEARS
                )
                asset_factors["pb_zscore"] = compute_zscore(
                    pb_series, max_window_years=WINDOW_PE_PERCENTILE_YEARS
                )
            # 股息率分位——数据不足时不做回退
            if name in ("银行ETF", "红利ETF"):
                asset_factors["dividend_percentile"] = dividend_yield_percentile(
                    dy_series, max_window_years=WINDOW_PE_PERCENTILE_YEARS
                )
                if name == "银行ETF":
                    asset_factors["dividend_zscore"] = compute_zscore(
                        dy_series, max_window_years=WINDOW_PE_PERCENTILE_YEARS
                    )

        # 动量因子（科创50）
        if name == "科创50ETF":
            from src.factors.momentum import momentum_120d, ma_trend_200d, expanding_percentile
            mom_120 = momentum_120d(price_series)
            trend_on = ma_trend_200d(price_series)

            # 构建动量历史序列计算分位
            clean = price_series.dropna()
            min_len = 121
            if len(clean) >= min_len:
                mom_history = []
                for i in range(min_len, len(clean) + 1):
                    window_series = clean.iloc[:i]
                    m = momentum_120d(window_series)
                    if m is not None:
                        mom_history.append(m)
                if mom_history and mom_120 is not None:
                    mom_series = pd.Series(mom_history)
                    from src.factors.value import expanding_percentile
                    asset_factors["momentum_percentile"] = expanding_percentile(
                        mom_series, mom_120
                    )

            asset_factors["trend_multiplier"] = 1.0 if trend_on else KECHUANG_TREND_OFF_MULTIPLIER

        # 波动率（所有资产，用于风险层）
        vol = annualized_volatility(price_series)
        asset_factors["volatility"] = vol

        factors[name] = asset_factors

    return factors


def compute_current_weights(
    conn: sqlite3.Connection, latest_date: date, overrides: dict = None
) -> dict:
    """
    计算当前组合权重。

    优先使用 overrides（用户传入的权重），否则使用目标带中点。

    Args:
        conn: 数据库连接
        latest_date: 最新日期
        overrides: 用户传入的权重字典 {asset_name: weight}，可选

    Returns:
        {asset_name: weight}
    """
    if overrides:
        missing = [name for name in ASSETS if name not in overrides]
        if missing:
            print(f"[WARN] 权重缺少以下资产: {missing}，使用目标带中点补齐")
            defaults = _midpoint_weights()
            result = dict(overrides)
            for name in missing:
                result[name] = defaults[name]
            return result
        return dict(overrides)

    return _midpoint_weights()


def _midpoint_weights() -> dict:
    """各资产目标带中点权重（适用于无持仓数据时的默认值）。"""
    from config.settings import TARGET_BANDS
    return {
        name: (lower + upper) / 2.0
        for name, (lower, upper) in TARGET_BANDS.items()
    }


def _demo_weights() -> dict:
    """
    演示用的组合权重——模拟"已有持仓但部分资产低于下限"的场景。
    - 白酒 8%  (低于下限10%) → 有缺口
    - 银行 22% (在带内)
    - 红利 8%  (低于下限10%) → 有缺口
    - 沪深300 25% (在带内)
    - 科创50 12% (在带内)
    - 国债 25% (超过上限20%—验证约束层)
    """
    return {
        "白酒ETF": 0.08,
        "银行ETF": 0.22,
        "红利ETF": 0.08,
        "沪深300ETF": 0.25,
        "科创50ETF": 0.12,
        "国债ETF": 0.25,
    }


def _demo_factors() -> dict:
    """
    演示用的因子数据——模拟各资产的因子值和波动率。
    数值设计为：部分资产低估（机会分高），部分中等。
    """
    return {
        "白酒ETF":    {"pe_percentile": 0.15, "volatility": 0.25},
        "银行ETF":    {"pb_percentile": 0.22, "dividend_percentile": 0.80, "pb_zscore": 0.80, "dividend_zscore": 1.10, "volatility": 0.20},
        "红利ETF":    {"dividend_percentile": 0.85, "volatility": 0.18},
        "沪深300ETF": {"pe_percentile": 0.55, "volatility": 0.22},
        "科创50ETF":  {"momentum_percentile": 0.70, "trend_multiplier": 1.0, "volatility": 0.35},
        "国债ETF":    {"volatility": None},
    }


def _parse_weights_arg(raw: str) -> dict:
    """解析 --weights 参数，如 '{"白酒ETF":0.08}'。"""
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError
        return parsed
    except (json.JSONDecodeError, ValueError):
        print("[ERROR] --weights 必须是有效的 JSON 字典，如 '{\"白酒ETF\": 0.08}'")
        sys.exit(1)


def run_report(verbose: bool = False, demo: bool = False,
               weights_override: dict = None, total_assets_input: float = None) -> None:
    """运行流A完整流程，输出月度报告。"""
    reset_recovery_tracking()
    NEW_MONEY = 8_000
    DEFAULT_TOTAL = 500_000

    print("[INFO] ETF-Allocator 流A — 月度配置报告")
    print()

    # ── 演示模式：跳过数据库，用合成数据 ──
    if demo:
        print("[DEMO] 使用模拟数据演示完整流程\n")
        factors = _demo_factors()
        scores = score_all(factors)
        hs300_pe_pct = 0.72
        all_a_pb_pct = 0.68
        current_weights = weights_override or _demo_weights()
        total_assets = total_assets_input if total_assets_input is not None else DEFAULT_TOTAL
        latest_date = date.today()

        print(f"[STEP 1-3] 因子计算 (演示数据)")
        if verbose:
            for name, fac in factors.items():
                print(f"  {name}: {fac}")
        print()

    # ── 正常模式：连接数据库 ──
    else:
        conn = get_db_connection()
        ensure_etf_seed_data(conn)

        print("[STEP 1] 更新数据 (AkShare)...")
        try:
            update_data(conn, verbose=verbose)
        except Exception as e:
            print(f"[WARN] 数据更新失败: {e}")
        print()

        latest_date = get_latest_date(conn)
        print(f"[STEP 2] 决策日期: {latest_date.isoformat()}")
        print()

        print("[STEP 3] 计算因子...")
        factors = calculate_factors(conn, latest_date)
        if verbose:
            for name, fac in factors.items():
                print(f"  {name}: {fac}")
        print()

        print("[STEP 4] 计算机会分...")
        scores = score_all(factors)
        if verbose:
            for name, sc in scores.items():
                print(f"  {name}: {sc}")
        print()

        hs300_factors = factors.get("沪深300ETF", {})
        hs300_pe_pct = hs300_factors.get("pe_percentile")
        # 全A PB分位：从 000985（上证50替代）加载 PB 序列并计算
        all_a_pb_series = load_valuation_series(conn, "000985", "pb", latest_date)
        if not all_a_pb_series.empty:
            all_a_pb_series = all_a_pb_series[all_a_pb_series.index <= pd.Timestamp(latest_date)]
        all_a_pb_pct = pb_percentile(all_a_pb_series, max_window_years=WINDOW_PE_PERCENTILE_YEARS) if not all_a_pb_series.empty else None

        current_weights = compute_current_weights(conn, latest_date, weights_override)
        total_assets = total_assets_input if total_assets_input is not None else DEFAULT_TOTAL

    # ── 初始建仓模式：新组合时权重归零 ──
    if total_assets <= 0:
        total_assets = 0.0
        current_weights = {name: 0.0 for name in current_weights}
        print("[INIT] 检测到初始建仓模式（总资产=0）")

    # ── 5. 市场温度计 ──
    print("[STEP 5] 市场温度计...")
    regime_state_path = PROJECT_ROOT / "data" / "db" / "regime_state.json"
    load_persistence(regime_state_path)
    eq_ratio, bond_ratio = equity_ratio(hs300_pe_pct, all_a_pb_pct)
    save_persistence(regime_state_path)
    overheated = (
        hs300_pe_pct is not None and all_a_pb_pct is not None
        and hs300_pe_pct > 0.90 and all_a_pb_pct > 0.90
    )
    def _temp_tier(value):
        if value is None:
            return None
        if value < 0.60:
            return 0
        if value < 0.80:
            return 1
        if value < 0.90:
            return 2
        return 3
    frozen = _temp_tier(hs300_pe_pct) != _temp_tier(all_a_pb_pct)
    labels = {1.0: "正常（双<60%）", 0.7: "中等偏高（双60%-80%）", 0.4: "高温（双80%-90%）", 0.3: "过热（双>90%）"}
    temp_label = "冻结（双指标档位不一致）" if frozen else labels.get(eq_ratio, "数据不足")
    temp_detail = "维持上一期权益比例" if frozen else f"双指标同档，权益比例 {eq_ratio:.0%}"

    temp_result = {
        "temperature": max(hs300_pe_pct or 0, all_a_pb_pct or 0),
        "equity_ratio": eq_ratio,
        "bond_ratio": bond_ratio,
        "hs300_pe_pct": hs300_pe_pct,
        "all_a_pb_pct": all_a_pb_pct,
        "detail": temp_detail,
        "label": temp_label,
    }
    if hs300_pe_pct is not None:
        print(f"  沪深300 PE分位: {hs300_pe_pct:.0%}  |  全A PB分位: {all_a_pb_pct:.0%}")
    else:
        print(f"  沪深300 PE分位: N/A (请先安装 akshare 获取数据)")
    print(f"  状态: {temp_label}  |  权益: {eq_ratio:.0%}  |  国债: {bond_ratio:.0%}")
    if temp_detail:
        print(f"  {temp_detail}")
    print()

    # ── 6. 风险控制 ──
    print("[STEP 6] 风险控制...")
    volatilities = {name: fac.get("volatility") for name, fac in factors.items()}
    limits = all_effective_limits(volatilities)
    # v1.3: 不在RISK_CONTROL中的资产使用TARGET_BANDS上限作为fallback
    from config.settings import TARGET_BANDS as _TB
    limits = {n: (v if v is not None else _TB.get(n, (0, 0.30))[1])
              for n, v in limits.items()}
    if verbose:
        for name, lim in limits.items():
            print(f"  {name}: {lim:.0%}" if lim else f"  {name}: N/A")
    print()

    # ── 7. 组合约束 ──
    print("[STEP 7] 组合约束...")
    constraints_result = apply_constraints(current_weights, limits, total_assets)

    gw = constraints_result["group_weights"]
    print(f"  价值+红利组: {gw.get('VALUE', 0):.1%} (上限 60%)")
    print(f"  成长组: {gw.get('GROWTH', 0):.1%} (上限 15%)")
    print()

    # ── 8. 资金分配 ──
    print(f"[STEP 8] 资金分配 (新钱={NEW_MONEY:,} 元)...")
    equity_budget = NEW_MONEY * eq_ratio

    allocation = allocate(
        opportunity_scores=scores,
        current_weights=current_weights,
        upper_limits=limits,
        total_assets=total_assets,
        equity_budget=equity_budget,
        buy_coefficients=constraints_result["buy_coefficients"],
    )

    # v1.3: 国债通过累积池执行，解决场内最低买入门槛
    bond_budget = NEW_MONEY * bond_ratio
    bond_alloc_from_allocator = allocation.pop("国债ETF", 0)  # 分配层溢出
    total_bond_deposit = bond_budget + bond_alloc_from_allocator

    # 加载累积池状态（流A跨月持久化）
    accumulator_path = str(PROJECT_ROOT / "data" / "db" / "bond_accumulator.json")
    bond_accumulator = BondAccumulator.load(accumulator_path)
    bond_accumulator.deposit(total_bond_deposit)
    bond_interest = bond_accumulator.accrue_interest()
    bond_action = bond_accumulator.execute()

    if bond_action.buy:
        allocation["国债ETF"] = bond_action.amount
    # 未触发买入时，allocation 中不包含国债ETF

    bond_status = bond_accumulator.get_status()
    bond_status["deposit_this_month"] = total_bond_deposit
    bond_status["interest_this_month"] = bond_interest

    # 保存累积池状态
    bond_accumulator.save(accumulator_path)

    if verbose:
        for name, amt in allocation.items():
            if amt > 0:
                print(f"  {name}: {amt:,.0f} 元")
    print()

    if verbose:
        for name, amt in allocation.items():
            print(f"  {name}: {amt:,.0f} 元")
    print()

    # ── 9. 报告 ──
    print("[STEP 9] 生成报告...\n")
    report = generate_report(
        invest_date=latest_date,
        new_money=NEW_MONEY,
        temp_result=temp_result,
        factors=factors,
        scores=scores,
        allocation=allocation,
        weights=current_weights,
        upper_limits=limits,
        constraints_result=constraints_result,
        bond_status=bond_status,
    )
    print(report)

    if not demo:
        conn.close()
    print("[DONE]")


def run_rebalance_check() -> None:
    """仅运行再平衡检查。"""
    conn = get_db_connection()
    ensure_etf_seed_data(conn)
    
    latest_date = get_latest_date(conn)
    current_weights = compute_current_weights(conn, latest_date)
    
    result = check_rebalance(
        current_date=latest_date,
        current_weights=current_weights,
        total_assets=100_000,
    )
    
    print(f"\n再平衡检查 ({latest_date.isoformat()}):")
    print(f"需再平衡: {'是' if result['rebalance_needed'] else '否'}")
    if result["detail"]:
        print(f"{result['detail']}")
    
    conn.close()


# ---- MAIN ----
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python run.py report [--demo] [--weights JSON] [--total N] [-v]")
        print("       python run.py rebalance")
        print()
        print("  report       运行完整月度配置报告（流A）")
        print("    --demo     使用模拟数据演示（无需安装 akshare）")
        print("    --weights  当前组合权重，如 '{\"白酒ETF\":0.08,\"银行ETF\":0.22}'")
        print("    --total N  当前总资产金额（默认 500,000）")
        print("    -v         详细输出")
        print("  rebalance    仅检查年度再平衡状态")
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "report":
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        demo = "--demo" in sys.argv
        weights_override = None
        total_assets_input = None

        # 解析 --weights
        for i, arg in enumerate(sys.argv):
            if arg == "--weights" and i + 1 < len(sys.argv):
                weights_override = _parse_weights_arg(sys.argv[i + 1])
            if arg == "--total" and i + 1 < len(sys.argv):
                try:
                    total_assets_input = float(sys.argv[i + 1])
                except ValueError:
                    print(f"[ERROR] --total 必须是数值: {sys.argv[i + 1]}")
                    sys.exit(1)

        run_report(
            verbose=verbose,
            demo=demo,
            weights_override=weights_override,
            total_assets_input=total_assets_input,
        )
    elif cmd == "rebalance":
        run_rebalance_check()
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: report, rebalance")
        sys.exit(1)
