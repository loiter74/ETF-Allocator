from datetime import date

import pytest

from src.strategy.kechuang import (
    KechuangProtectionState,
    apply_confirmed_kechuang_sale,
    evaluate_kechuang,
    kechuang_buy_allowed,
)
from src.strategy.models import PositionSnapshot


def _position(price=1.25, cost=1.0, shares=1000):
    return PositionSnapshot("科创50ETF", "588000", shares, price, shares * price, cost, True)


def test_activation_requires_25_percent_and_trend_on():
    off = evaluate_kechuang(
        observation_date=date(2026, 1, 31),
        position=_position(),
        trend_on=False,
        opportunity_score=0.8,
        managed_total=10_000,
        state=KechuangProtectionState(),
    )
    assert off.next_state.active is False
    on = evaluate_kechuang(
        observation_date=date(2026, 1, 31),
        position=_position(),
        trend_on=True,
        opportunity_score=0.8,
        managed_total=10_000,
        state=KechuangProtectionState(),
    )
    assert on.next_state.active is True
    assert on.next_state.high_watermark == pytest.approx(1.25)


def test_hwm_drawdown_partial_and_two_off_month_priority():
    state = KechuangProtectionState(active=True, high_watermark=1.25, cycle_id=1)
    first = evaluate_kechuang(
        observation_date=date(2026, 2, 28),
        position=_position(price=1.10),
        trend_on=False,
        opportunity_score=0.5,
        managed_total=10_000,
        state=state,
    )
    assert first.reason_code == "K50_HWM_DRAWDOWN_PARTIAL"
    assert first.desired_sell_shares == pytest.approx(1000 / 3)

    second = evaluate_kechuang(
        observation_date=date(2026, 3, 31),
        position=_position(price=1.0, shares=2000),
        trend_on=False,
        opportunity_score=0.5,
        managed_total=10_000,
        state=first.next_state,
    )
    assert second.reason_code == "K50_TWO_MONTH_OFF_EXIT"
    assert second.target_weight == pytest.approx(0.05)


def test_preview_is_pure_and_real_fill_starts_cooldown():
    state = KechuangProtectionState(active=True, high_watermark=1.25, cycle_id=1)
    result = evaluate_kechuang(
        observation_date=date(2026, 2, 28),
        position=_position(price=1.10),
        trend_on=False,
        opportunity_score=0.5,
        managed_total=10_000,
        state=state,
    )
    assert state.last_observation_month is None
    filled = apply_confirmed_kechuang_sale(
        result.next_state,
        sale_date=date(2026, 2, 28),
        filled_shares=300,
    )
    assert filled.active is False
    assert filled.last_sell_month == "2026-02"
    assert filled.independent_triggers == 1


def test_reentry_needs_full_month_two_on_months_score_and_underweight():
    state = KechuangProtectionState(last_sell_month="2026-01", on_months=2)
    assert not kechuang_buy_allowed(
        observation_date=date(2026, 2, 28), state=state, trend_on=True,
        opportunity_score=0.8, current_weight=0.05,
    )
    assert kechuang_buy_allowed(
        observation_date=date(2026, 3, 31), state=state, trend_on=True,
        opportunity_score=0.50, current_weight=0.05,
    )


def test_new_cycle_needs_recross_or_higher_peak():
    state = KechuangProtectionState(
        active=False,
        previous_cycle_peak=1.50,
        was_below_activation=False,
        last_sell_month="2025-12",
    )
    result = evaluate_kechuang(
        observation_date=date(2026, 3, 31),
        position=_position(price=1.30),
        trend_on=True,
        opportunity_score=0.8,
        managed_total=10_000,
        state=state,
    )
    assert result.next_state.active is False

