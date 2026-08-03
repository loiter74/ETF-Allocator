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
import math
import pandas as pd
import numpy as np
from datetime import date
from typing import Dict, Optional, List, Any, Tuple, Mapping
from itertools import product

# ---- config ----
from config.settings import (
    ASSETS, TARGET_BANDS, TRAIN_START, TRAIN_END, TEST_START, TEST_END,
    WINDOW_PE_PERCENTILE_YEARS, WINDOW_MOMENTUM_DAYS,
    EXCLUDE_INDEX_BACKFILL, KECHUANG_TREND_OFF_MULTIPLIER,
    BOND_MIN_PURCHASE, BOND_CASH_YIELD,
    COMMISSION_RATE, MIN_COMMISSION, SLIPPAGE_RATE, TRADE_UNIT_SIZE,
    TARGET_WEIGHTS, REBALANCE_OUTER_UPPER, REBALANCE_INNER_UPPER,
    BACKTEST_MAX_CAGR_LAG, BACKTEST_MIN_PROTECTION_TRIGGERS,
    KECHUANG_SENSITIVITY,
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

# ---- bond accumulator (v1.3) ----
from src.execution.bond_liquidity import BondAccumulator
from src.strategy.kechuang import KechuangProtectionState
from src.strategy.models import PortfolioSnapshot, PositionSnapshot
from src.strategy.planner import (
    apply_confirmed_sells,
    build_trade_plan,
    state_after_confirmed_fills,
)

__all__ = [
    "run_backtest",
    "run_trade_backtest",
    "run_strategy_comparison",
    "run_sensitivity_analysis",
    "compute_metrics",
]

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
            from src.store.normalization import normalize_iso_date
            data[normalize_iso_date(td)] = float(val)
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

    clean = np.array([r for r in monthly_returns
                      if not np.isnan(r) and not np.isinf(r)], dtype=float)
    if len(clean) == 0 or np.any(clean <= -1.0):
        return {"annualized_return": None, "max_drawdown": None,
                "calmar": None, "sharpe": None}

    # External cash flows have already been removed from monthly_returns.
    # Build a unit NAV so every metric uses the same cashflow-aware series.
    # Reuse _nav_from_returns (audit C5: was duplicated inline as cumprod).
    nav = np.array(_nav_from_returns(list(clean)))
    years = len(clean) / 12.0
    ann_ret = float(nav[-1] ** (1.0 / years) - 1.0) if years > 0 else None

    runmax = np.maximum.accumulate(nav)
    draws = nav / runmax - 1.0
    max_dd = float(np.min(draws))

    # Calmar
    if ann_ret is not None and abs(max_dd) > 1e-12:
        calmar = float(ann_ret / abs(max_dd))
    else:
        calmar = None

    # Sharpe (annualized)
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


def _nav_from_returns(monthly_returns: List[float]) -> List[float]:
    """Build an auditable unit-NAV series from cashflow-adjusted returns."""
    nav = [1.0]
    for value in monthly_returns:
        if np.isnan(value) or np.isinf(value):
            continue
        nav.append(nav[-1] * (1.0 + float(value)))
    return nav


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

    # ── bond accumulator (v1.3): 虚拟累积池，解决国债ETF最低买入门槛 ──
    bond_accumulator = BondAccumulator(min_purchase=BOND_MIN_PURCHASE)
    bond_cash_balance = 0.0  # 累积池中未买入的资金（计入总资产但不计入固收持仓）

    for i, d in enumerate(decision_dates):
        # ----- current market value -----
        prices: Dict[str, float]  = {}
        values: Dict[str, float]  = {}

        for name, cfg in ASSETS.items():
            rows = get_available_prices(conn, d, cfg["code"])
            p = float(rows[-1]["close_adj"]) if rows else 0.0
            prices[name] = p
            values[name] = shares[name] * p

        total_assets = sum(values.values()) + bond_cash_balance

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
        # An index factor may exist years before its ETF is listed. A signal is
        # not executable until a point-in-time market price exists.
        scores = {
            name: (score if prices.get(name, 0.0) > 0 else None)
            for name, score in scores.items()
        }

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
        upper_limits = {
            n: (v if v is not None else TARGET_BANDS.get(n, (0.0, 0.30))[1])
            for n, v in upper_limits.items()
        }

        # ---- 5. constraints (buy caps + group caps) ----
        constraints = apply_constraints(current_weights, upper_limits, total_assets)

        # ---- 6. allocate ----
        equity_budget = new_money_per_month * eq_ratio
        bond_budget   = new_money_per_month * bond_ratio

        alloc = allocate(
            opportunity_scores=scores,
            current_weights=current_weights,
            upper_limits=upper_limits,
            total_assets=total_assets,
            equity_budget=equity_budget,
            buy_coefficients=constraints["buy_coefficients"],
        )

        # ---- v1.3: bond accumulator ----
        # 固收应配金额进累积池，逆回购计息，判断是否触发买入
        bond_alloc_from_allocator = alloc.pop("国债ETF", 0)  # 分配层溢出
        total_bond_deposit = bond_budget + bond_alloc_from_allocator
        bond_accumulator.deposit(total_bond_deposit)
        bond_interest = bond_accumulator.accrue_interest(BOND_CASH_YIELD)
        bond_action = bond_accumulator.execute()

        # 只有触发买入时才记录国债ETF持仓
        if bond_action.buy:
            alloc["国债ETF"] = bond_action.amount

        # 累积池余额作为现金计入总资产（不计入固收持仓）
        bond_cash_balance = bond_accumulator.get_status()["balance"]

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
            "factors":         factors,
            "constraints":     constraints,
            "bond_status":     bond_accumulator.get_status(),
            "bond_action":     {"buy": bond_action.buy, "lots": bond_action.lots,
                                "amount": bond_action.amount, "interest": bond_interest},
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
        "monthly_returns": [float(r) for r in monthly_returns],
        "nav_series":      _nav_from_returns(monthly_returns),
        "monthly_results": monthly_records,
    }


