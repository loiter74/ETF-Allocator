"""
store/validator.py — AntiLookAhead 时间约束校验器。

核心功能：
1. 检查 publish_date 不晚于 trade_date
2. 按决策日 T 过滤可用的估值和价格数据（point-in-time）
"""
import sqlite3
from datetime import date
from typing import Optional, List, Dict


def validate_publish_date_not_future(
    publish_date: Optional[str],
    trade_date: Optional[str],
) -> bool:
    """
    校验 publish_date 不晚于 trade_date。
    如果任一为 None 或 publish_date > trade_date → 返回 False。
    """
    if publish_date is None or trade_date is None:
        return False
    return str(publish_date) <= str(trade_date)


def get_available_valuations(
    conn: sqlite3.Connection,
    decision_date: date,
    index_code: Optional[str] = None,
) -> List[Dict]:
    """
    获取 decision_date 当天及之前公开的估值数据。
    只返回 publish_date ≤ decision_date 的行。
    """
    query = """
        SELECT index_code, trade_date, pe, pb, dividend_yield, publish_date
        FROM index_valuation
        WHERE publish_date <= ?
    """
    params = [decision_date.isoformat()]

    if index_code is not None:
        query += " AND index_code = ?"
        params.append(index_code)

    query += " ORDER BY trade_date"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    return [dict(r) for r in rows]


def get_available_prices(
    conn: sqlite3.Connection,
    decision_date: date,
    code: Optional[str] = None,
) -> List[Dict]:
    """
    获取 decision_date 当天及之前的 ETF 价格。
    价格数据即时可得，因此用 trade_date ≤ decision_date 过滤。
    """
    query = """
        SELECT code, trade_date, close_adj, volume
        FROM etf_price
        WHERE trade_date <= ?
    """
    params = [decision_date.isoformat()]

    if code is not None:
        query += " AND code = ?"
        params.append(code)

    query += " ORDER BY trade_date"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    return [dict(r) for r in rows]
