"""Pre-registered monthly Kechuang 50 profit-protection state machine."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from typing import Any, Mapping, Optional

from config.settings import (
    KECHUANG_ACTIVATION_RETURN,
    KECHUANG_COOLDOWN_FULL_MONTHS,
    KECHUANG_DRAWDOWN_TRIGGER,
    KECHUANG_EXIT_TARGET,
    KECHUANG_OFF_MONTHS_EXIT,
    KECHUANG_PARTIAL_SELL_FRACTION,
    KECHUANG_REENTRY_ON_MONTHS,
    KECHUANG_REENTRY_SCORE,
    TARGET_WEIGHTS,
)
from src.strategy.models import PositionSnapshot


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def month_distance(later: date, earlier_month: str) -> int:
    year, month = (int(part) for part in earlier_month.split("-"))
    return (later.year - year) * 12 + later.month - month


@dataclass(frozen=True)
class KechuangProtectionState:
    mode: str = "shadow"
    active: bool = False
    cycle_id: int = 0
    high_watermark: float = 0.0
    previous_cycle_peak: float = 0.0
    off_months: int = 0
    on_months: int = 0
    pending_trigger: Optional[str] = None
    last_sell_month: Optional[str] = None
    last_observation_month: Optional[str] = None
    was_below_activation: bool = True
    independent_triggers: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "KechuangProtectionState":
        if not value:
            return cls()
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: item for key, item in value.items() if key in allowed})


@dataclass(frozen=True)
class KechuangEvaluation:
    next_state: KechuangProtectionState
    desired_sell_shares: float = 0.0
    reason_code: Optional[str] = None
    target_weight: Optional[float] = None
    profit_return: Optional[float] = None
    drawdown_from_high: Optional[float] = None
    activated_this_month: bool = False


def evaluate_kechuang(
    *,
    observation_date: date,
    position: Optional[PositionSnapshot],
    trend_on: bool,
    opportunity_score: Optional[float],
    managed_total: float,
    state: KechuangProtectionState,
) -> KechuangEvaluation:
    """Evaluate one monthly observation without mutating persisted state."""
    current_month = month_key(observation_date)
    is_new_observation = state.last_observation_month != current_month
    next_state = state

    if is_new_observation:
        next_state = replace(
            next_state,
            on_months=(next_state.on_months + 1 if trend_on else 0),
            off_months=(0 if trend_on else next_state.off_months + 1),
            last_observation_month=current_month,
        )

    if position is None or position.shares <= 0 or position.price <= 0:
        return KechuangEvaluation(next_state=next_state)

    profit_return: Optional[float] = None
    if position.average_cost is not None and position.average_cost > 0:
        profit_return = position.price / position.average_cost - 1.0

    if profit_return is not None and profit_return < KECHUANG_ACTIVATION_RETURN:
        next_state = replace(next_state, was_below_activation=True)

    activated = False
    if not next_state.active and profit_return is not None:
        rearm_allowed = (
            next_state.was_below_activation
            or position.price > next_state.previous_cycle_peak + 1e-12
        )
        if (
            profit_return >= KECHUANG_ACTIVATION_RETURN
            and trend_on
            and rearm_allowed
        ):
            next_state = replace(
                next_state,
                active=True,
                cycle_id=next_state.cycle_id + 1,
                high_watermark=position.price,
                pending_trigger=None,
                was_below_activation=False,
            )
            activated = True

    if not next_state.active:
        return KechuangEvaluation(
            next_state=next_state,
            profit_return=profit_return,
            activated_this_month=activated,
        )

    if position.price > next_state.high_watermark:
        next_state = replace(next_state, high_watermark=position.price)

    drawdown = (
        1.0 - position.price / next_state.high_watermark
        if next_state.high_watermark > 0
        else None
    )
    reason: Optional[str] = None
    desired_sell_shares = 0.0
    target_weight: Optional[float] = None

    # The two-month OFF exit has priority over the partial drawdown order.
    if not trend_on and next_state.off_months >= KECHUANG_OFF_MONTHS_EXIT:
        target_weight = KECHUANG_EXIT_TARGET
        desired_value = max(0.0, position.value - target_weight * managed_total)
        desired_sell_shares = desired_value / position.price
        reason = "K50_TWO_MONTH_OFF_EXIT"
    elif (
        not trend_on
        and drawdown is not None
        and drawdown + 1e-12 >= KECHUANG_DRAWDOWN_TRIGGER
    ):
        desired_sell_shares = position.shares * KECHUANG_PARTIAL_SELL_FRACTION
        reason = "K50_HWM_DRAWDOWN_PARTIAL"

    if reason:
        next_state = replace(next_state, pending_trigger=reason)

    return KechuangEvaluation(
        next_state=next_state,
        desired_sell_shares=max(0.0, desired_sell_shares),
        reason_code=reason,
        target_weight=target_weight,
        profit_return=profit_return,
        drawdown_from_high=drawdown,
        activated_this_month=activated,
    )


def apply_confirmed_kechuang_sale(
    state_after_observation: KechuangProtectionState,
    *,
    sale_date: date,
    filled_shares: float,
) -> KechuangProtectionState:
    """Close the current protection cycle only after a real executable fill."""
    if filled_shares <= 0:
        return state_after_observation
    peak = max(
        state_after_observation.previous_cycle_peak,
        state_after_observation.high_watermark,
    )
    return replace(
        state_after_observation,
        active=False,
        high_watermark=0.0,
        previous_cycle_peak=peak,
        pending_trigger=None,
        last_sell_month=month_key(sale_date),
        on_months=0,
        off_months=0,
        was_below_activation=False,
        independent_triggers=state_after_observation.independent_triggers + 1,
    )


def kechuang_buy_allowed(
    *,
    observation_date: date,
    state: KechuangProtectionState,
    trend_on: bool,
    opportunity_score: Optional[float],
    current_weight: float,
) -> bool:
    """Apply re-entry discipline after an actual protection sale."""
    if state.last_sell_month is None:
        return True
    required_distance = KECHUANG_COOLDOWN_FULL_MONTHS + 1
    return bool(
        month_distance(observation_date, state.last_sell_month) >= required_distance
        and trend_on
        and state.on_months >= KECHUANG_REENTRY_ON_MONTHS
        and opportunity_score is not None
        and opportunity_score >= KECHUANG_REENTRY_SCORE
        and current_weight < TARGET_WEIGHTS["科创50ETF"]
    )
