import sqlite3
from datetime import date

from config.settings import ASSETS, TARGET_BANDS
from src.store.schema import create_tables
from src.strategy.kechuang import KechuangProtectionState
from src.strategy.models import PortfolioSnapshot, PositionSnapshot
from src.strategy.planner import build_trade_plan
from src.strategy.repository import get_confirmation, save_confirmation


def test_confirmation_is_idempotent_and_saves_snapshot_state_and_response():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    position = PositionSnapshot("沪深300ETF", "510300", 10_000, 1.0, 10_000, 0.9, True)
    snapshot = PortfolioSnapshot(date(2026, 8, 31), date(2026, 8, 31), 0, 0, 0, (position,))
    plan = build_trade_plan(
        snapshot,
        opportunity_scores={name: None for name in ASSETS},
        risk_upper_limits={name: band[1] for name, band in TARGET_BANDS.items()},
        market_prices={name: 1.0 for name in ASSETS},
    )
    response = {"ok": True, "plan_id": plan.plan_id}
    state = KechuangProtectionState.from_mapping(plan.state_patch["kechuang"])
    first = save_confirmation(
        conn,
        idempotency_key="monthly-2026-08",
        snapshot=snapshot,
        plan=plan,
        fills=[],
        next_state=state,
        response=response,
    )
    second = save_confirmation(
        conn,
        idempotency_key="monthly-2026-08",
        snapshot=snapshot,
        plan=plan,
        fills=[],
        next_state=state,
        response={"ok": False},
    )
    assert first == second == response
    assert conn.execute("SELECT count(*) FROM portfolio_snapshot").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM trade_plan_confirmation").fetchone()[0] == 1
    assert get_confirmation(conn, "monthly-2026-08") == response
    conn.close()
