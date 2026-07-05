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
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.settings import ASSETS, WINDOW_PE_PERCENTILE_YEARS
from src.store.schema import create_tables
from src.scoring.engine import score_all
from src.regime.thermometer import equity_ratio
from src.risk.controller import all_effective_limits, reset_recovery_tracking
from src.constraints.portfolio import apply_constraints
from src.allocation.allocator import allocate

# v1.3: bond accumulator
from src.execution.bond_liquidity import BondAccumulator

app = FastAPI(title="ETF-Allocator API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DB_PATH = PROJECT_ROOT / "data" / "db" / "etf_data.db"
NEW_MONEY_DEFAULT = 8_000
TOTAL_ASSETS_DEFAULT = 500_000


class ReportParams(BaseModel):
    date: Optional[str] = None
    new_money: float = NEW_MONEY_DEFAULT
    total_assets: float = TOTAL_ASSETS_DEFAULT
    current_weights: Optional[dict[str, float]] = None


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
    all_a_pb_s = load_vals(conn, "000985", "pb")
    if not all_a_pb_s.empty:
        all_a_pb_s = all_a_pb_s[all_a_pb_s.index <= pd.Timestamp(d)]
    p2 = _pb_pct(all_a_pb_s, max_window_years=_WYEARS) if not all_a_pb_s.empty else None

    # 长周期 PE 分位（10年 expanding window）
    from config.settings import WINDOW_PE_PERCENTILE_LONG
    from src.factors.value import pe_percentile
    pe_long_s = load_vals(conn, "000300", "pe")
    if not pe_long_s.empty:
        pe_long_s = pe_long_s[pe_long_s.index <= pd.Timestamp(d)]
    p1_long = pe_percentile(pe_long_s, max_window_years=WINDOW_PE_PERCENTILE_LONG) if not pe_long_s.empty else None
    # 全A PB 长周期
    all_a_pb_long_s = load_vals(conn, "000985", "pb")
    if not all_a_pb_long_s.empty:
        all_a_pb_long_s = all_a_pb_long_s[all_a_pb_long_s.index <= pd.Timestamp(d)]
    p2_long = pe_percentile(all_a_pb_long_s, max_window_years=WINDOW_PE_PERCENTILE_LONG) if not all_a_pb_long_s.empty else None

    eq_ratio, bond_ratio = equity_ratio(p1, p2)

    vols = {n: fac.get("volatility") for n, fac in factors.items()}
    limits = all_effective_limits(vols)
    limits = {n: (v if v is not None else 0.3) for n, v in limits.items()}

    weights = calc_weights(conn, d)
    total = total_assets

    # total=0 → 初始建仓，所有权重归零
    if total <= 0:
        weights = {name: 0.0 for name in weights}

    cons = apply_constraints(weights, limits, max(total, 1))

    # total=0 时用初始建仓模式；>0 时传真实值
    alloc = allocate(scores, weights, limits, total, NEW_MONEY_DEFAULT * eq_ratio, cons["buy_coefficients"])

    # v1.3: bond accumulator
    bond_budget = NEW_MONEY_DEFAULT * bond_ratio
    bond_alloc_overflow = alloc.pop("国债ETF", 0)
    total_bond_deposit = bond_budget + bond_alloc_overflow
    accumulator_path = str(PROJECT_ROOT / "data" / "db" / "bond_accumulator.json")
    bond_accumulator = BondAccumulator.load(accumulator_path)
    bond_accumulator.deposit(total_bond_deposit)
    bond_interest = bond_accumulator.accrue_interest()
    bond_action = bond_accumulator.execute()
    if bond_action.buy:
        alloc["国债ETF"] = bond_action.amount
    bond_status = bond_accumulator.get_status()
    bond_status["deposit_this_month"] = total_bond_deposit
    bond_status["interest_this_month"] = bond_interest
    bond_status["action_buy"] = bond_action.buy
    bond_status["action_lots"] = bond_action.lots
    bond_status["action_amount"] = bond_action.amount
    bond_accumulator.save(accumulator_path)

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
            "allocation": alloc.get(name, 0),
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
        "new_money": NEW_MONEY_DEFAULT,
        "total_assets": total,
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
        "allocations": [
            {
                "asset": a["name"],
                "code": a["code"],
                "amount": a["allocation"],
                "current_weight": a["weight_current"],
                "upper_limit": a["weight_upper"],
                "opportunity_score": a["score"],
                "trigger_reason": a["trigger_reason"],
            }
            for a in assets_out
        ],
        "warnings": [
            f'{a["name"]} 估值数据不足，本月跳过' for a in assets_out
            if a["trigger_reason"] == "数据不足" and a["name"] != "国债ETF"
        ],
        # 红利 ETF 单因子背离检查：股息率极端低估 vs 市场 PE 高估
        "_divergence_check": True,  # 标记前端可展开详情
        "_divergence_note": (
            f'红利ETF仅用股息率分位({int(factors.get("红利ETF", {}).get("dividend_percentile", 0) * 100)}分)，'
            f'未纳入PE/PB价格估值。当前市场PE分位{int(p1 * 100) if p1 else "?"}%处于高位，'
            '单因子"极端低估"需结合价格估值综合判断。'
        ) if factors.get("红利ETF", {}).get("dividend_percentile", 0) > 0.85 and (p1 or 0) > 0.6 else "",
        # 分配占比摘要（供前端画饼图/柱状图）
        "allocation_summary": [
            {
                "asset": a["name"],
                "amount": a["allocation"],
                "percentage": round(a["allocation"] / NEW_MONEY_DEFAULT * 100, 1) if NEW_MONEY_DEFAULT > 0 else 0,
                "factor_group": a["factor_group"],
            }
            for a in assets_out
        ],
        # v1.3: 国债执行状态
        "bond_status": bond_status,
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
    all_a_pb_s = load_vals(conn, "000985", "pb")
    if not all_a_pb_s.empty:
        all_a_pb_s = all_a_pb_s[all_a_pb_s.index <= pd.Timestamp(d)]
    p2 = _pb_pct(all_a_pb_s, max_window_years=_WYEARS) if not all_a_pb_s.empty else None
    eq_ratio, bond_ratio = equity_ratio(p1, p2)

    vols = {n: fac.get("volatility") for n, fac in factors.items()}
    limits = all_effective_limits(vols)
    limits = {n: (v if v is not None else 0.3) for n, v in limits.items()}

    weights = params.current_weights or _midpoint_weights()
    total = max(params.total_assets, 1)
    cons = apply_constraints(weights, limits, total)

    alloc = allocate(scores, weights, limits, total, params.new_money * eq_ratio, cons["buy_coefficients"])

    # v1.3: bond accumulator
    bond_budget_post = params.new_money * bond_ratio
    bond_alloc_overflow_post = alloc.pop("国债ETF", 0)
    total_bond_deposit_post = bond_budget_post + bond_alloc_overflow_post
    accumulator_path_post = str(PROJECT_ROOT / "data" / "db" / "bond_accumulator.json")
    bond_acc_post = BondAccumulator.load(accumulator_path_post)
    bond_acc_post.deposit(total_bond_deposit_post)
    bond_acc_post.accrue_interest()
    bond_action_post = bond_acc_post.execute()
    if bond_action_post.buy:
        alloc["国债ETF"] = bond_action_post.amount
    bond_status_post = bond_acc_post.get_status()
    bond_status_post["action_buy"] = bond_action_post.buy
    bond_status_post["action_lots"] = bond_action_post.lots
    bond_status_post["action_amount"] = bond_action_post.amount

    # 投后仓位计算
    post_weights = {}
    new_total = total + params.new_money
    for name in ASSETS:
        current_val = weights.get(name, 0) * total
        added = alloc.get(name, 0)
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
