"""Single-source monthly buy/sell decision engine.

The planner is deliberately pure: previewing the same snapshot and persisted
state returns the same plan.  Persistence is handled by ``strategy.repository``
only after an explicit confirmation.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from config.settings import (
    ALLOCATION_GAP_WEIGHT,
    ALLOCATION_OPPORTUNITY_WEIGHT,
    ASSETS,
    BOND_MIN_PURCHASE,
    COMMISSION_RATE,
    DEFENSE_HARD_CAP,
    DEFENSE_HARD_FLOOR,
    EQUITY_GATE_LOWER,
    EQUITY_GATE_UPPER,
    GROUP_CAPS,
    HARD_CAP_SELL_TARGET_BUFFER,
    HIGH_OPPORTUNITY_EXTENSION,
    HIGH_OPPORTUNITY_SCORE,
    KECHUANG_PROTECTION_MODE,
    MAX_VOLUNTARY_COST_RATIO,
    MIN_COMMISSION,
    MIN_OPPORTUNITY_SCORE,
    REBALANCE_INNER_LOWER,
    REBALANCE_INNER_UPPER,
    REBALANCE_OUTER_LOWER,
    REBALANCE_OUTER_UPPER,
    SLIPPAGE_RATE,
    TARGET_BANDS,
    TARGET_WEIGHTS,
    TRADE_UNIT_SIZE,
)
from src.strategy.kechuang import (
    KechuangEvaluation,
    KechuangProtectionState,
    apply_confirmed_kechuang_sale,
    evaluate_kechuang,
    kechuang_buy_allowed,
)
from src.strategy.models import (
    CashLedger,
    PortfolioSnapshot,
    PositionSnapshot,
    TradeOrder,
    TradePlan,
)


CORE_MONTHLY_SELL_ASSETS = ("白酒ETF", "银行ETF", "红利ETF", "沪深300ETF")
EQUITY_ASSETS = tuple(name for name in ASSETS if name != "国债ETF")


@dataclass(frozen=True)
class CostModel:
    commission_rate: float = COMMISSION_RATE
    min_commission: float = MIN_COMMISSION
    slippage_rate: float = SLIPPAGE_RATE
    max_voluntary_cost_ratio: float = MAX_VOLUNTARY_COST_RATIO


def strategic_equity_ratio(account_equity_ratio: float, thermometer_ratio: float) -> float:
    """Apply the 80/90 whole-account gate; exact boundaries use thermometer."""
    if account_equity_ratio < EQUITY_GATE_LOWER:
        return 1.0
    if account_equity_ratio > EQUITY_GATE_UPPER:
        return 0.0
    return min(1.0, max(0.0, float(thermometer_ratio)))


def _commission(gross: float, model: CostModel) -> float:
    if gross <= 0:
        return 0.0
    return max(model.min_commission, gross * model.commission_rate)


def _price_for(
    asset: str,
    snapshot: PortfolioSnapshot,
    market_prices: Mapping[str, float],
) -> float:
    position = snapshot.position(asset)
    if asset in market_prices and float(market_prices[asset]) > 0:
        return float(market_prices[asset])
    return position.price if position is not None else 0.0


def _rounded_shares(requested: float, asset: str, maximum: Optional[float] = None) -> int:
    unit = int(TRADE_UNIT_SIZE.get(asset, 1))
    capped = max(0.0, requested)
    if maximum is not None:
        capped = min(capped, max(0.0, maximum))
    return int(math.floor((capped + 1e-9) / unit) * unit)


def _sell_order(
    *,
    asset: str,
    requested_shares: float,
    position: PositionSnapshot,
    reason_codes: Sequence[str],
    mandatory: bool,
    shadow: bool,
    model: CostModel,
) -> Optional[TradeOrder]:
    shares = _rounded_shares(requested_shares, asset, position.shares)
    if shares <= 0 or position.price <= 0:
        return None
    reference_gross = shares * position.price
    estimated_price = position.price * (1.0 - model.slippage_rate)
    gross = shares * estimated_price
    commission = _commission(gross, model)
    slippage = reference_gross - gross
    if (
        not mandatory
        and reference_gross > 0
        and (commission + slippage) / reference_gross > model.max_voluntary_cost_ratio
    ):
        return None
    return TradeOrder(
        side="SELL",
        asset=asset,
        code=position.code,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        shares=shares,
        reference_price=position.price,
        estimated_price=estimated_price,
        gross_amount=gross,
        commission=commission,
        slippage_cost=slippage,
        cash_effect=gross - commission,
        mandatory=mandatory,
        shadow=shadow,
    )


def _buy_order(
    *,
    asset: str,
    cash_budget: float,
    price: float,
    reason_codes: Sequence[str],
    stages: Sequence[str],
    stage_breakdown: Mapping[str, float],
    mandatory: bool,
    model: CostModel,
) -> Optional[TradeOrder]:
    if cash_budget <= 0 or price <= 0:
        return None
    unit = int(TRADE_UNIT_SIZE.get(asset, 1))
    estimated_price = price * (1.0 + model.slippage_rate)
    shares = int(math.floor(cash_budget / (estimated_price * unit)) * unit)
    while shares > 0:
        gross = shares * estimated_price
        commission = _commission(gross, model)
        if gross + commission <= cash_budget + 1e-9:
            break
        shares -= unit
    if shares <= 0:
        return None
    reference_gross = shares * price
    slippage = gross - reference_gross
    if (
        not mandatory
        and reference_gross > 0
        and (commission + slippage) / reference_gross > model.max_voluntary_cost_ratio
    ):
        return None
    return TradeOrder(
        side="BUY",
        asset=asset,
        code=ASSETS[asset]["code"],
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        shares=shares,
        reference_price=price,
        estimated_price=estimated_price,
        gross_amount=gross,
        commission=commission,
        slippage_cost=slippage,
        cash_effect=-(gross + commission),
        mandatory=mandatory,
        allocation_stages=tuple(dict.fromkeys(stages)),
        stage_breakdown=dict(stage_breakdown),
    )


def _exposure(
    snapshot: PortfolioSnapshot,
    *,
    formal_sells: Sequence[TradeOrder] = (),
    buys: Sequence[TradeOrder] = (),
    closing_cash: Optional[float] = None,
    bond_pool_after: Optional[float] = None,
) -> Dict[str, Any]:
    managed_values = {name: 0.0 for name in ASSETS}
    unknown_value = 0.0
    unknown_equity = 0.0
    for position in snapshot.positions:
        if position.managed:
            managed_values[position.asset] += position.value
        else:
            unknown_value += position.value
            if position.equity_exposure:
                unknown_equity += position.value

    for order in formal_sells:
        managed_values[order.asset] = max(
            0.0,
            managed_values.get(order.asset, 0.0) - order.shares * order.reference_price,
        )
    for order in buys:
        managed_values[order.asset] = managed_values.get(order.asset, 0.0) + order.shares * order.reference_price

    pool = snapshot.bond_pool_cash if bond_pool_after is None else bond_pool_after
    managed_values["国债ETF"] += pool + snapshot.reverse_repo_cash
    cash = snapshot.account_cash if closing_cash is None else closing_cash
    managed_total = sum(managed_values.values()) + max(0.0, cash - pool)
    whole_total = managed_total + unknown_value
    weights = {
        name: (value / managed_total if managed_total > 0 else 0.0)
        for name, value in managed_values.items()
    }
    groups = {
        group: sum(
            weights.get(name, 0.0)
            for name, config in ASSETS.items()
            if config["factor_group"] == group
        )
        for group in {config["factor_group"] for config in ASSETS.values()}
    }
    managed_equity = sum(managed_values[name] for name in EQUITY_ASSETS)
    account_equity = managed_equity + unknown_equity
    defense = managed_values["国债ETF"]
    return {
        "total_assets": round(whole_total, 2),
        "managed_total": round(managed_total, 2),
        "managed_weights": {name: round(weight, 8) for name, weight in weights.items()},
        "group_weights": {name: round(weight, 8) for name, weight in groups.items()},
        "account_equity_ratio": round(account_equity / whole_total, 8) if whole_total > 0 else 0.0,
        "defense_ratio": round(defense / whole_total, 8) if whole_total > 0 else 0.0,
        "unknown_value": round(unknown_value, 2),
    }


def _allocate_weighted(
    *,
    remaining: float,
    bases: Mapping[str, float],
    limits: Mapping[str, float],
    allocations: Dict[str, float],
    capacity,
) -> float:
    active = {name for name, basis in bases.items() if basis > 0 and limits.get(name, 0.0) > 1e-8}
    for _ in range(30):
        if remaining <= 0.005 or not active:
            break
        total_basis = sum(bases[name] for name in active)
        if total_basis <= 0:
            break
        before = remaining
        increments: Dict[str, float] = {}
        for name in active:
            proposed = before * bases[name] / total_basis
            stage_left = max(0.0, limits[name] - allocations.get(name, 0.0))
            increments[name] = min(proposed, stage_left, max(0.0, capacity(name)))
        allocated_now = sum(increments.values())
        if allocated_now <= 0.005:
            break
        for name, amount in increments.items():
            allocations[name] = allocations.get(name, 0.0) + amount
        remaining -= allocated_now
        active = {
            name for name in active
            if limits[name] - allocations.get(name, 0.0) > 0.005 and capacity(name) > 0.005
        }
        # If every active asset accepted its full pro-rata amount, budget is exhausted.
        if abs(before - allocated_now) <= 0.005:
            break
    return max(0.0, remaining)


def _equity_allocations(
    *,
    snapshot: PortfolioSnapshot,
    budget: float,
    scores: Mapping[str, Optional[float]],
    risk_upper_limits: Mapping[str, float],
    market_prices: Mapping[str, float],
    kechuang_state: KechuangProtectionState,
    kechuang_trend_on: bool,
) -> Tuple[Dict[str, float], Dict[str, set[str]], Dict[str, Dict[str, float]], float, list[str]]:
    planning_total = snapshot.managed_total + snapshot.new_money
    if planning_total <= 0 or budget <= 0:
        return {}, {}, {}, max(0.0, budget), []

    values = snapshot.managed_values()
    allocations: Dict[str, float] = {}
    stages: Dict[str, set[str]] = {}
    # stage_breakdown[asset][stage] = 该阶段给此资产分配的金额（用于 TradeOrder 可追溯）
    stage_breakdown: Dict[str, Dict[str, float]] = {}
    warnings: list[str] = []

    eligible: list[str] = []
    for asset in EQUITY_ASSETS:
        score = scores.get(asset)
        price = _price_for(asset, snapshot, market_prices)
        if score is None or score < MIN_OPPORTUNITY_SCORE or price <= 0:
            continue
        if asset == "科创50ETF" and not kechuang_buy_allowed(
            observation_date=snapshot.snapshot_date,
            state=kechuang_state,
            trend_on=kechuang_trend_on,
            opportunity_score=score,
            current_weight=(values[asset] / planning_total),
        ):
            warnings.append("科创50处于利润保护回补冷静期或尚未满足连续趋势条件")
            continue
        eligible.append(asset)

    def asset_capacity(asset: str, phase_fraction: float) -> float:
        strategic_upper = TARGET_BANDS[asset][1]
        risk_upper = risk_upper_limits.get(asset, strategic_upper)
        fraction = min(phase_fraction, strategic_upper, risk_upper)
        individual = fraction * planning_total - values[asset] - allocations.get(asset, 0.0)
        group = ASSETS[asset]["factor_group"]
        group_cap = GROUP_CAPS.get(group)
        if group_cap is None:
            return max(0.0, individual)
        group_current = sum(
            values[name] + allocations.get(name, 0.0)
            for name in ASSETS
            if ASSETS[name]["factor_group"] == group
        )
        group_remaining = group_cap * planning_total - group_current
        return max(0.0, min(individual, group_remaining))

    remaining = budget

    # 1. Repair the strategic lower band (or the annual inner lower band).
    lower_limits: Dict[str, float] = {}
    lower_bases: Dict[str, float] = {}
    for asset in eligible:
        lower_fraction = TARGET_BANDS[asset][0]
        weight = values[asset] / planning_total
        if snapshot.snapshot_date.month == 12 and weight < TARGET_WEIGHTS[asset] * REBALANCE_OUTER_LOWER:
            lower_fraction = max(lower_fraction, TARGET_WEIGHTS[asset] * REBALANCE_INNER_LOWER)
        gap = max(0.0, lower_fraction * planning_total - values[asset])
        if gap > 0:
            lower_limits[asset] = gap
            lower_bases[asset] = gap
            stages.setdefault(asset, set()).add("LOWER_BAND_REPAIR")
    _before = dict(allocations)
    remaining = _allocate_weighted(
        remaining=remaining,
        bases=lower_bases,
        limits=lower_limits,
        allocations=allocations,
        capacity=lambda name: asset_capacity(name, TARGET_BANDS[name][0] if snapshot.snapshot_date.month != 12 else max(TARGET_BANDS[name][0], TARGET_WEIGHTS[name] * REBALANCE_INNER_LOWER)),
    )
    for _asset, _val in allocations.items():
        _delta = _val - _before.get(_asset, 0.0)
        if _delta > 0.005:
            stage_breakdown.setdefault(_asset, {})["LOWER_BAND_REPAIR"] = _delta

    # 2. Fill target gaps using relative target gap + opportunity score.
    target_limits: Dict[str, float] = {}
    raw_gaps: Dict[str, float] = {}
    for asset in eligible:
        target_gap = max(
            0.0,
            TARGET_WEIGHTS[asset] * planning_total - values[asset] - allocations.get(asset, 0.0),
        )
        if target_gap > 0:
            target_limits[asset] = allocations.get(asset, 0.0) + target_gap
            raw_gaps[asset] = target_gap
            stages.setdefault(asset, set()).add("TARGET_FILL")
    max_gap = max(raw_gaps.values(), default=0.0)
    target_bases = {
        asset: (
            ALLOCATION_GAP_WEIGHT * (gap / max_gap if max_gap > 0 else 0.0)
            + ALLOCATION_OPPORTUNITY_WEIGHT * float(scores[asset])
        )
        for asset, gap in raw_gaps.items()
    }
    _before = dict(allocations)
    remaining = _allocate_weighted(
        remaining=remaining,
        bases=target_bases,
        limits=target_limits,
        allocations=allocations,
        capacity=lambda name: asset_capacity(name, TARGET_WEIGHTS[name]),
    )
    for _asset, _val in allocations.items():
        _delta = _val - _before.get(_asset, 0.0)
        if _delta > 0.005:
            stage_breakdown.setdefault(_asset, {})["TARGET_FILL"] = _delta

    # 3. Only very high opportunity assets may extend 2pp over target.
    extension_limits: Dict[str, float] = {}
    extension_bases: Dict[str, float] = {}
    for asset in eligible:
        score = float(scores[asset])
        if score < HIGH_OPPORTUNITY_SCORE:
            continue
        limit_fraction = min(
            TARGET_WEIGHTS[asset] + HIGH_OPPORTUNITY_EXTENSION,
            TARGET_BANDS[asset][1],
            risk_upper_limits.get(asset, TARGET_BANDS[asset][1]),
        )
        gap = max(
            0.0,
            limit_fraction * planning_total - values[asset] - allocations.get(asset, 0.0),
        )
        if gap > 0:
            extension_limits[asset] = allocations.get(asset, 0.0) + gap
            extension_bases[asset] = score
            stages.setdefault(asset, set()).add("HIGH_OPPORTUNITY_EXTENSION")
    _before = dict(allocations)
    remaining = _allocate_weighted(
        remaining=remaining,
        bases=extension_bases,
        limits=extension_limits,
        allocations=allocations,
        capacity=lambda name: asset_capacity(name, TARGET_WEIGHTS[name] + HIGH_OPPORTUNITY_EXTENSION),
    )
    for _asset, _val in allocations.items():
        _delta = _val - _before.get(_asset, 0.0)
        if _delta > 0.005:
            stage_breakdown.setdefault(_asset, {})["HIGH_OPPORTUNITY_EXTENSION"] = _delta
    return allocations, stages, stage_breakdown, remaining, warnings


def _plan_id(
    snapshot: PortfolioSnapshot,
    phase: str,
    formal_sells: Sequence[TradeOrder],
    shadow_sells: Sequence[TradeOrder],
    buys: Sequence[TradeOrder],
    state_patch: Mapping[str, Any],
) -> str:
    payload = {
        "snapshot": snapshot.to_dict(),
        "phase": phase,
        "formal_sells": [order.to_dict() for order in formal_sells],
        "shadow_sells": [order.to_dict() for order in shadow_sells],
        "buys": [order.to_dict() for order in buys],
        "state_patch": state_patch,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def build_trade_plan(
    snapshot: PortfolioSnapshot,
    *,
    opportunity_scores: Mapping[str, Optional[float]],
    risk_upper_limits: Optional[Mapping[str, float]] = None,
    thermometer_equity_ratio: float = 1.0,
    market_prices: Optional[Mapping[str, float]] = None,
    kechuang_trend_on: bool = True,
    kechuang_state: Optional[KechuangProtectionState | Mapping[str, Any]] = None,
    protection_mode: str = KECHUANG_PROTECTION_MODE,
    allow_sells: bool = True,
    cost_model: Optional[CostModel] = None,
) -> TradePlan:
    """Return a deterministic plan; never mutate persistence or the snapshot."""
    model = cost_model or CostModel()
    prices = dict(market_prices or {})
    limits = dict(risk_upper_limits or {name: band[1] for name, band in TARGET_BANDS.items()})
    state = (
        kechuang_state
        if isinstance(kechuang_state, KechuangProtectionState)
        else KechuangProtectionState.from_mapping(kechuang_state)
    )
    state = replace(state, mode=protection_mode)
    managed_total = snapshot.managed_total
    weights = snapshot.managed_weights()
    warnings = list(snapshot.warnings)

    # A defense overage first releases unexecuted tagged pool cash to equity-pending cash.
    pool_release = min(
        snapshot.bond_pool_cash,
        max(0.0, snapshot.defense_value - DEFENSE_HARD_CAP * snapshot.total_assets),
    )
    pool_after_release = snapshot.bond_pool_cash - pool_release
    pending_after_release = snapshot.equity_pending_cash + pool_release
    if pool_release > 0:
        warnings.append(f"国债累积池超额 {pool_release:.2f} 元重新标记为权益待投现金")

    # K50 protection is evaluated even in shadow mode so the report can show it.
    k_position = snapshot.position("科创50ETF")
    k_eval = (
        KechuangEvaluation(next_state=state)
        if snapshot.legacy_allocation_only
        else evaluate_kechuang(
            observation_date=snapshot.snapshot_date,
            position=k_position,
            trend_on=kechuang_trend_on,
            opportunity_score=opportunity_scores.get("科创50ETF"),
            managed_total=managed_total,
            state=state,
        )
    )
    state_patch: Dict[str, Any] = {
        "kechuang": k_eval.next_state.to_dict(),
        "observation": {
            "profit_return": k_eval.profit_return,
            "drawdown_from_high": k_eval.drawdown_from_high,
            "activated_this_month": k_eval.activated_this_month,
        },
    }

    formal_sells: list[TradeOrder] = []
    shadow_sells: list[TradeOrder] = []
    sell_targets: Dict[str, Dict[str, Any]] = {}

    if allow_sells and not snapshot.legacy_allocation_only and managed_total > 0:
        # Monthly strategic hard caps: dynamic risk limits never enter this test.
        for asset in CORE_MONTHLY_SELL_ASSETS:
            if weights.get(asset, 0.0) > TARGET_BANDS[asset][1] + 1e-12:
                sell_targets[asset] = {
                    "target": TARGET_WEIGHTS[asset] + HARD_CAP_SELL_TARGET_BUFFER,
                    "reasons": ["STRATEGIC_HARD_CAP"],
                    "mandatory": True,
                }

        # Annual outer/inner relative bands. K50 protection has priority.
        if snapshot.snapshot_date.month == 12:
            for asset in EQUITY_ASSETS:
                if asset == "科创50ETF" and k_eval.reason_code:
                    continue
                if weights.get(asset, 0.0) > TARGET_WEIGHTS[asset] * REBALANCE_OUTER_UPPER:
                    target = TARGET_WEIGHTS[asset] * REBALANCE_INNER_UPPER
                    existing = sell_targets.get(asset)
                    if existing:
                        existing["target"] = min(existing["target"], target)
                        existing["reasons"].append("ANNUAL_SOFT_BAND")
                    else:
                        sell_targets[asset] = {
                            "target": target,
                            "reasons": ["ANNUAL_SOFT_BAND"],
                            "mandatory": False,
                        }

        for asset, request in sell_targets.items():
            position = snapshot.position(asset)
            if position is None or position.price <= 0:
                warnings.append(f"{asset}命中卖出规则但缺少可执行份额/价格")
                continue
            desired_value = request["target"] * managed_total
            requested_shares = max(0.0, position.value - desired_value) / position.price
            order = _sell_order(
                asset=asset,
                requested_shares=requested_shares,
                position=position,
                reason_codes=request["reasons"],
                mandatory=bool(request["mandatory"]),
                shadow=False,
                model=model,
            )
            if order:
                formal_sells.append(order)
            else:
                warnings.append(f"{asset}卖出取整后不足交易单位或自愿交易成本过高，延后执行")

        # Bond annual exception after releasing tagged pool overage.
        bond_position = snapshot.position("国债ETF")
        if snapshot.snapshot_date.month == 12 and bond_position and bond_position.price > 0:
            unit = int(TRADE_UNIT_SIZE["国债ETF"])
            held_lots = int(bond_position.shares // unit)
            defense_after_release = snapshot.defense_value - pool_release
            if held_lots > 1 and defense_after_release > TARGET_WEIGHTS["国债ETF"] * REBALANCE_OUTER_UPPER * managed_total:
                target_value = TARGET_WEIGHTS["国债ETF"] * REBALANCE_INNER_UPPER * managed_total
                desired_lots = int(math.ceil(max(0.0, defense_after_release - target_value) / (bond_position.price * unit)))
                max_lots = int(math.floor(max(0.0, defense_after_release - DEFENSE_HARD_FLOOR * managed_total) / (bond_position.price * unit)))
                lots = min(desired_lots, max_lots, held_lots)
                order = _sell_order(
                    asset="国债ETF",
                    requested_shares=lots * unit,
                    position=bond_position,
                    reason_codes=("BOND_ANNUAL_SOFT_BAND",),
                    mandatory=False,
                    shadow=False,
                    model=model,
                )
                if order:
                    formal_sells.append(order)
            elif held_lots <= 1 and defense_after_release > DEFENSE_HARD_CAP * snapshot.total_assets:
                warnings.append("国债仅一手：不卖出，通过新增权益资金稀释")

    elif snapshot.legacy_allocation_only:
        warnings.append("兼容仅分配模式：缺少真实份额/成本，所有卖出能力已禁用")

    if k_eval.reason_code and k_position is not None:
        k_order = _sell_order(
            asset="科创50ETF",
            requested_shares=k_eval.desired_sell_shares,
            position=k_position,
            reason_codes=(k_eval.reason_code,),
            mandatory=True,
            shadow=protection_mode != "live",
            model=model,
        )
        if k_order is None:
            warnings.append("科创50利润保护已触发，但可卖份额不足一个交易单位，保留待触发状态")
        elif protection_mode == "live" and allow_sells and not snapshot.legacy_allocation_only:
            formal_sells.append(k_order)
        else:
            shadow_sells.append(k_order)

    formal_sells.sort(key=lambda order: order.asset)
    shadow_sells.sort(key=lambda order: order.asset)

    # "before" must reflect the broker snapshot exactly; pool reclassification
    # is an action and therefore appears only in the ledger/after exposure.
    before = _exposure(snapshot)
    sell_net = sum(order.cash_effect for order in formal_sells)
    sell_commission = sum(order.commission for order in formal_sells)
    sell_slippage = sum(order.slippage_cost for order in formal_sells)

    # A formal sell creates a strict two-stage plan: actual fills must be supplied.
    if formal_sells:
        closing_cash = snapshot.account_cash + snapshot.new_money + sell_net
        ledger = CashLedger(
            opening_cash=snapshot.account_cash,
            new_money=snapshot.new_money,
            sell_net_proceeds=sell_net,
            buy_cash_outflow=0.0,
            closing_cash=closing_cash,
            bond_pool_before=snapshot.bond_pool_cash,
            bond_pool_deposit=0.0,
            bond_pool_released=pool_release,
            bond_pool_after=pool_after_release,
            equity_pending_before=snapshot.equity_pending_cash,
            equity_pending_after=pending_after_release,
            free_cash_after=max(0.0, closing_cash - pool_after_release - pending_after_release),
            total_commission=sell_commission,
            total_slippage=sell_slippage,
        )
        after = _exposure(
            snapshot,
            formal_sells=formal_sells,
            closing_cash=closing_cash,
            bond_pool_after=pool_after_release,
        )
        phase = "sell_preview"
        plan_id = _plan_id(snapshot, phase, formal_sells, shadow_sells, (), state_patch)
        return TradePlan(
            plan_id=plan_id,
            snapshot_date=snapshot.snapshot_date,
            phase=phase,
            formal_sells=tuple(formal_sells),
            shadow_sells=tuple(shadow_sells),
            warnings=tuple(warnings),
            before=before,
            after=after,
            cash_ledger=ledger,
            state_patch=state_patch,
            pending_buy_recalculation=True,
            legacy_allocation_only=snapshot.legacy_allocation_only,
        )

    # No formal sale: classify this month's new money and any confirmed sale proceeds.
    gate_ratio = strategic_equity_ratio(snapshot.account_equity_ratio, thermometer_equity_ratio)
    equity_budget = snapshot.new_money * gate_ratio + pending_after_release
    defense_budget_requested = snapshot.new_money * (1.0 - gate_ratio)
    if snapshot.confirmed_sell_proceeds > 0:
        if snapshot.account_equity_ratio <= EQUITY_GATE_UPPER:
            equity_budget += snapshot.confirmed_sell_proceeds
        else:
            defense_budget_requested += snapshot.confirmed_sell_proceeds

    projected_whole_total = snapshot.total_assets + snapshot.new_money
    defense_after_release = snapshot.defense_value - pool_release
    defense_capacity = max(0.0, DEFENSE_HARD_CAP * projected_whole_total - defense_after_release)
    defense_deposit = min(defense_budget_requested, defense_capacity)
    defense_overflow = max(0.0, defense_budget_requested - defense_deposit)
    # Overflow remains tagged equity cash; it does not bypass a 0% equity gate this month.
    pending_overflow = defense_overflow

    effective_snapshot = replace(
        snapshot,
        bond_pool_cash=pool_after_release,
        equity_pending_cash=pending_after_release,
    )
    allocations, stages, stage_breakdown, allocation_remaining, allocation_warnings = _equity_allocations(
        snapshot=effective_snapshot,
        budget=equity_budget,
        scores=opportunity_scores,
        risk_upper_limits=limits,
        market_prices=prices,
        kechuang_state=k_eval.next_state,
        kechuang_trend_on=kechuang_trend_on,
    )
    warnings.extend(allocation_warnings)

    buys: list[TradeOrder] = []
    allocated_cash_actual = 0.0
    for asset, cash_budget in sorted(allocations.items(), key=lambda item: item[0]):
        price = _price_for(asset, snapshot, prices)
        order = _buy_order(
            asset=asset,
            cash_budget=cash_budget,
            price=price,
            reason_codes=tuple(sorted(stages.get(asset, {"TARGET_FILL"}))),
            stages=tuple(sorted(stages.get(asset, ()))),
            stage_breakdown=stage_breakdown.get(asset, {}),
            mandatory=False,
            model=model,
        )
        if order:
            buys.append(order)
            allocated_cash_actual += -order.cash_effect
        elif cash_budget > 0.005:
            warnings.append(f"{asset}预算 {cash_budget:.2f} 元不足交易单位或成本占比过高，留作权益待投现金")

    # Defense allocation is a cash marker first; when the pool reaches the
    # executable threshold, a whole-lot bond order converts tagged cash to ETF.
    projected_pool = pool_after_release + defense_deposit
    bond_buy_outflow = 0.0
    bond_price = _price_for("国债ETF", snapshot, prices)
    if projected_pool + 1e-9 >= BOND_MIN_PURCHASE and bond_price > 0:
        bond_order = _buy_order(
            asset="国债ETF",
            cash_budget=projected_pool,
            price=bond_price,
            reason_codes=("BOND_POOL_EXECUTION",),
            stages=("DEFENSE_BUCKET",),
            stage_breakdown={"BOND_POOL_EXECUTION": projected_pool},
            mandatory=True,
            model=model,
        )
        if bond_order:
            buys.append(bond_order)
            bond_buy_outflow = -bond_order.cash_effect
    bond_pool_after = max(0.0, projected_pool - bond_buy_outflow)

    buy_outflow = sum(-order.cash_effect for order in buys)
    closing_cash = snapshot.account_cash + snapshot.new_money - buy_outflow
    equity_pending_after = max(0.0, equity_budget - allocated_cash_actual) + pending_overflow
    marked_after = bond_pool_after + equity_pending_after
    if marked_after > closing_cash + 0.01:
        # Floating point and minimum commissions can only reduce the available
        # pending marker; cash itself remains authoritative.
        equity_pending_after = max(0.0, closing_cash - bond_pool_after)
        warnings.append("交易成本挤占部分待投资金，已按账户现金下调权益待投标记")
    free_cash_after = max(0.0, closing_cash - bond_pool_after - equity_pending_after)

    total_commission = sum(order.commission for order in buys)
    total_slippage = sum(order.slippage_cost for order in buys)
    ledger = CashLedger(
        opening_cash=snapshot.account_cash,
        new_money=snapshot.new_money,
        sell_net_proceeds=0.0,
        buy_cash_outflow=buy_outflow,
        closing_cash=closing_cash,
        bond_pool_before=snapshot.bond_pool_cash,
        bond_pool_deposit=defense_deposit,
        bond_pool_released=pool_release,
        bond_pool_after=bond_pool_after,
        equity_pending_before=snapshot.equity_pending_cash,
        equity_pending_after=equity_pending_after,
        free_cash_after=free_cash_after,
        total_commission=total_commission,
        total_slippage=total_slippage,
    )
    after = _exposure(
        snapshot,
        buys=buys,
        closing_cash=closing_cash,
        bond_pool_after=bond_pool_after,
    )
    state_patch["allocation"] = {
        "gate_equity_ratio": gate_ratio,
        "thermometer_equity_ratio": thermometer_equity_ratio,
        "defense_budget_requested": defense_budget_requested,
        "defense_budget_accepted": defense_deposit,
        "unrounded_equity_remaining": allocation_remaining,
    }
    phase = "complete"
    plan_id = _plan_id(snapshot, phase, (), shadow_sells, buys, state_patch)
    return TradePlan(
        plan_id=plan_id,
        snapshot_date=snapshot.snapshot_date,
        phase=phase,
        shadow_sells=tuple(shadow_sells),
        buys=tuple(buys),
        warnings=tuple(warnings),
        before=before,
        after=after,
        cash_ledger=ledger,
        state_patch=state_patch,
        pending_buy_recalculation=False,
        legacy_allocation_only=snapshot.legacy_allocation_only,
    )


def apply_confirmed_sells(
    snapshot: PortfolioSnapshot,
    plan: TradePlan,
    fills: Iterable[Mapping[str, Any]],
    *,
    cost_model: Optional[CostModel] = None,
) -> Tuple[PortfolioSnapshot, Dict[str, float]]:
    """Apply real sell fills to a derived snapshot for the second planning phase."""
    model = cost_model or CostModel()
    expected = {order.asset: order for order in plan.formal_sells}
    positions = {position.asset: position for position in snapshot.positions}
    total_net = 0.0
    filled_by_asset: Dict[str, float] = {}

    for fill in fills:
        asset = str(fill["asset"])
        if asset not in expected:
            raise ValueError(f"成交不属于计划正式卖单: {asset}")
        order = expected[asset]
        shares = float(fill["shares"])
        price = float(fill["price"])
        if shares <= 0 or price <= 0:
            raise ValueError(f"{asset}成交份额和价格必须大于0")
        if shares > order.shares + 1e-9:
            raise ValueError(f"{asset}成交份额超过计划卖出份额")
        position = positions.get(asset)
        if position is None or shares > position.shares + 1e-9:
            raise ValueError(f"{asset}成交份额超过持仓")
        gross = shares * price
        commission = float(fill.get("commission", _commission(gross, model)))
        if commission < 0 or commission >= gross:
            raise ValueError(f"{asset}成交佣金无效")
        total_net += gross - commission
        filled_by_asset[asset] = filled_by_asset.get(asset, 0.0) + shares
        positions[asset] = position.with_shares(position.shares - shares)

    if not filled_by_asset:
        raise ValueError("至少需要一条真实卖出成交")

    ordered_positions = tuple(positions[position.asset] for position in snapshot.positions)
    derived = replace(
        snapshot,
        positions=ordered_positions,
        account_cash=snapshot.account_cash + total_net,
        confirmed_sell_proceeds=total_net,
    )
    return derived, filled_by_asset


def state_after_confirmed_fills(
    plan: TradePlan,
    filled_by_asset: Mapping[str, float],
) -> KechuangProtectionState:
    state = KechuangProtectionState.from_mapping(plan.state_patch.get("kechuang"))
    return apply_confirmed_kechuang_sale(
        state,
        sale_date=plan.snapshot_date,
        filled_shares=float(filled_by_asset.get("科创50ETF", 0.0)),
    )