# ============================================================
# sell-aware exact-share backtest (v2 candidate)
# ============================================================

def _latest_prices(conn: sqlite3.Connection, decision_date: date) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for name, config in ASSETS.items():
        rows = get_available_prices(conn, decision_date, config["code"])
        result[name] = float(rows[-1]["close_adj"]) if rows else 0.0
    return result


def _portfolio_value(shares: Mapping[str, float], prices: Mapping[str, float], cash: float) -> float:
    return float(cash + sum(shares.get(name, 0.0) * prices.get(name, 0.0) for name in ASSETS))


def _static_exact_month(
    *,
    decision_date: date,
    shares: Dict[str, float],
    average_costs: Dict[str, float],
    prices: Mapping[str, float],
    cash: float,
    new_money: float,
) -> Tuple[float, float, int, List[Dict[str, Any]]]:
    """Static-target plus annual relative-band benchmark with real units/costs."""
    costs = 0.0
    sell_count = 0
    trades: List[Dict[str, Any]] = []
    total_before = _portfolio_value(shares, prices, cash)

    if decision_date.month == 12 and total_before > 0:
        for name, target in TARGET_WEIGHTS.items():
            price = prices.get(name, 0.0)
            if price <= 0:
                continue
            value = shares[name] * price
            if value / total_before <= target * REBALANCE_OUTER_UPPER:
                continue
            target_value = target * REBALANCE_INNER_UPPER * total_before
            unit = int(TRADE_UNIT_SIZE[name])
            sell_shares = int(math.floor(max(0.0, value - target_value) / price / unit) * unit)
            if sell_shares <= 0:
                continue
            execution_price = price * (1.0 - SLIPPAGE_RATE)
            gross = sell_shares * execution_price
            commission = max(MIN_COMMISSION, gross * COMMISSION_RATE)
            cash += gross - commission
            shares[name] -= sell_shares
            costs += commission + sell_shares * price * SLIPPAGE_RATE
            sell_count += 1
            trades.append({"side": "SELL", "asset": name, "shares": sell_shares})

    cash += new_money
    planning_total = _portfolio_value(shares, prices, cash)
    # One aggregated order per asset/month. Charging the minimum commission for
    # every single lot would materially overstate the benchmark's costs.
    candidates = sorted(
        (
            target * planning_total - shares[name] * prices.get(name, 0.0),
            name,
        )
        for name, target in TARGET_WEIGHTS.items()
        if prices.get(name, 0.0) > 0
    )
    for gap, name in reversed(candidates):
        if gap <= 0 or cash <= 0:
            continue
        price = prices[name]
        unit = int(TRADE_UNIT_SIZE[name])
        execution_price = price * (1.0 + SLIPPAGE_RATE)
        shares_to_buy = int(math.floor(min(gap, cash) / (execution_price * unit)) * unit)
        while shares_to_buy > 0:
            gross = shares_to_buy * execution_price
            commission = max(MIN_COMMISSION, gross * COMMISSION_RATE)
            if gross + commission <= cash + 1e-9:
                break
            shares_to_buy -= unit
        if shares_to_buy <= 0:
            continue
        old_shares = shares[name]
        old_cost_value = old_shares * average_costs.get(name, 0.0)
        cash -= gross + commission
        shares[name] += shares_to_buy
        average_costs[name] = (old_cost_value + gross + commission) / shares[name]
        costs += commission + shares_to_buy * price * SLIPPAGE_RATE
        trades.append({"side": "BUY", "asset": name, "shares": shares_to_buy})
    return cash, costs, sell_count, trades


