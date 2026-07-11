"""
store/validator.py — AntiLookAhead 时间约束校验器。

核心功能：
1. 检查 publish_date 不晚于 trade_date
2. 按决策日 T 过滤可用的估值和价格数据（point-in-time）
"""
import sqlite3
from datetime import date
from typing import Optional, List, Dict

from src.store.normalization import normalize_iso_date


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
    # Publication normally happens on or after the represented trade date.
    return normalize_iso_date(publish_date) >= normalize_iso_date(trade_date)


def get_available_valuations(
    conn: sqlite3.Connection,
    decision_date: date,
    index_code: Optional[str] = None,
) -> List[Dict]:
    """
    获取 decision_date 当天及之前公开的估值数据。
    只返回 publish_date ≤ decision_date 的行。
    """
    decision_iso = normalize_iso_date(decision_date)
    query = """
        SELECT index_code, trade_date, pe, pb, dividend_yield, publish_date
        FROM index_valuation
    """
    params = []

    if index_code is not None:
        query += " WHERE index_code = ?"
        params.append(index_code)

    cursor = conn.execute(query, params)
    visible = []
    for row in cursor.fetchall():
        item = dict(row)
        trade_iso = normalize_iso_date(item["trade_date"])
        publish_iso = normalize_iso_date(item["publish_date"])
        if trade_iso <= decision_iso and publish_iso <= decision_iso:
            item["trade_date"] = trade_iso
            item["publish_date"] = publish_iso
            visible.append(item)
    visible.sort(key=lambda item: (item["trade_date"], item["publish_date"]))
    return visible


def get_available_prices(
    conn: sqlite3.Connection,
    decision_date: date,
    code: Optional[str] = None,
) -> List[Dict]:
    """
    获取 decision_date 当天及之前的 ETF 价格。
    价格数据即时可得，因此用 trade_date ≤ decision_date 过滤。
    """
    decision_iso = normalize_iso_date(decision_date)
    query = """
        SELECT code, trade_date, close_adj, volume
        FROM etf_price
    """
    params = []

    if code is not None:
        query += " WHERE code = ?"
        params.append(code)

    cursor = conn.execute(query, params)
    visible = []
    for row in cursor.fetchall():
        item = dict(row)
        trade_iso = normalize_iso_date(item["trade_date"])
        if trade_iso <= decision_iso:
            item["trade_date"] = trade_iso
            visible.append(item)
    visible.sort(key=lambda item: item["trade_date"])
    return visible
