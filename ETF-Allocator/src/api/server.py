"""
src/api/server.py — FastAPI 后端，复用现有 src/ 模块提供数据接口。

端点:
  GET  /api/report?date=...    — 月报数据
  POST /api/report              — 自定义参数模拟
  GET  /api/history?index=...&field=...&years=...  — PE/PB 历史序列
"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config.settings import (
    ASSETS,
    WINDOW_PE_PERCENTILE_YEARS,
    DEFAULT_NEW_MONEY,
    DEFAULT_TOTAL_ASSETS,
)
from src.store.schema import create_tables
from src.scoring.engine import score_all
from src.regime.thermometer import read_persistence, resolve_equity_ratio
from src.risk.controller import all_effective_limits, reset_recovery_tracking
from src.constraints.portfolio import apply_constraints
from src.allocation.allocator import allocate
# V2 决策函数（preview/confirm 调用）；模块级暴露满足"API/CLI/回测同一决策函数"契约
from src.strategy.planner import build_trade_plan
from src.strategy.models import PortfolioSnapshot, PositionSnapshot
from src.strategy.kechuang import KechuangProtectionState
from src.strategy import repository as strategy_repo

# v1.3: bond accumulator（仅 run.py 流A + 回测用，API 路径不再触碰）
from src.execution.bond_liquidity import BondAccumulator

app = FastAPI(title="ETF-Allocator API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = PROJECT_ROOT / "data" / "db" / "etf_data.db"
NEW_MONEY_DEFAULT = DEFAULT_NEW_MONEY          # 从 settings 统一读取（audit C4）
TOTAL_ASSETS_DEFAULT = DEFAULT_TOTAL_ASSETS
REGIME_STATE_PATH = PROJECT_ROOT / "data" / "db" / "regime_state.json"
BOND_ACCUMULATOR_PATH = PROJECT_ROOT / "data" / "db" / "bond_accumulator.json"


class ReportParams(BaseModel):
    date: Optional[str] = None
    new_money: float = NEW_MONEY_DEFAULT
    total_assets: float = TOTAL_ASSETS_DEFAULT
    current_weights: Optional[dict[str, float]] = None


class InvestmentRecordParams(BaseModel):
    investment_date: date
    amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    allocations: dict[str, Decimal] = Field(default_factory=dict)
    note: str = Field(default="", max_length=200)


def _open_investment_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_tables(conn)
    return conn


def _serialize_investment(
    row: sqlite3.Row,
    allocations: Optional[dict[str, float]] = None,
) -> dict:
    return {
        "id": row["id"],
        "investment_date": row["investment_date"],
        "amount": round(row["amount_cents"] / 100, 2),
        "note": row["note"],
        "created_at": row["created_at"],
        "allocations": allocations or {},
    }


def _investment_response(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT id, investment_date, amount_cents, note, created_at "
        "FROM investment_record ORDER BY investment_date DESC, id DESC"
    ).fetchall()
    item_rows = conn.execute(
        "SELECT record_id, asset, amount_cents FROM investment_record_item "
        "ORDER BY record_id, asset"
    ).fetchall()
    allocations_by_record: dict[int, dict[str, float]] = {}
    for item in item_rows:
        allocations_by_record.setdefault(item["record_id"], {})[item["asset"]] = round(
            item["amount_cents"] / 100, 2
        )
    records = [
        _serialize_investment(row, allocations_by_record.get(row["id"]))
        for row in rows
    ]
    total_cents = sum(row["amount_cents"] for row in rows)
    latest = records[0] if records else None
    return {
        "records": records,
        "summary": {
            "count": len(records),
            "total_amount": round(total_cents / 100, 2),
            "last_date": latest["investment_date"] if latest else None,
            "last_amount": latest["amount"] if latest else None,
        },
    }


@app.get("/api/investments")
def get_investments():
    conn = _open_investment_db()
    try:
        return _investment_response(conn)
    finally:
        conn.close()


@app.post("/api/investments", status_code=201)
def create_investment(params: InvestmentRecordParams):
    if params.investment_date > date.today():
        raise HTTPException(status_code=422, detail="投入日期不能晚于今天")

    note = params.note.strip()
    allowed_assets = tuple(ASSETS.keys())
    unknown_assets = sorted(set(params.allocations) - set(allowed_assets))
    if unknown_assets:
        raise HTTPException(
            status_code=422,
            detail=f"不支持的资产: {', '.join(unknown_assets)}",
        )

    allocation_cents: dict[str, int] = {}
    if params.allocations:
        for asset in allowed_assets:
            value = params.allocations.get(asset, Decimal("0"))
            if value < 0:
                raise HTTPException(status_code=422, detail=f"{asset} 投入金额不能为负数")
            if value > Decimal("999999999999.99"):
                raise HTTPException(status_code=422, detail=f"{asset} 投入金额过大")
            allocation_cents[asset] = int(
                (value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        amount_cents = sum(allocation_cents.values())
        if params.amount is not None:
            declared_cents = int(
                (params.amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            if declared_cents != amount_cents:
                raise HTTPException(status_code=422, detail="总金额与资产明细合计不一致")
    elif params.amount is not None:
        # 兼容旧客户端和已有纯总额记录；新页面始终提交 allocations。
        amount_cents = int(
            (params.amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    else:
        amount_cents = 0

    if amount_cents <= 0:
        raise HTTPException(status_code=422, detail="至少一个资产的投入金额必须大于 0")

    conn = _open_investment_db()
    try:
        try:
            cursor = conn.execute(
                "INSERT INTO investment_record (investment_date, amount_cents, note) "
                "VALUES (?, ?, ?)",
                (params.investment_date.isoformat(), amount_cents, note),
            )
            record_id = cursor.lastrowid
            if allocation_cents:
                conn.executemany(
                    "INSERT INTO investment_record_item (record_id, asset, amount_cents) "
                    "VALUES (?, ?, ?)",
                    [
                        (record_id, asset, allocation_cents[asset])
                        for asset in allowed_assets
                    ],
                )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="这条投入记录已经存在") from exc

        row = conn.execute(
            "SELECT id, investment_date, amount_cents, note, created_at "
            "FROM investment_record WHERE id = ?",
            (record_id,),
        ).fetchone()
        serialized_allocations = {
            asset: round(cents / 100, 2)
            for asset, cents in allocation_cents.items()
        }
        return _serialize_investment(row, serialized_allocations)
    finally:
        conn.close()


@app.delete("/api/investments/{record_id}", status_code=204)
def delete_investment(record_id: int):
    conn = _open_investment_db()
    try:
        cursor = conn.execute("DELETE FROM investment_record WHERE id = ?", (record_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="投入记录不存在")
        conn.commit()
        return Response(status_code=204)
    finally:
        conn.close()


# ── imports from run.py (guarded, safe since run.py has __name__ guard) ──
def _import_run_functions():
    """延迟导入 run.py 的计算函数（避免重复执行）。"""
    from run import (
        get_db_connection, ensure_etf_seed_data, get_latest_date,
        calculate_factors, compute_current_weights,
        load_valuation_series,
    )
    return get_db_connection, ensure_etf_seed_data, get_latest_date, calculate_factors, compute_current_weights, load_valuation_series


def _midpoint_weights():
    from config.settings import TARGET_BANDS
    return {name: (lo + hi) / 2.0 for name, (lo, hi) in TARGET_BANDS.items()}


# ── GET /api/report ──
@app.get("/api/report")
def get_report(
    date_str: Optional[str] = Query(None, alias="date"),
    total_assets: float = Query(0, alias="total"),   # 0 = 初始建仓模式
):
    get_db, seed, get_latest, calc_factors, calc_weights, load_vals = _import_run_functions()
    conn = get_db()
    seed(conn)
    reset_recovery_tracking()

    latest = get_latest(conn)
    d = pd.to_datetime(date_str).date() if date_str else latest

    factors = calc_factors(conn, d)
    scores = score_all(factors)

    hs300 = factors.get("沪深300ETF", {})
    p1 = hs300.get("pe_percentile")
    # 全A PB分位：从 000985（上证50替代）计算
    from config.settings import WINDOW_PE_PERCENTILE_YEARS as _WYEARS
    from src.factors.value import pb_percentile as _pb_pct
    all_a_pb_s = load_vals(conn, "000985", "pb", d)
    if not all_a_pb_s.empty:
        all_a_pb_s = all_a_pb_s[all_a_pb_s.index <= pd.Timestamp(d)]
    p2 = _pb_pct(all_a_pb_s, max_window_years=_WYEARS) if not all_a_pb_s.empty else None

    # 长周期 PE 分位（10年 expanding window）
    from config.settings import WINDOW_PE_PERCENTILE_LONG
    from src.factors.value import pe_percentile
    pe_long_s = load_vals(conn, "000300", "pe", d)
    if not pe_long_s.empty:
        pe_long_s = pe_long_s[pe_long_s.index <= pd.Timestamp(d)]
    p1_long = pe_percentile(pe_long_s, max_window_years=WINDOW_PE_PERCENTILE_LONG) if not pe_long_s.empty else None
    # 全A PB 长周期
    all_a_pb_long_s = load_vals(conn, "000985", "pb", d)
    if not all_a_pb_long_s.empty:
        all_a_pb_long_s = all_a_pb_long_s[all_a_pb_long_s.index <= pd.Timestamp(d)]
    p2_long = _pb_pct(all_a_pb_long_s, max_window_years=WINDOW_PE_PERCENTILE_LONG) if not all_a_pb_long_s.empty else None

    eq_ratio, bond_ratio = resolve_equity_ratio(p1, p2, read_persistence(REGIME_STATE_PATH))

    vols = {n: fac.get("volatility") for n, fac in factors.items()}
    limits = all_effective_limits(vols)
    limits = {n: (v if v is not None else 0.3) for n, v in limits.items()}

    weights = calc_weights(conn, d)
    total = total_assets

    # total=0 → 初始建仓，所有权重归零
    if total <= 0:
        weights = {name: 0.0 for name in weights}

    cons = apply_constraints(weights, limits, total)

    # v1.3 退役：GET report 不再做决策（allocate/bond模拟）。
    # 决策由 POST /api/trade-plan/preview 提供。本接口仅返回市场状态。

    conn.close()

    # 温度计状态：用档位映射到英文 key，前端根据 key 显示中文标签
    from src.regime.thermometer import _tier
    tier_labels = {0: "cool", 1: "mild_cool", 2: "strong_cool", 3: "overheat"}
    t1 = _tier(p1) if p1 is not None else None
    t2 = _tier(p2) if p2 is not None else None
    if t1 is not None and t2 is not None and t1 == t2:
        temperature_status = tier_labels.get(t1, "cool")
    elif t1 is not None and t2 is not None:
        temperature_status = "frozen"
    else:
        temperature_status = "cool"

    assets_out = []
    for name, cfg in ASSETS.items():
        w = weights.get(name, 0)
        ul = limits.get(name, 0)
        f = factors.get(name, {})
        s = scores.get(name)
        assets_out.append({
            "name": name, "code": cfg["code"], "factor_group": cfg["factor_group"],
            "score": s, "weight_current": w, "weight_upper": ul,
            "weight_lower": 0.10,  # default
            "pe_percentile": f.get("pe_percentile"),
            "pb_percentile": f.get("pb_percentile"),
            "dividend_percentile": f.get("dividend_percentile"),
            "momentum_percentile": f.get("momentum_percentile"),
            "volatility": f.get("volatility"),
            "trend_multiplier": f.get("trend_multiplier"),
        })

    from config.settings import TARGET_BANDS
    for a in assets_out:
        band = TARGET_BANDS.get(a["name"])
        if band:
            a["weight_lower"] = band[0]

    # Build trigger reasons
    for a in assets_out:
        reasons = []
        if a.get("pe_percentile") is not None:
            reasons.append(f'PE分位 {(a["pe_percentile"]*100):.0f}%')
        if a.get("pb_percentile") is not None:
            reasons.append(f'PB分位 {(a["pb_percentile"]*100):.0f}%')
        if a.get("dividend_percentile") is not None:
            reasons.append(f'股息率分位 {(a["dividend_percentile"]*100):.0f}%')
        if a.get("momentum_percentile") is not None:
            trend = "ON" if a.get("trend_multiplier", 0) >= 1 else "OFF"
            reasons.append(f'动量分位 {(a["momentum_percentile"]*100):.0f}%, 趋势{trend}')
        if not reasons and a["name"] == "国债ETF":
            reasons.append("国债避险配置")
        a["trigger_reason"] = ", ".join(reasons) if reasons else "数据不足"

    # 红利 ETF 单因子背离检查
    hl_div = factors.get("红利ETF", {}).get("dividend_percentile")
    if hl_div is not None and hl_div > 0.85 and (p1 is not None and p1 > 0.6):
        for a in assets_out:
            if a["name"] == "红利ETF":
                a["trigger_reason"] += " ⚠️仅股息率单因子，市场PE偏高，注意估值背离"
                break

    return {
        "date": d.isoformat(),
        "market_temp": {
            "hs300_pe_percentile": p1,
            "all_a_pb_percentile": p2,
            "hs300_pe_percentile_long": p1_long,
            "all_a_pb_percentile_long": p2_long,
            "equity_ratio": eq_ratio,
            "bond_ratio": bond_ratio,
            "status": temperature_status,
        },
        "portfolio_risk": {
            "value_group_weight": cons["group_weights"].get("VALUE", 0),
            "value_group_cap": 0.60,
            "growth_group_weight": cons["group_weights"].get("GROWTH", 0),
            "growth_group_cap": 0.15,
            "next_rebalance_date": f"{d.year}-12-01",
        },
        "assets": assets_out,
        "warnings": [
            f'{a["name"]} 估值数据不足，本月跳过' for a in assets_out
            if a["trigger_reason"] == "数据不足" and a["name"] != "国债ETF"
        ],
        # 红利 ETF 单因子背离检查：股息率极端低估 vs 市场 PE 高估
        "_divergence_check": True,  # 标记前端可展开详情
        "_divergence_note": (
            f'红利ETF仅用股息率分位({int((factors.get("红利ETF", {}).get("dividend_percentile") or 0) * 100)}分)，'
            f'未纳入PE/PB价格估值。当前市场PE分位{int(p1 * 100) if p1 else "?"}%处于高位，'
            '单因子"极端低估"需结合价格估值综合判断。'
        ) if (factors.get("红利ETF", {}).get("dividend_percentile") or 0) > 0.85 and (p1 or 0) > 0.6 else "",
    }


# ── POST /api/report ──
@app.post("/api/report")
def post_report(params: ReportParams):
    get_db, seed, get_latest, calc_factors, calc_weights, load_vals = _import_run_functions()
    conn = get_db()
    seed(conn)
    reset_recovery_tracking()

    d = pd.to_datetime(params.date).date() if params.date else get_latest(conn)

    factors = calc_factors(conn, d)
    scores = score_all(factors)

    hs300 = factors.get("沪深300ETF", {})
    p1 = hs300.get("pe_percentile")
    # 全A PB分位：从 000985（上证50替代）计算
    from config.settings import WINDOW_PE_PERCENTILE_YEARS as _WYEARS
    from src.factors.value import pb_percentile as _pb_pct
    all_a_pb_s = load_vals(conn, "000985", "pb", d)
    if not all_a_pb_s.empty:
        all_a_pb_s = all_a_pb_s[all_a_pb_s.index <= pd.Timestamp(d)]
    p2 = _pb_pct(all_a_pb_s, max_window_years=_WYEARS) if not all_a_pb_s.empty else None
    eq_ratio, bond_ratio = resolve_equity_ratio(p1, p2, read_persistence(REGIME_STATE_PATH))

    vols = {n: fac.get("volatility") for n, fac in factors.items()}
    limits = all_effective_limits(vols)
    limits = {n: (v if v is not None else 0.3) for n, v in limits.items()}

    weights = params.current_weights or _midpoint_weights()
    total = max(params.total_assets, 0)
    cons = apply_constraints(weights, limits, total)

    alloc = allocate(scores, weights, limits, total, params.new_money * eq_ratio, cons["buy_coefficients"])

    # v1.3: bond accumulator
    bond_budget_post = params.new_money * bond_ratio
    bond_alloc_overflow_post = alloc.pop("国债ETF", 0)
    total_bond_deposit_post = bond_budget_post + bond_alloc_overflow_post
    accumulator_path_post = str(BOND_ACCUMULATOR_PATH)
    bond_acc_post = BondAccumulator.load(accumulator_path_post)
    bond_acc_post.deposit(total_bond_deposit_post)
    bond_interest_post = bond_acc_post.accrue_interest()
    bond_action_post = bond_acc_post.execute()
    if bond_action_post.buy:
        alloc["国债ETF"] = bond_action_post.amount
    bond_status_post = bond_acc_post.get_status()
    bond_status_post["deposit_this_month"] = total_bond_deposit_post
    bond_status_post["interest_this_month"] = bond_interest_post
    bond_status_post["action_buy"] = bond_action_post.buy
    bond_status_post["action_lots"] = bond_action_post.lots
    bond_status_post["action_amount"] = bond_action_post.amount

    # 投后仓位计算
    post_weights = {}
    new_total = total + params.new_money
    for name in ASSETS:
        current_val = weights.get(name, 0) * total
        # 未达到 ETF 买入门槛前，累积池仍属于 DEFENSE 资产，必须计入投后权重。
        added = total_bond_deposit_post if name == "国债ETF" else alloc.get(name, 0)
        post_weights[name] = round((current_val + added) / new_total, 6) if new_total > 0 else 0

    conn.close()

    assets_out = []
    for name, cfg in ASSETS.items():
        f = factors.get(name, {})
        s = scores.get(name)
        assets_out.append({
            "name": name, "code": cfg["code"],
            "score": s, "weight_before": weights.get(name, 0),
            "weight_after": post_weights.get(name, 0),
            "weight_upper": limits.get(name, 0),
            "allocation": alloc.get(name, 0),
            "pe_percentile": f.get("pe_percentile"),
            "momentum_percentile": f.get("momentum_percentile"),
            "volatility": f.get("volatility"),
        })

    return {
        "date": d.isoformat(),
        "new_money": params.new_money,
        "total_assets": total,
        "new_total": new_total,
        "before_weights": {name: weights.get(name, 0) for name in ASSETS},
        "after_weights": post_weights,
        "allocations": [
            {
                "asset": a["name"],
                "code": a.get("code", ""),
                "amount": a["allocation"],
                "current_weight": a["weight_before"],
                "upper_limit": a["weight_upper"],
                "opportunity_score": a["score"],
                "trigger_reason": (
                    (f'PE分位 {int(a["pe_percentile"]*100)}%' if a.get("pe_percentile") is not None else '') +
                    (f'PB分位 {int(a.get("pb_percentile", 0)*100)}%' if a.get("pb_percentile") is not None else '') +
                    (f'股息率分位 {int(factors.get(a["name"], {}).get("dividend_percentile", 0)*100)}%'
                     if factors.get(a["name"], {}).get("dividend_percentile") is not None else '') +
                    (f'动量分位 {int(a.get("momentum_percentile", 0)*100)}%'
                     if a.get("momentum_percentile") is not None else '') +
                    ('国债避险配置' if a["name"] == "国债ETF" and not any([
                        a.get("pe_percentile"), a.get("pb_percentile"),
                        factors.get(a["name"], {}).get("dividend_percentile"),
                        a.get("momentum_percentile")
                    ]) else '') +
                    (' ⚠️仅股息率单因子，市场PE偏高，注意估值背离'
                     if a["name"] == "红利ETF"
                     and factors.get("红利ETF", {}).get("dividend_percentile", 0) > 0.85
                     and (p1 is not None and p1 > 0.6) else '')
                ) or "数据不足",
            }
            for a in assets_out
        ],
        "bond_status": bond_status_post,
    }


# ============================================================
# V2: 完整快照交易计划（preview / confirm）
# ============================================================

class PositionSnapshotParams(BaseModel):
    asset: str
    code: str
    shares: float = Field(ge=0)
    price: float = Field(ge=0)
    market_value: Optional[float] = Field(default=None, ge=0)
    average_cost: Optional[float] = Field(default=None, ge=0)
    is_equity: bool = True


class PortfolioSnapshotParams(BaseModel):
    snapshot_date: date
    price_date: date
    new_money: float = 0.0
    account_cash: float = 0.0
    bond_pool_cash: float = 0.0
    reverse_repo_cash: float = 0.0
    equity_pending_cash: float = 0.0
    confirmed_sell_proceeds: float = 0.0
    positions: list[PositionSnapshotParams] = Field(default_factory=list)
    legacy_allocation_only: bool = False


class TradePlanPreviewParams(BaseModel):
    snapshot: PortfolioSnapshotParams
    opportunity_scores: Optional[dict[str, Optional[float]]] = None
    risk_upper_limits: Optional[dict[str, float]] = None
    thermometer_equity_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    market_prices: dict[str, float] = Field(default_factory=dict)
    kechuang_trend_on: Optional[bool] = None
    protection_mode: Optional[str] = None


class TradeFillParams(BaseModel):
    asset: str
    shares: float = Field(gt=0)
    price: float = Field(gt=0)
    commission: Optional[float] = Field(default=None, ge=0)


class TradePlanConfirmParams(TradePlanPreviewParams):
    plan_id: str = Field(min_length=8)
    idempotency_key: str = Field(min_length=8, max_length=200)
    fills: list[TradeFillParams] = Field(default_factory=list)


def _domain_position(p: PositionSnapshotParams) -> PositionSnapshot:
    return PositionSnapshot(
        asset=p.asset, code=p.code, shares=p.shares, price=p.price,
        market_value=p.market_value, average_cost=p.average_cost, is_equity=p.is_equity,
    )


def _domain_snapshot(s: PortfolioSnapshotParams) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_date=s.snapshot_date, price_date=s.price_date,
        new_money=s.new_money, account_cash=s.account_cash,
        bond_pool_cash=s.bond_pool_cash, reverse_repo_cash=s.reverse_repo_cash,
        equity_pending_cash=s.equity_pending_cash,
        confirmed_sell_proceeds=s.confirmed_sell_proceeds,
        positions=tuple(_domain_position(p) for p in s.positions),
        legacy_allocation_only=s.legacy_allocation_only,
    )


def _resolve_trade_inputs(
    conn: sqlite3.Connection,
    params: TradePlanPreviewParams,
) -> tuple[dict[str, Optional[float]], dict[str, float], float, dict[str, float], bool]:
    """Resolve optional decision inputs (factors, limits, thermometer) from PIT pipeline."""
    decision_date = params.snapshot.price_date
    factors: dict[str, dict] = {}
    needs_factors = (
        params.opportunity_scores is None
        or params.risk_upper_limits is None
        or params.thermometer_equity_ratio is None
        or params.kechuang_trend_on is None
    )
    if needs_factors:
        get_db, seed, get_latest, calc_factors, calc_weights, load_vals = _import_run_functions()
        factors = calc_factors(conn, decision_date)

    # opportunity scores
    if params.opportunity_scores is not None:
        scores = dict(params.opportunity_scores)
    else:
        scores = score_all(factors)

    # risk upper limits
    if params.risk_upper_limits is not None:
        limits = dict(params.risk_upper_limits)
    else:
        vols = {n: fac.get("volatility") for n, fac in factors.items()}
        limits = {n: (v if v is not None else 0.3) for n, v in all_effective_limits(vols).items()}

    # thermometer equity ratio
    if params.thermometer_equity_ratio is not None:
        eq_ratio = params.thermometer_equity_ratio
    else:
        from config.settings import WINDOW_PE_PERCENTILE_YEARS as _WYEARS
        from src.factors.value import pb_percentile as _pb_pct
        hs300 = factors.get("沪深300ETF", {})
        p1 = hs300.get("pe_percentile")
        all_a_pb_s = load_vals(conn, "000985", "pb", decision_date) if needs_factors else pd.Series(dtype=float)
        if not all_a_pb_s.empty:
            all_a_pb_s = all_a_pb_s[all_a_pb_s.index <= pd.Timestamp(decision_date)]
        p2 = _pb_pct(all_a_pb_s, max_window_years=_WYEARS) if not all_a_pb_s.empty else None
        eq_ratio, _ = resolve_equity_ratio(p1, p2, read_persistence(REGIME_STATE_PATH))

    # kechuang trend
    if params.kechuang_trend_on is not None:
        trend_on = params.kechuang_trend_on
    else:
        trend_on = factors.get("科创50ETF", {}).get("trend_multiplier", 1.0) >= 1.0

    return scores, limits, eq_ratio, dict(params.market_prices), trend_on


def _preview_plan(
    conn: sqlite3.Connection,
    params: TradePlanPreviewParams,
) -> tuple[PortfolioSnapshot, KechuangProtectionState, TradePlan, dict]:
    """Build a read-only trade plan from preview params (no persistence)."""
    from config.settings import KECHUANG_PROTECTION_MODE
    domain_snapshot = _domain_snapshot(params.snapshot)
    scores, limits, eq_ratio, market_prices, trend_on = _resolve_trade_inputs(conn, params)
    persisted_state = strategy_repo.load_kechuang_state(conn)
    plan = build_trade_plan(
        domain_snapshot,
        opportunity_scores=scores,
        risk_upper_limits=limits,
        thermometer_equity_ratio=eq_ratio,
        market_prices=market_prices,
        kechuang_trend_on=trend_on,
        kechuang_state=persisted_state,
        protection_mode=params.protection_mode or KECHUANG_PROTECTION_MODE,
    )
    context = {"kechuang_trend_on": trend_on}
    return domain_snapshot, persisted_state, plan, context


@app.post("/api/trade-plan/preview")
def preview_trade_plan(params: TradePlanPreviewParams):
    """V2 完整快照只读预览（无副作用）。决策类操作的核心入口。"""
    conn = _open_investment_db()
    try:
        snapshot, _state, plan, context = _preview_plan(conn, params)
    finally:
        conn.close()
    ks = plan.state_patch.get("kechuang", {})
    obs = plan.state_patch.get("observation", {})
    from config.settings import (
        KECHUANG_ACTIVATION_RETURN, KECHUANG_DRAWDOWN_TRIGGER,
        KECHUANG_OFF_MONTHS_EXIT, KECHUANG_PARTIAL_SELL_FRACTION,
    )
    shadow_sells_for_k50 = [o for o in plan.shadow_sells if o.asset == "科创50ETF"]
    return {
        "snapshot_total_assets": round(snapshot.total_assets, 2),
        "trade_plan": plan.to_dict(),
        "protection_status": {
            "mode": ks.get("mode", "shadow"),
            "active": ks.get("active", False),
            "cycle_id": ks.get("cycle_id", 0),
            "high_watermark": ks.get("high_watermark", 0.0),
            "off_months": ks.get("off_months", 0),
            "on_months": ks.get("on_months", 0),
            "pending_trigger": ks.get("pending_trigger"),
            "profit_return": obs.get("profit_return"),
            "drawdown_from_high": obs.get("drawdown_from_high"),
            "activated_this_month": obs.get("activated_this_month", False),
            "trend_on": context.get("kechuang_trend_on", True),
            "triggered": len(shadow_sells_for_k50) > 0,
            "trigger_reason_codes": [o.reason_codes[0] if o.reason_codes else "" for o in shadow_sells_for_k50],
            "thresholds": {
                "activation_return": KECHUANG_ACTIVATION_RETURN,
                "drawdown_trigger": KECHUANG_DRAWDOWN_TRIGGER,
                "off_months_exit": KECHUANG_OFF_MONTHS_EXIT,
                "partial_sell_fraction": KECHUANG_PARTIAL_SELL_FRACTION,
            },
        },
        "read_only": True,
    }


@app.post("/api/trade-plan/confirm")
def confirm_trade_plan(params: TradePlanConfirmParams):
    """显式确认月度观察/真实卖出（有副作用：写 SQLite + 推进科创状态）。幂等。"""
    conn = _open_investment_db()
    try:
        snapshot, persisted_state, plan, context = _preview_plan(conn, params)
    except Exception:
        conn.close()
        raise

    if plan.plan_id != params.plan_id:
        conn.close()
        raise HTTPException(status_code=409, detail="计划已变化，请重新预览后确认")

    # 两阶段：有正式卖单时必须回填 fills
    if plan.formal_sells and not params.fills:
        conn.close()
        raise HTTPException(status_code=422, detail="正式卖单必须先回填真实成交")
    if not plan.formal_sells and params.fills:
        conn.close()
        raise HTTPException(status_code=422, detail="当前计划没有可确认的正式卖单")

    # 推进后的科创状态（从 plan 的 state_patch 取）
    next_state = KechuangProtectionState.from_mapping(plan.state_patch.get("kechuang"))

    # 构造响应体（也是要持久化的 response_json）
    response_body: dict[str, Any] = {
        "confirmation": {
            "idempotency_key": params.idempotency_key,
            "plan_id": params.plan_id,
        },
        "confirmed_plan": plan.to_dict(),
        "next_plan": None,
    }

    # 如果有 fills，重算下一阶段买单
    if params.fills:
        from src.strategy.planner import build_trade_plan as _btp
        from config.settings import KECHUANG_PROTECTION_MODE
        fill_by_asset = {f.asset: f for f in params.fills}
        updated_positions = []
        for p in params.snapshot.positions:
            if p.asset in fill_by_asset:
                fill = fill_by_asset[p.asset]
                new_shares = max(0.0, p.shares - fill.shares)
                # 改 price 后必须同步 market_value，否则 PositionSnapshot 校验不一致
                p = p.model_copy(update={
                    "shares": new_shares,
                    "price": fill.price,
                    "market_value": new_shares * fill.price,
                })
            updated_positions.append(p)
        updated_snapshot_params = params.snapshot.model_copy(update={"positions": updated_positions})
        updated_domain = _domain_snapshot(updated_snapshot_params)
        scores, limits, eq_ratio, market_prices, trend_on = _resolve_trade_inputs(conn, params)
        next_plan = _btp(
            updated_domain,
            opportunity_scores=scores,
            risk_upper_limits=limits,
            thermometer_equity_ratio=eq_ratio,
            market_prices=market_prices,
            kechuang_trend_on=trend_on,
            kechuang_state=next_state,
            protection_mode=params.protection_mode or KECHUANG_PROTECTION_MODE,
        )
        response_body["next_plan"] = next_plan.to_dict()

    # 幂等持久化（save_confirmation 内部检查 existing）
    saved = strategy_repo.save_confirmation(
        conn,
        idempotency_key=params.idempotency_key,
        snapshot=snapshot,
        plan=plan,
        fills=[f.model_dump() for f in params.fills],
        next_state=next_state,
        response=response_body,
    )
    conn.close()

    # save_confirmation 可能返回已存在的缓存响应
    if "confirmed_plan" in saved:
        return saved
    response_body["confirmation"]["snapshot_id"] = saved.get("snapshot_id")
    return response_body


# ============================================================
# V2: 券商截图 OCR 文字解析
# ============================================================

class OcrTextSegmentParams(BaseModel):
    text: str
    name: str = "截图"
    ocr_confidence: Optional[float] = Field(default=None, ge=0, le=100)


class OcrTextStructureParams(BaseModel):
    ocr_texts: list[OcrTextSegmentParams]
    snapshot_date: Optional[date] = None


@app.get("/api/portfolio-snapshot/ocr-config")
def get_portfolio_snapshot_ocr_config():
    """查询 DeepSeek OCR 配置状态（不暴露 API Key）。"""
    from src.snapshot_import.service import ocr_config
    return ocr_config()


@app.post("/api/portfolio-snapshot/parse-text")
def parse_portfolio_snapshot_text(params: OcrTextStructureParams):
    """解析券商截图 OCR 文字为结构化持仓草稿（只读，不写库）。"""
    from src.snapshot_import.service import structure_ocr_texts
    from src.snapshot_import.models import StructureResult
    texts = [seg.text for seg in params.ocr_texts if seg.text.strip()]
    if not texts:
        raise HTTPException(status_code=422, detail="OCR 文字不能为空")
    result = structure_ocr_texts(
        texts=texts,
        snapshot_date=params.snapshot_date.isoformat() if params.snapshot_date else None,
        db_path=DB_PATH,
    )
    return result.to_dict()


# ── GET /api/history ──
@app.get("/api/history")
def get_history(
    index: str = Query("000300"),
    field: str = Query("pe"),
    years: int = Query(5),
):
    if field not in ("pe", "pb"):
        return {"index": index, "field": field, "available": False, "data": []}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    create_tables(conn)

    start_date = date.today() - timedelta(days=years * 365)
    rows = conn.execute(
        f"SELECT trade_date, {field} FROM index_valuation "
        f"WHERE index_code = ? AND {field} IS NOT NULL AND trade_date >= ? "
        f"ORDER BY trade_date",
        (index, start_date.isoformat()),
    ).fetchall()

    conn.close()

    if not rows:
        return {"index": index, "field": field, "available": False, "data": []}

    values = [float(r[field]) for r in rows]
    # 计算 expanding window 分位
    series = pd.Series(values)
    percentile = series.expanding().rank(pct=True).fillna(0.5)

    data = [{
        "date": str(r["trade_date"]),
        "value": round(float(r[field]), 4),
        "percentile": round(float(percentile.iloc[i]), 4),
    } for i, r in enumerate(rows)]

    # 降采样到 ~200 个点
    if len(data) > 300:
        step = len(data) // 200
        data = data[::step]

    return {"index": index, "field": field, "available": True, "data": data}


# ── 生产模式：静态文件 + SPA fallback ──
FRONTEND_DIST = PROJECT_ROOT / "dashboard" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    app.mount("/icon-192.png", StaticFiles(directory=FRONTEND_DIST, html=True), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str = ""):
        """所有非 API 路径返回 index.html（SPA 路由支持）。"""
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"message": "Frontend not built. Run: cd dashboard && npm run build"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