def run_trade_backtest(
    conn: sqlite3.Connection,
    *,
    mode: str = "test",
    variant: str = "new_no_protection",
    new_money_per_month: float = 10_000.0,
    exclude_backfill: Optional[bool] = None,
) -> Dict[str, Any]:
    """Replay the v2 strategy with exact shares, cash, sells and costs.

    ``variant`` is one of ``static_target_annual``, ``new_no_protection`` or
    ``full_protection``.  The full variant deliberately runs K50 protection in
    live simulation while production remains shadow.
    """
    if variant not in {"static_target_annual", "new_no_protection", "full_protection"}:
        raise ValueError(f"未知策略变体: {variant}")
    if exclude_backfill is None:
        exclude_backfill = EXCLUDE_INDEX_BACKFILL

    reset_recovery_tracking()
    reset_persistence()
    d_start = TRAIN_START if mode == "train" else TEST_START
    d_end = TRAIN_END if mode == "train" else TEST_END
    dates = _monthly_dates(d_start, d_end)
    shares: Dict[str, float] = {name: 0.0 for name in ASSETS}
    average_costs: Dict[str, float] = {name: 0.0 for name in ASSETS}
    cash = 0.0
    bond_pool = 0.0
    equity_pending = 0.0
    state = KechuangProtectionState(mode="live" if variant == "full_protection" else "shadow")
    total_invested = 0.0
    total_costs = 0.0
    sell_count = 0
    last_post_value: Optional[float] = None
    monthly_returns: List[float] = []
    portfolio_values: List[float] = []
    monthly_records: List[Dict[str, Any]] = []

    for decision_date in dates:
        prices = _latest_prices(conn, decision_date)
        pre_value = _portfolio_value(shares, prices, cash)
        if last_post_value is not None and last_post_value > 0:
            monthly_returns.append(pre_value / last_post_value - 1.0)
        portfolio_values.append(pre_value)

        if variant == "static_target_annual":
            cash, month_cost, month_sells, trades = _static_exact_month(
                decision_date=decision_date,
                shares=shares,
                average_costs=average_costs,
                prices=prices,
                cash=cash,
                new_money=new_money_per_month,
            )
            total_costs += month_cost
            sell_count += month_sells
            total_invested += new_money_per_month
            last_post_value = _portfolio_value(shares, prices, cash)
            monthly_records.append({
                "date": decision_date.isoformat(),
                "total_assets": pre_value,
                "new_money": new_money_per_month,
                "trades": trades,
                "costs": month_cost,
            })
            continue

        factors = _compute_factors(conn, decision_date, bool(exclude_backfill))
        scores = score_all(factors)
        scores = {
            name: (score if prices.get(name, 0.0) > 0 else None)
            for name, score in scores.items()
        }
        p1, p2 = _thermometer_inputs(conn, decision_date, bool(exclude_backfill))
        thermometer_ratio, _ = equity_ratio(p1, p2)
        vols: Dict[str, Optional[float]] = {}
        for name, config in ASSETS.items():
            rows = get_available_prices(conn, decision_date, config["code"])
            vols[name] = None if name == "国债ETF" else factor_annualized_vol(_build_series(rows, "close_adj"))
        raw_limits = all_effective_limits(vols)
        limits = {
            name: (raw_limits.get(name) if raw_limits.get(name) is not None else TARGET_BANDS[name][1])
            for name in ASSETS
        }
        positions = tuple(
            PositionSnapshot(
                asset=name,
                code=ASSETS[name]["code"],
                shares=shares[name],
                price=prices[name],
                market_value=shares[name] * prices[name],
                average_cost=(average_costs[name] if average_costs[name] > 0 else None),
                is_equity=name != "国债ETF",
            )
            for name in ASSETS
            if shares[name] > 0 and prices[name] > 0
        )
        snapshot = PortfolioSnapshot(
            snapshot_date=decision_date,
            price_date=decision_date,
            new_money=new_money_per_month,
            account_cash=cash,
            bond_pool_cash=bond_pool,
            equity_pending_cash=equity_pending,
            positions=positions,
        )
        protection_mode = "live" if variant == "full_protection" else "shadow"
        trend_on = factors.get("科创50ETF", {}).get("trend_multiplier", 1.0) >= 1.0
        plan = build_trade_plan(
            snapshot,
            opportunity_scores=scores,
            risk_upper_limits=limits,
            thermometer_equity_ratio=thermometer_ratio,
            market_prices=prices,
            kechuang_trend_on=trend_on,
            kechuang_state=state,
            protection_mode=protection_mode,
        )

        month_sells = list(plan.formal_sells)
        if month_sells:
            fills = [
                {
                    "asset": order.asset,
                    "shares": order.shares,
                    "price": order.estimated_price,
                    "commission": order.commission,
                }
                for order in month_sells
            ]
            derived, filled_by_asset = apply_confirmed_sells(snapshot, plan, fills)
            shares = {
                name: (derived.position(name).shares if derived.position(name) else 0.0)
                for name in ASSETS
            }
            cash = derived.account_cash
            state = state_after_confirmed_fills(plan, filled_by_asset)
            sell_count += len(month_sells)
            total_costs += sum(order.commission + order.slippage_cost for order in month_sells)
            plan = build_trade_plan(
                derived,
                opportunity_scores=scores,
                risk_upper_limits=limits,
                thermometer_equity_ratio=thermometer_ratio,
                market_prices=prices,
                kechuang_trend_on=trend_on,
                kechuang_state=state,
                protection_mode=protection_mode,
            )
            snapshot = derived

        # External contribution is credited exactly once after all sell fills.
        cash += new_money_per_month
        for order in plan.buys:
            outflow = -order.cash_effect
            if outflow > cash + 0.01:
                raise AssertionError("回测买单透支现金")
            old_shares = shares.get(order.asset, 0.0)
            old_cost_value = old_shares * average_costs.get(order.asset, 0.0)
            cash -= outflow
            shares[order.asset] = old_shares + order.shares
            average_costs[order.asset] = (
                old_cost_value + order.gross_amount + order.commission
            ) / shares[order.asset]
            total_costs += order.commission + order.slippage_cost
        if plan.cash_ledger:
            # Planner ledger and executed cash must match to cents.
            if abs(cash - plan.cash_ledger.closing_cash) > 0.011:
                raise AssertionError(
                    f"回测现金与计划不一致: actual={cash}, planned={plan.cash_ledger.closing_cash}"
                )
            bond_pool = plan.cash_ledger.bond_pool_after
            equity_pending = plan.cash_ledger.equity_pending_after
        state = KechuangProtectionState.from_mapping(plan.state_patch.get("kechuang"))
        total_invested += new_money_per_month
        last_post_value = _portfolio_value(shares, prices, cash)
        monthly_records.append({
            "date": decision_date.isoformat(),
            "total_assets": pre_value,
            "new_money": new_money_per_month,
            "scores": scores,
            "trade_plan": plan.to_dict(),
            "formal_sell_count": len(month_sells),
            "shadow_sell_count": len(plan.shadow_sells),
            "costs_to_date": total_costs,
            "kechuang_state": state.to_dict(),
        })

    final_prices = _latest_prices(conn, dates[-1]) if dates else {}
    final_value = _portfolio_value(shares, final_prices, cash) if dates else None
    if final_value is not None:
        portfolio_values.append(final_value)
    metrics = compute_metrics(portfolio_values, total_invested, monthly_returns)
    return {
        "mode": mode,
        "variant": variant,
        "date_range": {"start": d_start, "end": d_end},
        "total_invested": round(total_invested, 2),
        "final_value": round(final_value, 2) if final_value is not None else None,
        "metrics": metrics,
        "monthly_returns": [float(value) for value in monthly_returns],
        "nav_series": _nav_from_returns(monthly_returns),
        "monthly_results": monthly_records,
        "execution": {
            "total_costs": round(total_costs, 2),
            "annualized_cost_drag": (
                total_costs / total_invested * 12 / max(1, len(dates))
                if total_invested > 0 and dates else 0.0
            ),
            "sell_count": sell_count,
            "kechuang_independent_triggers": state.independent_triggers,
            "ending_cash": round(cash, 2),
            "ending_bond_pool": round(bond_pool, 2),
            "ending_equity_pending": round(equity_pending, 2),
        },
    }


