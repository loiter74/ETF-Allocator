"""
src/backtest/engine.py — Point-in-time monthly backtest engine.

Simulates the full allocation pipeline (流A) across historical data:
  factors → scores → regime → risk → constraints → allocation → execute.

Each decision date only sees data published on or before that date
(point-in-time discipline). At the end it computes:
  - Annualized return (CAGR)
  - Maximum drawdown
  - Calmar ratio (CAGR / |max_drawdown|)
  - Sharpe ratio (annualized, on monthly returns)
"""
import sqlite3
import pandas as pd
import numpy as np
from datetime import date
from typing import Dict, Optional, List, Any, Tuple

# ---- config ----
from config.settings import (
    ASSETS, TRAIN_START, TRAIN_END, TEST_START, TEST_END,
    WINDOW_PE_PERCENTILE_YEARS, WINDOW_MOMENTUM_DAYS,
    EXCLUDE_INDEX_BACKFILL, KECHUANG_TREND_OFF_MULTIPLIER,
)

# ---- point-in-time data ----
from src.store.validator import get_available_valuations, get_available_prices

# ---- factors ----
from src.factors.value import pe_percentile, pb_percentile, expanding_percentile, compute_zscore
from src.factors.dividend import dividend_yield_percentile
from src.factors.momentum import momentum_120d, ma_trend_200d
from src.factors.risk import annualized_volatility as factor_annualized_vol

# ---- pipeline ----
from src.scoring.engine import score_all
from src.regime.thermometer import equity_ratio, reset_persistence
from src.risk.controller import all_effective_limits, reset_recovery_tracking
from src.constraints.portfolio import apply_constraints
from src.allocation.allocator import allocate

__all__ = ["run_backtest", "compute_metrics"]

# ---- constants ----

ALL_MARKET_INDEX = "000985"   # 万得全A → p2 source for the regime thermometer


# ============================================================
# helpers
# ============================================================

def _monthly_dates(start: str, end: str) -> List[date]:
    """Month-end dates in [start, end]."""
    return [d.date() for d in pd.date_range(start, end, freq="ME")]


def _build_series(rows: List[Dict], field: str) -> pd.Series:
    """Turn DB row-list into a sorted pd.Series indexed by trade_date."""
    if not rows:
        return pd.Series(dtype=float)
    data = {}
    for r in rows:
        val = r.get(field)
        td  = r.get("trade_date")
        if val is not None and td is not None:
            data[str(td)] = float(val)
    s = pd.Series(data)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _is_backfill(
    conn: sqlite3.Connection, index_code: str, trade_date: str,
) -> bool:
    """
    True when *trade_date* falls inside the index's backfill window
    (base_date ≤ trade_date < publish_date), meaning the data was
    constructed after the fact and carries a future-information bias.
    """
    row = conn.execute(
        "SELECT base_date, publish_date FROM index_info WHERE index_code = ?",
        (index_code,),
    ).fetchone()
    if not row:
        return False
    base, pub = row["base_date"], row["publish_date"]
    if base and pub:
        return str(base) <= str(trade_date) < str(pub)
    return False


# ============================================================
# factor computation (point-in-time)
# ============================================================

