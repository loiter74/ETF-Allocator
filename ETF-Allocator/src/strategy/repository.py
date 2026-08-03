"""SQLite persistence for confirmed portfolio observations and strategy state."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable, Mapping, Optional

from src.store.schema import create_tables
from src.strategy.kechuang import KechuangProtectionState
from src.strategy.models import PortfolioSnapshot, TradePlan


STRATEGY_NAME = "kechuang_profit_protection"


def _cents(value: float) -> int:
    return int(round(float(value) * 100))


def load_kechuang_state(conn: sqlite3.Connection) -> KechuangProtectionState:
    create_tables(conn)
    row = conn.execute(
        "SELECT state_json FROM strategy_state WHERE strategy_name = ?",
        (STRATEGY_NAME,),
    ).fetchone()
    if not row:
        return KechuangProtectionState()
    raw = row["state_json"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        return KechuangProtectionState.from_mapping(json.loads(raw))
    except (TypeError, json.JSONDecodeError):
        raise ValueError("数据库中的科创利润保护状态无法解析")


def get_confirmation(conn: sqlite3.Connection, idempotency_key: str) -> Optional[dict[str, Any]]:
    create_tables(conn)
    row = conn.execute(
        "SELECT response_json FROM trade_plan_confirmation WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if not row:
        return None
    raw = row["response_json"] if isinstance(row, sqlite3.Row) else row[0]
    return json.loads(raw)


def save_confirmation(
    conn: sqlite3.Connection,
    *,
    idempotency_key: str,
    snapshot: PortfolioSnapshot,
    plan: TradePlan,
    fills: Iterable[Mapping[str, Any]],
    next_state: KechuangProtectionState,
    response: Mapping[str, Any],
) -> dict[str, Any]:
    """Atomically save a confirmed monthly observation and real fills."""
    if not idempotency_key.strip():
        raise ValueError("idempotency_key不能为空")
    create_tables(conn)
    existing = get_confirmation(conn, idempotency_key)
    if existing is not None:
        return existing

    fill_rows = [dict(fill) for fill in fills]
    response_dict = dict(response)
    try:
        with conn:
            cursor = conn.execute(
                """INSERT INTO portfolio_snapshot (
                       snapshot_date, price_date, new_money_cents,
                       account_cash_cents, bond_pool_cash_cents,
                       reverse_repo_cash_cents, equity_pending_cents,
                       sell_proceeds_cents, total_assets_cents
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.snapshot_date.isoformat(),
                    snapshot.price_date.isoformat(),
                    _cents(snapshot.new_money),
                    _cents(snapshot.account_cash),
                    _cents(snapshot.bond_pool_cash),
                    _cents(snapshot.reverse_repo_cash),
                    _cents(snapshot.equity_pending_cash),
                    _cents(snapshot.confirmed_sell_proceeds),
                    _cents(snapshot.total_assets),
                ),
            )
            snapshot_id = int(cursor.lastrowid)
            conn.executemany(
                """INSERT INTO portfolio_snapshot_item (
                       snapshot_id, asset, code, shares, price, market_value,
                       average_cost, is_equity
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        snapshot_id,
                        position.asset,
                        position.code,
                        position.shares,
                        position.price,
                        position.value,
                        position.average_cost,
                        int(position.is_equity),
                    )
                    for position in snapshot.positions
                ],
            )
            conn.execute(
                """INSERT INTO strategy_state (strategy_name, state_json, version, updated_at)
                   VALUES (?, ?, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                   ON CONFLICT(strategy_name) DO UPDATE SET
                     state_json = excluded.state_json,
                     version = strategy_state.version + 1,
                     updated_at = excluded.updated_at""",
                (STRATEGY_NAME, json.dumps(next_state.to_dict(), ensure_ascii=False, sort_keys=True)),
            )
            confirmation = conn.execute(
                """INSERT INTO trade_plan_confirmation (
                       plan_id, idempotency_key, snapshot_id, response_json
                   ) VALUES (?, ?, ?, ?)""",
                (
                    plan.plan_id,
                    idempotency_key,
                    snapshot_id,
                    json.dumps(response_dict, ensure_ascii=False, sort_keys=True),
                ),
            )
            confirmation_id = int(confirmation.lastrowid)
            if fill_rows:
                conn.executemany(
                    """INSERT INTO trade_fill (
                           confirmation_id, asset, side, shares, price, commission
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    [
                        (
                            confirmation_id,
                            str(fill["asset"]),
                            str(fill.get("side", "SELL")).upper(),
                            float(fill["shares"]),
                            float(fill["price"]),
                            float(fill.get("commission", 0.0)),
                        )
                        for fill in fill_rows
                    ],
                )
    except sqlite3.IntegrityError:
        # A concurrent identical confirmation won the unique-key race.
        existing = get_confirmation(conn, idempotency_key)
        if existing is not None:
            return existing
        raise
    return response_dict
