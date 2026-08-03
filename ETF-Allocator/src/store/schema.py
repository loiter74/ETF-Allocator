"""
store/schema.py — SQLite 建表语句与基础 CRUD。
所有表使用 IF NOT EXISTS 保证幂等。
"""
import sqlite3
from typing import Optional

from src.store.normalization import normalize_dividend_yield, normalize_iso_date

SCHEMA_VERSION = 4

DDL = """
-- 指数元信息：基日 vs 发布日，用于识别"回填段"
CREATE TABLE IF NOT EXISTS index_info (
    index_code  TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    base_date   DATE NOT NULL,
    publish_date DATE NOT NULL
);

-- ETF 元信息：factor_group 是反伪分散的关键
CREATE TABLE IF NOT EXISTS etf_info (
    code         TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    asset_class  TEXT NOT NULL,
    factor_group TEXT NOT NULL,    -- VALUE / GROWTH / DEFENSE
    tracking_index TEXT,
    list_date    DATE
);

-- 指数估值（挂在指数上，ETF 本身没 PE）
CREATE TABLE IF NOT EXISTS index_valuation (
    index_code    TEXT NOT NULL,
    trade_date    DATE NOT NULL,
    pe            REAL,
    pb            REAL,
    dividend_yield REAL,
    publish_date  DATE NOT NULL,   -- ★ 该数据实际公开的日期
    PRIMARY KEY (index_code, trade_date)
);

-- ETF 价格（必须后复权）
CREATE TABLE IF NOT EXISTS etf_price (
    code       TEXT NOT NULL,
    trade_date DATE NOT NULL,
    close_adj  REAL NOT NULL,
    volume     REAL,
    PRIMARY KEY (code, trade_date)
);

-- 因子计算结果（可选缓存，用于审计和提速）
CREATE TABLE IF NOT EXISTS etf_factor (
    code             TEXT NOT NULL,
    calc_date        DATE NOT NULL,
    factor_name      TEXT NOT NULL,
    raw_value        REAL,
    opportunity_score REAL,
    PRIMARY KEY (code, calc_date, factor_name)
);

-- 用户确认的真实追加投入；与模拟/分配结果分离
CREATE TABLE IF NOT EXISTS investment_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    investment_date DATE NOT NULL,
    amount_cents    INTEGER NOT NULL CHECK (amount_cents > 0),
    note            TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 200),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (investment_date, amount_cents, note)
);

CREATE INDEX IF NOT EXISTS idx_investment_record_date
ON investment_record (investment_date DESC, id DESC);

-- 每次真实投入在六个资产之间的分项；旧记录可没有子项
CREATE TABLE IF NOT EXISTS investment_record_item (
    record_id    INTEGER NOT NULL,
    asset        TEXT NOT NULL CHECK (
        asset IN ('白酒ETF', '银行ETF', '红利ETF', '沪深300ETF', '科创50ETF', '国债ETF')
    ),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    PRIMARY KEY (record_id, asset),
    FOREIGN KEY (record_id) REFERENCES investment_record(id) ON DELETE CASCADE
);

-- 券商月度持仓快照：仅显式确认时写入，预览接口保持只读
CREATE TABLE IF NOT EXISTS portfolio_snapshot (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date            DATE NOT NULL,
    price_date               DATE NOT NULL,
    new_money_cents          INTEGER NOT NULL CHECK (new_money_cents >= 0),
    account_cash_cents       INTEGER NOT NULL CHECK (account_cash_cents >= 0),
    bond_pool_cash_cents     INTEGER NOT NULL CHECK (bond_pool_cash_cents >= 0),
    reverse_repo_cash_cents  INTEGER NOT NULL CHECK (reverse_repo_cash_cents >= 0),
    equity_pending_cents     INTEGER NOT NULL CHECK (equity_pending_cents >= 0),
    sell_proceeds_cents      INTEGER NOT NULL CHECK (sell_proceeds_cents >= 0),
    total_assets_cents       INTEGER NOT NULL CHECK (total_assets_cents >= 0),
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_date
ON portfolio_snapshot (snapshot_date DESC, id DESC);

CREATE TABLE IF NOT EXISTS portfolio_snapshot_item (
    snapshot_id   INTEGER NOT NULL,
    asset         TEXT NOT NULL,
    code          TEXT NOT NULL,
    shares        REAL NOT NULL CHECK (shares >= 0),
    price         REAL NOT NULL CHECK (price >= 0),
    market_value  REAL NOT NULL CHECK (market_value >= 0),
    average_cost  REAL,
    is_equity     INTEGER NOT NULL CHECK (is_equity IN (0, 1)),
    PRIMARY KEY (snapshot_id, asset, code),
    FOREIGN KEY (snapshot_id) REFERENCES portfolio_snapshot(id) ON DELETE CASCADE
);

-- 月频策略状态使用JSON保存，便于状态机字段向后兼容
CREATE TABLE IF NOT EXISTS strategy_state (
    strategy_name TEXT PRIMARY KEY,
    state_json    TEXT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1,
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- 幂等确认同时保存输入快照、成交和最终响应，重复请求不会重复记账
CREATE TABLE IF NOT EXISTS trade_plan_confirmation (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id          TEXT NOT NULL,
    idempotency_key  TEXT NOT NULL UNIQUE,
    snapshot_id      INTEGER NOT NULL,
    response_json    TEXT NOT NULL,
    confirmed_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (snapshot_id) REFERENCES portfolio_snapshot(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_trade_plan_confirmation_plan
ON trade_plan_confirmation (plan_id, confirmed_at DESC);

CREATE TABLE IF NOT EXISTS trade_fill (
    confirmation_id INTEGER NOT NULL,
    asset            TEXT NOT NULL,
    side             TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    shares           REAL NOT NULL CHECK (shares > 0),
    price            REAL NOT NULL CHECK (price > 0),
    commission       REAL NOT NULL CHECK (commission >= 0),
    PRIMARY KEY (confirmation_id, asset, side),
    FOREIGN KEY (confirmation_id) REFERENCES trade_plan_confirmation(id) ON DELETE CASCADE
);
"""