def run_strategy_comparison(
    conn: sqlite3.Connection,
    *,
    mode: str = "test",
    new_money_per_month: float = 10_000.0,
) -> Dict[str, Any]:
    """Run all four pre-registered comparison groups and evaluate promotion gates."""
    baseline = run_backtest(conn, mode=mode, new_money_per_month=new_money_per_month)
    static = run_trade_backtest(
        conn, mode=mode, variant="static_target_annual", new_money_per_month=new_money_per_month
    )
    no_protection = run_trade_backtest(
        conn, mode=mode, variant="new_no_protection", new_money_per_month=new_money_per_month
    )
    full = run_trade_backtest(
        conn, mode=mode, variant="full_protection", new_money_per_month=new_money_per_month
    )
    variants = {
        "v1_3": baseline,
        "static_target_annual": static,
        "new_no_protection": no_protection,
        "full_protection": full,
    }

    def metric(result: Mapping[str, Any], key: str) -> Optional[float]:
        value = result.get("metrics", {}).get(key)
        return float(value) if value is not None else None

    base_cagr = metric(baseline, "annualized_return")
    full_cagr = metric(full, "annualized_return")
    no_calmar = metric(no_protection, "calmar")
    full_calmar = metric(full, "calmar")
    no_dd = metric(no_protection, "max_drawdown")
    full_dd = metric(full, "max_drawdown")
    triggers = int(full.get("execution", {}).get("kechuang_independent_triggers", 0))
    gates = {
        "cagr_lag_within_2pp": (
            base_cagr is not None and full_cagr is not None
            and full_cagr >= base_cagr - BACKTEST_MAX_CAGR_LAG
        ),
        "calmar_not_below_no_protection": (
            no_calmar is not None and full_calmar is not None and full_calmar >= no_calmar
        ),
        "max_drawdown_not_worse": (
            no_dd is not None and full_dd is not None and full_dd >= no_dd
        ),
        "at_least_three_independent_triggers": triggers >= BACKTEST_MIN_PROTECTION_TRIGGERS,
    }
    return {
        "mode": mode,
        "variants": variants,
        "acceptance": {
            "gates": gates,
            "profit_protection_status": "eligible_for_live" if all(gates.values()) else "shadow",
            "note": "任何单项不满足或独立触发少于3次，科创利润保护继续影子运行。",
        },
    }


