"""
validate.py — 流B 入口：离线回测验证。

用法:
    python validate.py train    # 训练期回测 → 打印参数建议
    python validate.py test     # 测试期回测 → 用锁定参数打印指标

流B 纪律:
  - 训练期(TRAIN_START ~ TRAIN_END)定参数 → 锁死 → 测试期(TEST_START ~ TEST_END)只验
  - 绝不"看着回测结果调参数"
  - 输出: 年化收益 / 最大回撤 / 夏普比率 / Calmar

配置来源:
  - config/settings.py 中的所有可调参数
"""
import sys
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np

from config.settings import (
    TRAIN_START, TRAIN_END,
    TEST_START, TEST_END,
    ASSETS,
    TARGET_BANDS,
    TRADING_DAYS_PER_YEAR,
    WINDOW_PE_PERCENTILE_YEARS,
)
from src.store.schema import create_tables
from src.backtest.engine import (
    run_backtest,
    run_sensitivity_analysis,
    run_strategy_comparison,
)
from src.backtest.parameter_lock import verify_snapshot, write_snapshot


DB_PATH = PROJECT_ROOT / "data" / "db" / "etf_data.db"
PARAMETER_LOCK_PATH = PROJECT_ROOT / "data" / "db" / "locked_parameters.json"


def get_db_connection() -> sqlite3.Connection:
    """获取数据库连接。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    return conn


def load_price_series(conn: sqlite3.Connection, etf_code: str) -> pd.Series:
    """从数据库加载 ETF 后复权价格序列。"""
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


def generate_monthly_dates(start: str, end: str) -> list:
    """
    生成每月第一个交易日的近似列表。
    用每月 1 日或最近的有效日期。
    """
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    # 生成月初日期作为决策日
    dates = pd.date_range(start=start_dt, end=end_dt, freq="MS")
    return [d.date() for d in dates]


def simple_backtest(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    monthly_amount: float = 10_000,
) -> dict:
    """
    简化回测：每月定投等额分配。
    
    策略：每月月初用 10,000 元新增资金按等权重购买所有资产。
    国债 ETF 作为现金等价物（价格看作 1.0 或从数据加载）。
    
    Returns:
        {
            "period": (start, end),
            "total_invested": float,
            "final_value": float,
            "annualized_return": float,
            "max_drawdown": float,
            "sharpe_ratio": float,
            "calmar": float,
            "monthly_returns": list,
        }
    """
    decision_dates = generate_monthly_dates(start_date, end_date)
    if not decision_dates:
        return {"error": "无有效决策日"}

    # 为每个 ETF 加载完整价格序列
    price_data = {}
    for name, cfg in ASSETS.items():
        series = load_price_series(conn, cfg["code"])
        if series.empty:
            print(f"  [WARN] {name} 无价格数据，回测跳过")
            continue
        price_data[name] = series

    if not price_data:
        return {"error": "无可用价格数据"}

    # 找到所有资产共有的日期范围
    all_dates = set()
    for series in price_data.values():
        all_dates.update(series.index)
    all_dates = sorted(all_dates)

    # 初始化组合
    equity_assets = [n for n in ASSETS if n != "国债ETF"]
    holdings = {name: 0.0 for name in ASSETS}
    total_invested = 0.0
    monthly_values = []

    for dec_date in decision_dates:
        # 找到决策日最近的交易日期
        dec_ts = pd.Timestamp(dec_date)
        available = [d for d in all_dates if d <= dec_ts]
        if not available:
            continue
        trade_date = available[-1]

        # 获取当日价格
        prices = {}
        for name, series in price_data.items():
            try:
                prices[name] = float(series.loc[trade_date])
            except (KeyError, TypeError):
                # 找之前最近的价格
                prev = [d for d in series.index if d <= trade_date]
                if prev:
                    prices[name] = float(series.loc[prev[-1]])
                else:
                    prices[name] = None

        # 等权重买入
        n_equity = len(equity_assets)
        per_asset = monthly_amount / n_equity if n_equity > 0 else 0

        for name in equity_assets:
            p = prices.get(name)
            if p and p > 0:
                shares = per_asset / p
                holdings[name] += shares
                total_invested += per_asset

        # 国债ETF：买国债等于持有现金
        holdings["国债ETF"] += monthly_amount * 0.0  # 回测中全仓权益

        # 计算当前组合价值
        current_value = 0.0
        for name, shares in holdings.items():
            p = prices.get(name)
            if p and shares > 0:
                current_value += shares * p
        current_value += holdings["国债ETF"]  # 国债当现金

        monthly_values.append({
            "date": trade_date,
            "value": current_value,
            "invested": total_invested,
        })

    if not monthly_values:
        return {"error": "无可用回测数据"}

    # 计算指标
    df_values = pd.DataFrame(monthly_values)
    df_values = df_values.sort_values("date")

    final_value = df_values.iloc[-1]["value"]
    total_invested = df_values.iloc[-1]["invested"]

    # 年化收益率
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    years = (end_dt - start_dt).days / 365.25
    if years > 0 and total_invested > 0:
        annualized_return = (final_value / total_invested) ** (1.0 / years) - 1
    else:
        annualized_return = 0.0

    # 最大回撤（基于组合价值）
    values = df_values["value"].values
    if len(values) > 1:
        peak = values[0]
        max_dd = 0.0
        for v in values:
            if v > peak:
                peak = v
            dd = (v - peak) / peak if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd
    else:
        max_dd = 0.0

    # 月度收益率
    values_series = pd.Series(values, index=df_values["date"])
    monthly_ret = values_series.pct_change().dropna()

    # 夏普比率
    if len(monthly_ret) > 1:
        monthly_mean = monthly_ret.mean()
        monthly_std = monthly_ret.std()
        sharpe = (monthly_mean / monthly_std) * np.sqrt(12) if monthly_std > 0 else 0.0
    else:
        sharpe = 0.0

    # Calmar = 年化收益 / |最大回撤|
    calmar = annualized_return / abs(max_dd) if abs(max_dd) > 0 else 0.0

    return {
        "period": (start_date, end_date),
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2),
        "annualized_return": round(annualized_return, 4),
        "max_drawdown": round(max_dd, 4),
        "sharpe_ratio": round(sharpe, 4),
        "calmar": round(calmar, 4),
        "n_months": len(decision_dates),
    }


def print_train_results(results: dict) -> None:
    """打印训练期结果和参数建议。"""
    dr = results.get("date_range", {})
    m = results.get("metrics", {})

    print()
    print("=" * 60)
    print("  训练期回测结果（完整流水线）")
    print("=" * 60)
    print(f"  期间: {dr.get('start', 'N/A')} ~ {dr.get('end', 'N/A')}")
    print(f"  决策月数: {len(results.get('monthly_results', []))}")
    print(f"  总投资: {results.get('total_invested', 0):,.0f} 元")
    print(f"  终值: {results.get('final_value', 0):,.0f} 元" if results.get("final_value") else "  终值: N/A")
    print(f"  年化收益率: {m.get('annualized_return', 0):.2%}" if m.get("annualized_return") else "  年化收益率: N/A")
    print(f"  最大回撤: {m.get('max_drawdown', 0):.2%}" if m.get("max_drawdown") else "  最大回撤: N/A")
    print(f"  夏普比率: {m.get('sharpe', 0):.2f}" if m.get("sharpe") else "  夏普比率: N/A")
    print(f"  Calmar: {m.get('calmar', 0):.2f}" if m.get("calmar") else "  Calmar: N/A")
    print()

    print("  --- 参数建议 ---")
    print("  训练期参数在 config/settings.py 中定义。")
    print("  请基于上述回测结果调整以下旋钮：")
    print("    - TEMP_THRESHOLDS: 温度计三档阈值 [0.60, 0.80, 0.90]")
    print("    - TEMP_EQUITY_RATIOS: 对应权益比例 [1.00, 0.70, 0.40, 0.30]")
    print("    - TARGET_BANDS: 单标的上限带")
    print("    - GROUP_CAPS: 因子组上限")
    print("    - ALLOCATION_GAP_WEIGHT / OPPORTUNITY_WEIGHT: 分配权重")
    print("    - WINDOW_PE_PERCENTILE_YEARS: 分位窗口年数")
    print()
    print("  [WARN] 调参完成后，锁死参数，用 'python validate.py test' 验证。")
    print("  严禁在测试期回头调参。")
    print("=" * 60)


def print_test_results(results: dict) -> None:
    """打印测试期结果（锁死参数）。"""
    dr = results.get("date_range", {})
    m = results.get("metrics", {})

    print()
    print("=" * 60)
    print("  测试期回测结果（参数锁定）")
    print("=" * 60)
    print(f"  期间: {dr.get('start', 'N/A')} ~ {dr.get('end', 'N/A')}")
    print(f"  决策月数: {len(results.get('monthly_results', []))}")
    print(f"  总投资: {results.get('total_invested', 0):,.0f} 元")
    print(f"  终值: {results.get('final_value', 0):,.0f} 元" if results.get("final_value") else "  终值: N/A")
    print(f"  年化收益率: {m.get('annualized_return', 0):.2%}" if m.get("annualized_return") else "  年化收益率: N/A")
    print(f"  最大回撤: {m.get('max_drawdown', 0):.2%}" if m.get("max_drawdown") else "  最大回撤: N/A")
    print(f"  夏普比率: {m.get('sharpe', 0):.2f}" if m.get("sharpe") else "  夏普比率: N/A")
    print(f"  Calmar: {m.get('calmar', 0):.2f}" if m.get("calmar") else "  Calmar: N/A")
    print("=" * 60)


def print_strategy_comparison(comparison: dict) -> None:
    """Print four pre-registered variants and the shadow/live acceptance gates."""
    print()
    print("=" * 88)
    print("  四策略测试期对照（净交易成本口径）")
    print("=" * 88)
    print(f"  {'策略':<28}{'年化':>10}{'最大回撤':>12}{'Calmar':>10}{'成本':>12}{'卖出':>8}")
    for name, result in comparison["variants"].items():
        metrics = result.get("metrics", {})
        execution = result.get("execution", {})
        annualized = metrics.get("annualized_return")
        drawdown = metrics.get("max_drawdown")
        calmar = metrics.get("calmar")
        annualized_text = f"{annualized:.2%}" if annualized is not None else "N/A"
        drawdown_text = f"{drawdown:.2%}" if drawdown is not None else "N/A"
        calmar_text = f"{calmar:.2f}" if calmar is not None else "N/A"
        print(
            f"  {name:<28}{annualized_text:>10}{drawdown_text:>12}{calmar_text:>10}"
            f"{execution.get('total_costs', 0):>12,.2f}{execution.get('sell_count', 0):>8}"
        )
    print()
    gates = comparison["acceptance"]["gates"]
    for gate, passed in gates.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {gate}")
    print(f"  科创利润保护状态: {comparison['acceptance']['profit_protection_status']}")
    print(f"  {comparison['acceptance']['note']}")
    print("=" * 88)


def run_train() -> None:
    """训练期回测 — 使用完整 PIT 回测引擎。"""
    print("[INFO] 流B — 训练期回测（完整流水线：因子→评分→温度计→风险→约束→分配）")
    print(f"[INFO] 期间: {TRAIN_START} ~ {TRAIN_END}")
    print()

    conn = get_db_connection()

    try:
        results = run_backtest(conn, mode="train")
    except Exception as e:
        print(f"[ERROR] 回测失败: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        sys.exit(1)

    conn.close()

    if results.get("final_value") is None and not results.get("monthly_results"):
        print("[ERROR] 回测无有效数据")
        sys.exit(1)

    print_train_results(results)
    snapshot = write_snapshot(PARAMETER_LOCK_PATH)
    print(f"[LOCK] 参数快照: {PARAMETER_LOCK_PATH}")
    print(f"[LOCK] SHA-256: {snapshot['parameter_hash']}")


def run_test() -> None:
    """测试期回测 — 使用完整 PIT 回测引擎（参数锁定）。"""
    print("[INFO] 流B — 测试期回测（完整流水线 + 参数锁定）")
    print(f"[INFO] 期间: {TEST_START} ~ {TEST_END}")
    print("[WARN] 参数已在训练期锁死，测试期只验不调！")
    print()

    valid, detail = verify_snapshot(PARAMETER_LOCK_PATH)
    if not valid:
        print(f"[ERROR] {detail}")
        sys.exit(1)
    print(f"[LOCK] 参数校验通过: {detail}")

    conn = get_db_connection()

    try:
        results = run_strategy_comparison(conn, mode="test")
    except Exception as e:
        print(f"[ERROR] 回测失败: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        sys.exit(1)

    conn.close()

    full = results.get("variants", {}).get("full_protection", {})
    if full.get("final_value") is None and not full.get("monthly_results"):
        print("[ERROR] 回测无有效数据")
        sys.exit(1)
    print_strategy_comparison(results)


def run_sensitivity() -> None:
    """Run the fixed neighboring grid without changing the parameter lock."""
    valid, detail = verify_snapshot(PARAMETER_LOCK_PATH)
    if not valid:
        print(f"[ERROR] {detail}")
        sys.exit(1)
    print(f"[LOCK] 参数校验通过: {detail}")
    conn = get_db_connection()
    try:
        report = run_sensitivity_analysis(conn, mode="test")
    finally:
        conn.close()
    print(f"[INFO] 敏感性组合数: {len(report['results'])}")
    print(f"[LOCKED] 预注册参数保持不变: {report['locked_choice']}")
    print("[INFO] selection_performed=false；测试期不选择最优参数")


# ---- MAIN ----
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python validate.py <mode>")
        print("  train — 训练期回测，打印参数建议")
        print("  test  — 测试期回测，使用锁定参数打印指标")
        print("  sensitivity — 运行预注册邻近参数敏感性报告（不择优）")
        sys.exit(0)

    mode = sys.argv[1].lower()

    if mode == "train":
        run_train()
    elif mode == "test":
        run_test()
    elif mode == "sensitivity":
        run_sensitivity()
    else:
        print(f"未知模式: {mode}")
        print("可用模式: train, test, sensitivity")
        sys.exit(1)
