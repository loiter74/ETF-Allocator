"""
测试 store/validator.py — AntiLookAhead 时间约束校验器。
这是整个系统防止未来函数泄漏的第一道防线。
"""
import sys
import os
import sqlite3
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.store.schema import create_tables, insert_index_valuation, insert_etf_price
from src.store.validator import (
    validate_publish_date_not_future,
    get_available_valuations,
    get_available_prices,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_tables(c)
    yield c
    c.close()


class TestValidatePublishDate:
    """publish_date 不能早于其所描述的 trade_date。"""

    def test_publish_same_as_trade_ok(self):
        assert validate_publish_date_not_future("2024-01-15", "2024-01-15") is True

    def test_publish_before_trade_fails(self):
        assert validate_publish_date_not_future("2024-01-10", "2024-01-15") is False

    def test_publish_after_trade_ok(self):
        assert validate_publish_date_not_future("2024-01-20", "2024-01-15") is True

    def test_mixed_integer_dates_do_not_leak_future_rows(self, conn):
        conn.execute(
            "INSERT INTO index_valuation VALUES (?,?,?,?,?,?)",
            ("000300", 20270101, 12.0, 1.2, 0.03, 20270102),
        )
        assert get_available_valuations(conn, date(2024, 1, 1), "000300") == []

    def test_publish_date_none_fails(self):
        """缺少 publish_date → 不安全，拒绝"""
        assert validate_publish_date_not_future(None, "2024-01-15") is False

    def test_trade_date_none_fails(self):
        assert validate_publish_date_not_future("2024-01-15", None) is False


class TestGetAvailableValuations:
    """按决策日 T 过滤估值数据"""

    def setup_data(self, conn):
        """插入三条估值数据，publish_date 各不相同"""
        insert_index_valuation(conn, "000300", "2024-01-15",
                                pe=11.5, pb=1.3, dividend_yield=3.2,
                                publish_date="2024-01-15")
        insert_index_valuation(conn, "000300", "2024-01-16",
                                pe=11.8, pb=1.4, dividend_yield=3.1,
                                publish_date="2024-01-16")
        insert_index_valuation(conn, "000300", "2024-01-17",
                                pe=12.0, pb=1.5, dividend_yield=3.0,
                                publish_date="2024-01-18")  # 晚一天发布
        # 插入index_info以通过外键（如果有的话）
        try:
            from src.store.schema import insert_index_info
            insert_index_info(conn, "000300", "沪深300", "2004-12-31", "2005-04-08")
        except Exception:
            pass

    def test_decision_day_T_16_gets_two_rows(self, conn):
        """T=01-16：可以看到 publish_date ≤ T 的两行"""
        self.setup_data(conn)
        rows = get_available_valuations(conn, date(2024, 1, 16))
        # publish_date: 01-15 ✓, 01-16 ✓, 01-18 ✗
        assert len(rows) == 2
        dates = {r["trade_date"] for r in rows}
        assert "2024-01-15" in dates
        assert "2024-01-16" in dates
        assert "2024-01-17" not in dates  # publish_date=01-18 > T=01-16

    def test_decision_day_T_17_gets_two_rows(self, conn):
        """T=01-17：01-18 发布的数据仍然不可见"""
        self.setup_data(conn)
        rows = get_available_valuations(conn, date(2024, 1, 17))
        assert len(rows) == 2

    def test_decision_day_T_18_gets_all_three(self, conn):
        """T=01-18：所有数据都可见了"""
        self.setup_data(conn)
        rows = get_available_valuations(conn, date(2024, 1, 18))
        assert len(rows) == 3

    def test_future_decision_day_gets_all(self, conn):
        """T 远大于所有 publish_date → 全部可见"""
        self.setup_data(conn)
        rows = get_available_valuations(conn, date(2024, 6, 1))
        assert len(rows) == 3

    def test_past_decision_day_gets_none(self, conn):
        """T 远小于所有 publish_date → 零条"""
        self.setup_data(conn)
        rows = get_available_valuations(conn, date(2020, 1, 1))
        assert len(rows) == 0

    def test_filter_by_index_code(self, conn):
        self.setup_data(conn)
        rows = get_available_valuations(
            conn, date(2024, 6, 1), index_code="000300"
        )
        assert len(rows) == 3
        rows_other = get_available_valuations(
            conn, date(2024, 6, 1), index_code="nonexist"
        )
        assert len(rows_other) == 0


class TestGetAvailablePrices:
    """价格数据没有 publish_date（即时可得），但有 trade_date 过滤"""

    def setup_data(self, conn):
        insert_etf_price(conn, "510300", "2024-01-15", close_adj=3.45, volume=1e7)
        insert_etf_price(conn, "510300", "2024-01-16", close_adj=3.50, volume=1e7)
        insert_etf_price(conn, "510300", "2024-01-17", close_adj=3.48, volume=1e7)

    def test_T_16_gets_two_prices(self, conn):
        self.setup_data(conn)
        rows = get_available_prices(conn, date(2024, 1, 16))
        assert len(rows) == 2

    def test_T_17_gets_three_prices(self, conn):
        self.setup_data(conn)
        rows = get_available_prices(conn, date(2024, 1, 17))
        assert len(rows) == 3

    def test_T_before_any_price(self, conn):
        self.setup_data(conn)
        rows = get_available_prices(conn, date(2020, 1, 1))
        assert len(rows) == 0
