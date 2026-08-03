import sqlite3

import pytest

from config.settings import ASSETS, TARGET_BANDS, TARGET_WEIGHTS
from src.api import server


def _position(asset: str, value: float):
    return {
        "asset": asset,
        "code": ASSETS[asset]["code"],
        "shares": value,
        "price": 1.0,
        "market_value": value,
        "average_cost": 0.9,
        "is_equity": asset != "国债ETF",
    }


def _payload(values: dict[str, float], *, new_money=0.0):
    return {
        "snapshot": {
            "snapshot_date": "2026-08-31",
            "price_date": "2026-08-31",
            "new_money": new_money,
            "account_cash": 0,
            "bond_pool_cash": 0,
            "positions": [_position(name, value) for name, value in values.items()],
        },
        "opportunity_scores": {
            name: (None if name == "国债ETF" else 0.5) for name in ASSETS
        },
        "risk_upper_limits": {name: band[1] for name, band in TARGET_BANDS.items()},
        "thermometer_equity_ratio": 1.0,
        "market_prices": {name: 1.0 for name in ASSETS},
        "kechuang_trend_on": True,
    }


def test_preview_is_read_only_and_confirmation_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "strategy.db"
    monkeypatch.setattr(server, "DB_PATH", db_path)
    values = {name: target * 100_000 for name, target in TARGET_WEIGHTS.items()}
    params = server.TradePlanPreviewParams(**_payload(values, new_money=10_000))

    first = server.preview_trade_plan(params)
    second = server.preview_trade_plan(params)
    assert first == second
    assert first["read_only"] is True
    assert first["protection_status"]["mode"] == "shadow"
    assert first["protection_status"]["trend_on"] is True
    assert first["protection_status"]["thresholds"]["activation_return"] == 0.25

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT count(*) FROM strategy_state").fetchone()[0] == 0
    conn.close()

    confirm_payload = _payload(values, new_money=10_000)
    confirm_payload.update({
        "plan_id": first["trade_plan"]["plan_id"],
        "idempotency_key": "2026-08-monthly-confirm",
        "fills": [],
    })
    confirmed = server.confirm_trade_plan(server.TradePlanConfirmParams(**confirm_payload))
    repeated = server.confirm_trade_plan(server.TradePlanConfirmParams(**confirm_payload))
    assert confirmed == repeated

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT count(*) FROM strategy_state").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM trade_plan_confirmation").fetchone()[0] == 1
    conn.close()


def test_preview_exposes_authoritative_profit_protection_status(tmp_path, monkeypatch):
    db_path = tmp_path / "strategy-protection-status.db"
    monkeypatch.setattr(server, "DB_PATH", db_path)
    values = {name: target * 100_000 for name, target in TARGET_WEIGHTS.items()}
    raw = _payload(values)
    kechuang = next(
        position for position in raw["snapshot"]["positions"]
        if position["asset"] == "科创50ETF"
    )
    kechuang["average_cost"] = 0.70

    preview = server.preview_trade_plan(server.TradePlanPreviewParams(**raw))
    status = preview["protection_status"]

    assert status["profit_return"] == pytest.approx(1 / 0.70 - 1)
    assert status["active"] is True
    assert status["activated_this_month"] is True
    assert status["high_watermark"] == 1.0
    assert status["off_months"] == 0
    assert status["triggered"] is False


def test_formal_sell_requires_fill_then_returns_recomputed_plan(tmp_path, monkeypatch):
    db_path = tmp_path / "strategy-sell.db"
    monkeypatch.setattr(server, "DB_PATH", db_path)
    values = {
        "白酒ETF": 30_000,
        "银行ETF": 20_000,
        "红利ETF": 15_000,
        "沪深300ETF": 15_000,
        "科创50ETF": 10_000,
        "国债ETF": 10_000,
    }
    raw = _payload(values, new_money=10_000)
    preview = server.preview_trade_plan(server.TradePlanPreviewParams(**raw))["trade_plan"]
    assert preview["phase"] == "sell_preview"
    sell = next(order for order in preview["formal_sells"] if order["asset"] == "白酒ETF")

    raw.update({
        "plan_id": preview["plan_id"],
        "idempotency_key": "2026-08-sell-confirm",
        "fills": [{
            "asset": "白酒ETF",
            "shares": sell["shares"],
            "price": sell["estimated_price"],
            "commission": sell["commission"],
        }],
    })
    response = server.confirm_trade_plan(server.TradePlanConfirmParams(**raw))
    assert response["confirmed_plan"]["phase"] == "sell_preview"
    assert response["next_plan"]["plan_id"] != preview["plan_id"]
    assert response["next_plan"]["pending_buy_recalculation"] is False