def create_tables(conn: sqlite3.Connection) -> None:
    """建表，幂等（IF NOT EXISTS）。"""
    conn.executescript(DDL)
    conn.commit()


# ---- CRUD helpers ----

def insert_etf_info(
    conn: sqlite3.Connection,
    code: str,
    name: str,
    asset_class: str,
    factor_group: str,
    tracking_index: Optional[str],
    list_date: Optional[str],
) -> None:
    conn.execute(
        """INSERT INTO etf_info (code, name, asset_class, factor_group, tracking_index, list_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            code, name, asset_class, factor_group, tracking_index,
            normalize_iso_date(list_date, allow_none=True),
        ),
    )
    conn.commit()


def insert_index_info(
    conn: sqlite3.Connection,
    index_code: str,
    name: str,
    base_date: str,
    publish_date: str,
) -> None:
    conn.execute(
        """INSERT INTO index_info (index_code, name, base_date, publish_date)
           VALUES (?, ?, ?, ?)""",
        (
            index_code, name,
            normalize_iso_date(base_date),
            normalize_iso_date(publish_date),
        ),
    )
    conn.commit()


def insert_index_valuation(
    conn: sqlite3.Connection,
    index_code: str,
    trade_date: str,
    pe: Optional[float],
    pb: Optional[float],
    dividend_yield: Optional[float],
    publish_date: str,
) -> None:
    conn.execute(
        """INSERT INTO index_valuation
               (index_code, trade_date, pe, pb, dividend_yield, publish_date)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(index_code, trade_date) DO UPDATE SET
               pe = excluded.pe,
               pb = excluded.pb,
               dividend_yield = excluded.dividend_yield,
               publish_date = excluded.publish_date""",
        (
            index_code,
            normalize_iso_date(trade_date),
            pe,
            pb,
            normalize_dividend_yield(dividend_yield),
            normalize_iso_date(publish_date),
        ),
    )
    conn.commit()


def insert_etf_price(
    conn: sqlite3.Connection,
    code: str,
    trade_date: str,
    close_adj: float,
    volume: Optional[float],
) -> None:
    conn.execute(
        """INSERT INTO etf_price (code, trade_date, close_adj, volume)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(code, trade_date) DO UPDATE SET
               close_adj = excluded.close_adj,
               volume = excluded.volume""",
        (code, normalize_iso_date(trade_date), close_adj, volume),
    )
    conn.commit()