def _compute_factors(
    conn: sqlite3.Connection,
    decision_date: date,
    exclude_backfill: bool,
) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Return {asset_name: {factor_name: value or None}} computed using
    only data visible on *decision_date*.
    """
    factors: Dict[str, Dict[str, Optional[float]]] = {}

    for name, cfg in ASSETS.items():
        if name == "国债ETF":
            factors[name] = {}
            continue

        index_code = cfg["tracking_index"]
        code       = cfg["code"]
        window     = WINDOW_PE_PERCENTILE_YEARS

        # ── fetch point-in-time data ──
        vals = get_available_valuations(conn, decision_date, index_code)
        if exclude_backfill and vals and index_code:
            vals = [v for v in vals
                    if not _is_backfill(conn, index_code, v["trade_date"])]

        prices = get_available_prices(conn, decision_date, code)

        pe_s  = _build_series(vals, "pe")
        pb_s  = _build_series(vals, "pb")
        dy_s  = _build_series(vals, "dividend_yield")
        pr_s  = _build_series(prices, "close_adj")

        f: Dict[str, Optional[float]] = {}

        # ── per-asset logic ──
        if name == "白酒ETF":
            f["pe_percentile"] = pe_percentile(pe_s, window)

        elif name == "银行ETF":
            f["pb_zscore"]       = compute_zscore(pb_s, window)
            f["dividend_zscore"] = compute_zscore(dy_s, window)

        elif name == "红利ETF":
            f["dividend_percentile"]   = dividend_yield_percentile(dy_s, window)

        elif name == "沪深300ETF":
            f["pe_percentile"] = pe_percentile(pe_s, window)

        elif name == "科创50ETF":
            mom      = momentum_120d(pr_s)
            trend_on = ma_trend_200d(pr_s)
            mult     = 1.0 if trend_on else float(KECHUANG_TREND_OFF_MULTIPLIER)
            f["trend_multiplier"] = mult

            if mom is not None:
                clean    = pr_s.dropna()
                min_len  = WINDOW_MOMENTUM_DAYS + 1
                mom_hist: List[float] = []
                for i in range(min_len, len(clean) + 1):
                    m = momentum_120d(clean.iloc[:i])
                    if m is not None:
                        mom_hist.append(m)
                if len(mom_hist) >= 20:
                    f["momentum_percentile"] = expanding_percentile(
                        pd.Series(mom_hist), mom,
                    )
                else:
                    f["momentum_percentile"] = None
            else:
                f["momentum_percentile"] = None

        factors[name] = f

    return factors


# ============================================================
# regime thermometer inputs
# ============================================================

def _thermometer_inputs(
    conn: sqlite3.Connection,
    decision_date: date,
    exclude_backfill: bool,
) -> Tuple[Optional[float], Optional[float]]:
    """p1 = 沪深300 PE分位,  p2 = 全A PB分位."""
    w = WINDOW_PE_PERCENTILE_YEARS

    # p1
    h300 = get_available_valuations(conn, decision_date, "000300")
    if exclude_backfill and h300:
        h300 = [v for v in h300
                if not _is_backfill(conn, "000300", v["trade_date"])]
    p1 = pe_percentile(_build_series(h300, "pe"), w)

    # p2
    allm = get_available_valuations(conn, decision_date, ALL_MARKET_INDEX)
    if exclude_backfill and allm:
        allm = [v for v in allm
                if not _is_backfill(conn, ALL_MARKET_INDEX, v["trade_date"])]
    p2 = pb_percentile(_build_series(allm, "pb"), w)

    return p1, p2


# ============================================================
# metrics
# ============================================================

def compute_metrics(
    portfolio_values: List[float],
    total_invested: float,
    monthly_returns: List[float],
) -> Dict[str, Optional[float]]:
    """
    Compute performance metrics from a backtest run.

    All inputs and outputs are decimal (0.15 = 15 %).

    Returns:
        {"annualized_return", "max_drawdown", "calmar", "sharpe"}
        Each value is a float or None when insufficient data.
    """
    n = len(monthly_returns)
    if n == 0 or total_invested <= 0 or len(portfolio_values) < 2:
        return {"annualized_return": None, "max_drawdown": None,
                "calmar": None, "sharpe": None}

    arr       = np.array(portfolio_values, dtype=float)
    final_val = arr[-1]
    years     = n / 12.0

    # CAGR
    ann_ret = (final_val / total_invested) ** (1.0 / years) - 1.0 if years > 0 else None

    # max drawdown (avoid div-by-zero when starting at 0)
    runmax = np.maximum.accumulate(arr)
    draws  = np.divide(arr, runmax, out=np.ones_like(arr), where=runmax > 0) - 1.0
    max_dd = float(np.min(draws))

    # Calmar
    if ann_ret is not None and abs(max_dd) > 1e-12:
        calmar = float(ann_ret / abs(max_dd))
    else:
        calmar = None

    # Sharpe (annualized)
    clean = np.array([r for r in monthly_returns
                      if not np.isnan(r) and not np.isinf(r)], dtype=float)
    if len(clean) >= 2:
        std = float(clean.std(ddof=1))
        mu  = float(clean.mean())
        sharpe = float(mu / std * np.sqrt(12)) if std > 1e-12 else None
    else:
        sharpe = None

    return {
        "annualized_return": float(ann_ret) if ann_ret is not None else None,
        "max_drawdown":      float(max_dd),
        "calmar":            float(calmar) if calmar is not None else None,
        "sharpe":            float(sharpe) if sharpe is not None else None,
    }


# ============================================================
# main backtest loop
# ============================================================

def run_backtest(
    conn: sqlite3.Connection,
    mode: str = "test",
    new_money_per_month: float = 10000.0,
    exclude_backfill: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Simulate the monthly allocation pipeline over historical data.

    Args:
        conn:
            SQLite connection with ``etf_price`` and ``index_valuation`` tables.
        mode:
            ``"train"`` → 2015–2021;  ``"test"`` → 2022–2025.
        new_money_per_month:
            Fixed cash inflow each decision period.
        exclude_backfill:
            Toggle index-backfill filter.  Defaults to ``config.settings.EXCLUDE_INDEX_BACKFILL``.

    Returns:
        {
            "mode":           str,
            "date_range":     {"start", "end"},
            "total_invested": float,
            "final_value":    float | None,
            "metrics":        {annualized_return, max_drawdown, calmar, sharpe},
            "monthly_results": [
                {date, total_assets, new_money, equity_ratio, bond_ratio,
                 p1, p2, allocations, current_weights, scores},
                ...
            ],
        }
        Metrics are ``None`` when there is insufficient data.
    """
    if exclude_backfill is None:
        exclude_backfill = EXCLUDE_INDEX_BACKFILL

    # ── reset stateful modules ──
    reset_recovery_tracking()
    reset_persistence()

    # ── date range ──
    d_start = TRAIN_START if mode == "train" else TEST_START
    d_end   = TRAIN_END   if mode == "train" else TEST_END
    decision_dates = _monthly_dates(d_start, d_end)

    if not decision_dates:
        return {
            "mode": mode,
            "date_range": {"start": d_start, "end": d_end},
            "total_invested": 0.0,
            "final_value": None,
            "metrics": {"annualized_return": None, "max_drawdown": None,
                        "calmar": None, "sharpe": None},
            "monthly_results": [],
        }

    # ── portfolio state ──
    shares: Dict[str, float]       = {n: 0.0 for n in ASSETS}
    total_invested  = 0.0
    monthly_records: List[Dict]     = []
    portfolio_values: List[float]   = []   # market value *before* investing
    monthly_returns: List[float]    = []
    post_invest_values: List[float] = []   # value *after* investing

    for i, d in enumerate(decision_dates):
        # ----- current market value -----
        prices: Dict[str, float]  = {}
        values: Dict[str, float]  = {}

        for name, cfg in ASSETS.items():
            rows = get_available_prices(conn, d, cfg["code"])
            p = float(rows[-1]["close_adj"]) if rows else 0.0
            prices[name] = p
            values[name] = shares[name] * p

        total_assets = sum(values.values())

        # ----- portfolio snapshots -----
        if i > 0:
            portfolio_values.append(total_assets)
            last_post = post_invest_values[-1] if post_invest_values else 0.0
            monthly_returns.append(
                total_assets / last_post - 1.0 if last_post > 0 else 0.0
            )

        # ----- current weights -----
        if total_assets > 0:
            current_weights = {n: v / total_assets for n, v in values.items()}
        else:
            current_weights = {n: 0.0 for n in ASSETS}

        # ---- 1. factors ----
        factors = _compute_factors(conn, d, exclude_backfill)

        # ---- 2. scores ----
        scores = score_all(factors)

        # ---- 3. regime thermometer ----
        p1, p2 = _thermometer_inputs(conn, d, exclude_backfill)
        eq_ratio, bond_ratio = equity_ratio(p1, p2)

        # ---- 4. risk control (volatility caps) ----
        vols: Dict[str, Optional[float]] = {}
        for name, cfg in ASSETS.items():
            if name == "国债ETF":
                vols[name] = None
                continue
            rows = get_available_prices(conn, d, cfg["code"])
            vols[name] = factor_annualized_vol(_build_series(rows, "close_adj"))

        upper_limits = all_effective_limits(vols)
        upper_limits = {n: (v if v is not None else 0.30) for n, v in upper_limits.items()}

        # ---- 5. constraints (buy caps + group caps) ----
        _ = apply_constraints(current_weights, upper_limits, max(total_assets, 1.0))

        # ---- 6. allocate ----
        equity_budget = new_money_per_month * eq_ratio
        bond_budget   = new_money_per_month * bond_ratio

        alloc = allocate(
            opportunity_scores=scores,
            current_weights=current_weights,
            upper_limits=upper_limits,
            total_assets=max(total_assets, 1.0),
            equity_budget=equity_budget,
        )
        if bond_budget > 0:
            alloc["国债ETF"] = alloc.get("国债ETF", 0) + bond_budget

        # ---- 7. execute (buy shares) ----
        for name, amount in alloc.items():
            if amount <= 0:
                continue
            p = prices.get(name, 0.0)
            if p > 0:
                shares[name] += amount / p

        total_invested += new_money_per_month
        post_invest_values.append(total_assets + new_money_per_month)

        # ---- record ----
        monthly_records.append({
            "date":            d.isoformat(),
            "total_assets":    total_assets,
            "new_money":       new_money_per_month,
            "equity_ratio":    eq_ratio,
            "bond_ratio":      bond_ratio,
            "p1":              p1,
            "p2":              p2,
            "allocations":     alloc,
            "current_weights": current_weights,
            "scores":          {k: v for k, v in scores.items()},
        })

    # ── final portfolio value ──
    if decision_dates and post_invest_values:
        portfolio_values.append(post_invest_values[-1])
    final_value = portfolio_values[-1] if portfolio_values else None

    # ── compute metrics ──
    metrics = compute_metrics(portfolio_values, total_invested, monthly_returns)

    return {
        "mode":            mode,
        "date_range":      {"start": d_start, "end": d_end},
        "total_invested":  round(total_invested, 2),
        "final_value":     round(final_value, 2) if final_value is not None else None,
        "metrics":         metrics,
        "monthly_results": monthly_records,
    }
