from datetime import date

import pytest

from config.settings import ASSETS, TARGET_BANDS, TARGET_WEIGHTS
from src.strategy.models import PortfolioSnapshot, PositionSnapshot
from src.strategy.planner import build_trade_plan, strategic_equity_ratio
from src.strategy.kechuang import KechuangProtectionState


def _position(asset: str, value: float, *, price: float = 1.0, cost: float | None = None):
    return PositionSnapshot(
        asset=asset,
        code=ASSETS.get(asset, {}).get("code", "600000"),
        shares=value / price,
        price=price,
        market_value=value,
        average_cost=cost,
        is_equity=asset != "国债ETF",
    )


def _snapshot(
    values: dict[str, float],
    *,
    when: date = date(2026, 8, 31),
    new_money: float = 0.0,
    cash: float = 0.0,
    pool: float = 0.0,
    pending: float = 0.0,
    extra=(),
):
    return PortfolioSnapshot(
        snapshot_date=when,
        price_date=when,
        new_money=new_money,
        account_cash=cash,
        bond_pool_cash=pool,
        equity_pending_cash=pending,
        positions=tuple(_position(name, value) for name, value in values.items()) + tuple(extra),
    )


def _scores(value: float | None = 0.5):
    return {name: (None if name == "国债ETF" else value) for name in ASSETS}


def _limits(overrides=None):
    result = {name: band[1] for name, band in TARGET_BANDS.items()}
    result.update(overrides or {})
    return result


def test_whole_account_gate_exact_boundaries_use_thermometer():
    assert strategic_equity_ratio(0.7999, 0.3) == 1.0
    assert strategic_equity_ratio(0.80, 0.3) == 0.3
    assert strategic_equity_ratio(0.90, 0.7) == 0.7
    assert strategic_equity_ratio(0.9001, 1.0) == 0.0


def test_defense_deposit_is_capped_at_twenty_percent():
    snapshot = _snapshot(
        {
            "白酒ETF": 20_000,
            "银行ETF": 20_000,
            "红利ETF": 15_000,
            "沪深300ETF": 15_000,
            "科创50ETF": 10_000,
            "国债ETF": 19_000,
        },
        cash=1_000,
        new_money=10_000,
    )
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(None),
        risk_upper_limits=_limits(),
        thermometer_equity_ratio=0.0,
        market_prices={name: 1.0 for name in ASSETS},
    )
    assert plan.cash_ledger.bond_pool_deposit == pytest.approx(3_000)
    assert plan.cash_ledger.equity_pending_after == pytest.approx(7_000)


def test_score_point_twenty_repairs_lower_band():
    snapshot = _snapshot(
        {
            "白酒ETF": 20_000,
            "银行ETF": 0,
            "红利ETF": 20_000,
            "沪深300ETF": 30_000,
            "科创50ETF": 10_000,
            "国债ETF": 20_000,
        },
        new_money=10_000,
    )
    scores = _scores(None)
    scores["银行ETF"] = 0.20
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=scores,
        risk_upper_limits=_limits(),
        thermometer_equity_ratio=1.0,
        market_prices={name: 1.0 for name in ASSETS},
    )
    bank = next(order for order in plan.buys if order.asset == "银行ETF")
    assert "LOWER_BAND_REPAIR" in bank.allocation_stages


def test_score_point_eighty_can_extend_only_to_target_plus_two_pp():
    values = {name: TARGET_WEIGHTS[name] * 100_000 for name in ASSETS}
    snapshot = _snapshot(values, new_money=10_000)
    scores = _scores(None)
    scores["银行ETF"] = 0.80
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=scores,
        risk_upper_limits=_limits(),
        thermometer_equity_ratio=1.0,
        market_prices={name: 1.0 for name in ASSETS},
    )
    assert any("HIGH_OPPORTUNITY_EXTENSION" in order.allocation_stages for order in plan.buys)
    assert plan.after["managed_weights"]["银行ETF"] <= TARGET_WEIGHTS["银行ETF"] + 0.02 + 1e-8
    assert plan.after["managed_weights"]["银行ETF"] > TARGET_WEIGHTS["银行ETF"]


def test_core_hard_cap_sells_to_target_plus_two_pp():
    snapshot = _snapshot(
        {
            "白酒ETF": 30_000,
            "银行ETF": 20_000,
            "红利ETF": 15_000,
            "沪深300ETF": 15_000,
            "科创50ETF": 10_000,
            "国债ETF": 10_000,
        }
    )
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(),
        risk_upper_limits=_limits(),
        market_prices={name: 1.0 for name in ASSETS},
    )
    assert plan.phase == "sell_preview"
    order = next(order for order in plan.formal_sells if order.asset == "白酒ETF")
    assert "STRATEGIC_HARD_CAP" in order.reason_codes
    assert order.shares == 10_500
    assert plan.pending_buy_recalculation is True


