import sqlite3

import pytest
import pandas as pd

from src.allocation.allocator import allocate
from src.backtest.engine import compute_metrics
from src.backtest.parameter_lock import verify_snapshot, write_snapshot
from src.constraints.portfolio import check_factor_group_constraint
from src.store.normalization import normalize_dividend_yield, normalize_iso_date
from src.store.schema import create_tables, insert_etf_price
from src.store.schema import insert_index_valuation
from scripts.migrate_date_contract import audit, migrate


def test_date_and_dividend_normalization():
    assert normalize_iso_date(20260703) == "2026-07-03"
    assert normalize_iso_date("20260703") == "2026-07-03"
    assert normalize_dividend_yield(4.2) == pytest.approx(0.042)
    assert normalize_dividend_yield(0.042) == pytest.approx(0.042)


def test_schema_stores_eight_digit_dates_as_text():
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    insert_etf_price(conn, "510300", 20260703, 4.2, 100.0)
    stored = conn.execute(
        "SELECT trade_date, typeof(trade_date) FROM etf_price"
    ).fetchone()
    assert stored == ("2026-07-03", "text")
    conn.close()


def test_zero_market_return_with_monthly_cashflows_has_zero_metrics():
    result = compute_metrics(
        portfolio_values=[10_000, 20_000, 30_000],
        total_invested=30_000,
        monthly_returns=[0.0, 0.0],
    )
    assert result["annualized_return"] == pytest.approx(0.0)
    assert result["max_drawdown"] == pytest.approx(0.0)


def test_group_cap_uses_all_existing_group_holdings():
    allocations = {"银行ETF": 10_000.0}
    weights = {
        "白酒ETF": 0.30, "银行ETF": 0.15, "红利ETF": 0.15,
        "沪深300ETF": 0.09, "科创50ETF": 0.10, "国债ETF": 0.21,
    }
    result = check_factor_group_constraint(allocations, weights, 100_000)
    assert result["status"] == "scale_down"
    assert result["scaled_allocations"]["银行ETF"] < 10_000
    assert result["scaled_allocations"]["国债ETF"] > 0


def test_initial_build_never_redistributes_past_asset_caps():
    scores = {
        "白酒ETF": 1.0, "银行ETF": 0.9, "红利ETF": 0.8,
        "沪深300ETF": 0.7, "科创50ETF": 0.6, "国债ETF": None,
    }
    limits = {
        "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
        "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
    }
    result = allocate(scores, {k: 0.0 for k in scores}, limits, 0.0, 10_000.0)
    assert result["白酒ETF"] <= 2_500
    assert result["银行ETF"] <= 3_000
    assert result.get("科创50ETF", 0.0) <= 1_500


def test_parameter_snapshot_detects_change(tmp_path, monkeypatch):
    from config import settings

    path = tmp_path / "locked.json"
    snapshot = write_snapshot(path)
    ok, digest = verify_snapshot(path)
    assert ok and digest == snapshot["parameter_hash"]

    monkeypatch.setattr(settings, "ALLOCATION_GAP_WEIGHT", 0.51)
    ok, message = verify_snapshot(path)
    assert not ok
    assert "参数已改变" in message


def test_date_migration_merges_logical_integer_text_duplicates():
    conn = sqlite3.connect(":memory:")
    create_tables(conn)
    conn.execute(
        "INSERT INTO index_valuation VALUES (?,?,?,?,?,?)",
        ("000300", 20240115, 12.0, None, None, 20240116),
    )
    conn.execute(
        "INSERT INTO index_valuation VALUES (?,?,?,?,?,?)",
        ("000300", "2024-01-15", None, 1.2, 0.03, "2024-01-16"),
    )
    conn.commit()
    assert audit(conn)["canonical_duplicates"]["index_valuation"] == 1

    counts = migrate(conn)
    assert counts["index_valuation"] == 1
    row = conn.execute(
        "SELECT trade_date, typeof(trade_date), pe, pb FROM index_valuation"
    ).fetchone()
    assert tuple(row) == ("2024-01-15", "text", 12.0, 1.2)
    conn.close()


def test_flow_a_and_backtest_bank_factors_match():
    from datetime import date
    from run import calculate_factors
    from src.backtest.engine import _compute_factors

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    days = pd.date_range("2023-01-02", periods=300, freq="B")
    for i, day in enumerate(days):
        iso = day.date().isoformat()
        insert_index_valuation(
            conn, "399986", iso,
            pe=6.0, pb=0.6 + i / 10_000, dividend_yield=0.04 + i / 100_000,
            publish_date=iso,
        )
        insert_etf_price(conn, "512800", iso, 1.0 + i / 10_000, 1_000_000)

    decision = days[-1].date()
    flow_a = calculate_factors(conn, decision)["银行ETF"]
    flow_b = _compute_factors(conn, decision, False)["银行ETF"]
    assert flow_a["pb_zscore"] == pytest.approx(flow_b["pb_zscore"])
    assert flow_a["dividend_zscore"] == pytest.approx(flow_b["dividend_zscore"])
    conn.close()