def run_sensitivity_analysis(
    conn: sqlite3.Connection,
    *,
    mode: str = "test",
    new_money_per_month: float = 10_000.0,
) -> Dict[str, Any]:
    """Report the pre-registered neighboring grid without selecting a winner."""
    import src.strategy.kechuang as k_module

    original = {
        "KECHUANG_ACTIVATION_RETURN": k_module.KECHUANG_ACTIVATION_RETURN,
        "KECHUANG_DRAWDOWN_TRIGGER": k_module.KECHUANG_DRAWDOWN_TRIGGER,
        "KECHUANG_OFF_MONTHS_EXIT": k_module.KECHUANG_OFF_MONTHS_EXIT,
        "KECHUANG_PARTIAL_SELL_FRACTION": k_module.KECHUANG_PARTIAL_SELL_FRACTION,
    }
    results: List[Dict[str, Any]] = []
    try:
        for activation, drawdown, off_months, fraction in product(
            KECHUANG_SENSITIVITY["activation"],
            KECHUANG_SENSITIVITY["drawdown"],
            KECHUANG_SENSITIVITY["off_months"],
            KECHUANG_SENSITIVITY["sell_fraction"],
        ):
            k_module.KECHUANG_ACTIVATION_RETURN = activation
            k_module.KECHUANG_DRAWDOWN_TRIGGER = drawdown
            k_module.KECHUANG_OFF_MONTHS_EXIT = off_months
            k_module.KECHUANG_PARTIAL_SELL_FRACTION = fraction
            result = run_trade_backtest(
                conn,
                mode=mode,
                variant="full_protection",
                new_money_per_month=new_money_per_month,
            )
            results.append({
                "parameters": {
                    "activation": activation,
                    "drawdown": drawdown,
                    "off_months": off_months,
                    "sell_fraction": fraction,
                },
                "metrics": result["metrics"],
                "execution": result["execution"],
            })
    finally:
        for name, value in original.items():
            setattr(k_module, name, value)
    return {
        "mode": mode,
        "locked_choice": {
            "activation": 0.25,
            "drawdown": 0.12,
            "off_months": 2,
            "sell_fraction": 1.0 / 3.0,
        },
        "selection_performed": False,
        "results": results,
    }