def test_dynamic_risk_buy_cap_does_not_trigger_sale():
    snapshot = _snapshot(
        {
            "白酒ETF": 22_000,
            "银行ETF": 20_000,
            "红利ETF": 17_000,
            "沪深300ETF": 20_000,
            "科创50ETF": 10_000,
            "国债ETF": 11_000,
        }
    )
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(),
        risk_upper_limits=_limits({"白酒ETF": 0.20}),
        market_prices={name: 1.0 for name in ASSETS},
    )
    assert not plan.formal_sells


def test_annual_relative_soft_band_sells_only_above_outer_band():
    snapshot = _snapshot(
        {
            "白酒ETF": 15_000,
            "银行ETF": 25_000,
            "红利ETF": 15_000,
            "沪深300ETF": 20_000,
            "科创50ETF": 10_000,
            "国债ETF": 15_000,
        },
        when=date(2026, 12, 31),
    )
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(),
        risk_upper_limits=_limits(),
        market_prices={name: 1.0 for name in ASSETS},
    )
    bank = next(order for order in plan.formal_sells if order.asset == "银行ETF")
    assert bank.shares == 3_000
    assert bank.reason_codes == ("ANNUAL_SOFT_BAND",)


def test_one_bond_lot_is_never_sold_and_unknown_holding_is_warning_only():
    unknown = _position("航民股份", 5_000)
    snapshot = PortfolioSnapshot(
        snapshot_date=date(2026, 12, 31),
        price_date=date(2026, 12, 31),
        new_money=0,
        account_cash=0,
        bond_pool_cash=0,
        positions=(
            _position("白酒ETF", 10_000),
            _position("银行ETF", 10_000),
            _position("国债ETF", 10_000, price=100.0),
            unknown,
        ),
    )
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(None),
        risk_upper_limits=_limits(),
        market_prices={name: 1.0 for name in ASSETS},
    )
    assert not any(order.asset == "国债ETF" for order in plan.formal_sells)
    assert not any(order.asset == "航民股份" for order in (*plan.formal_sells, *plan.buys))
    assert any("非白名单" in warning for warning in plan.warnings)


def test_multiple_bond_lots_may_sell_annually_but_not_below_floor():
    snapshot = _snapshot(
        {
            "白酒ETF": 15_000,
            "银行ETF": 15_000,
            "红利ETF": 15_000,
            "沪深300ETF": 15_000,
            "科创50ETF": 10_000,
            "国债ETF": 30_000,
        },
        when=date(2026, 12, 31),
    )
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(None),
        risk_upper_limits=_limits(),
        market_prices={name: 1.0 for name in ASSETS},
    )
    bond = next(order for order in plan.formal_sells if order.asset == "国债ETF")
    assert bond.shares == 13_500
    assert (30_000 - bond.shares * bond.reference_price) / 100_000 >= 0.10


def test_cash_ledger_conserves_cash_to_cent():
    values = {name: TARGET_WEIGHTS[name] * 100_000 for name in ASSETS}
    plan = build_trade_plan(
        _snapshot(values, new_money=10_000),
        opportunity_scores=_scores(0.5),
        risk_upper_limits=_limits(),
        market_prices={name: 1.0 for name in ASSETS},
    )
    assert abs(plan.cash_ledger.cash_identity_error) < 0.005


def test_legacy_allocation_only_never_generates_any_sell_capability():
    k50 = PositionSnapshot(
        "科创50ETF", "588000", 20_000, 1.0, 20_000, 0.5, True,
    )
    snapshot = PortfolioSnapshot(
        date(2026, 8, 31), date(2026, 8, 31), 0, 0, 0,
        (_position("白酒ETF", 30_000), k50),
        legacy_allocation_only=True,
    )
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(0.9),
        risk_upper_limits=_limits(),
        market_prices={name: 1.0 for name in ASSETS},
        kechuang_trend_on=True,
    )
    assert not plan.formal_sells
    assert not plan.shadow_sells
    assert plan.legacy_allocation_only is True


def test_kechuang_shadow_sell_never_enters_formal_orders_or_cash_ledger():
    k50 = PositionSnapshot(
        "科创50ETF", "588000", 1000, 1.10, 1100, 0.8, True,
    )
    snapshot = PortfolioSnapshot(
        date(2026, 8, 31), date(2026, 8, 31), 0, 8900, 0, (k50,),
    )
    state = KechuangProtectionState(active=True, high_watermark=1.25, cycle_id=1)
    plan = build_trade_plan(
        snapshot,
        opportunity_scores=_scores(0.5),
        risk_upper_limits=_limits(),
        market_prices={name: 1.0 for name in ASSETS} | {"科创50ETF": 1.10},
        kechuang_trend_on=False,
        kechuang_state=state,
        protection_mode="shadow",
    )
    assert not plan.formal_sells
    assert len(plan.shadow_sells) == 1
    assert plan.shadow_sells[0].shares == 300
    assert plan.cash_ledger.sell_net_proceeds == 0
