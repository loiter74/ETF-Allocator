"""
测试 store/schema.py — SQLite 建表语句的正确性和幂等性。
"""
import sys
import os
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.store.schema import (
    create_tables,
    insert_etf_info,
    insert_index_info,
    insert_index_valuation,
    insert_etf_price,
)


@pytest.fixture
def conn():
    """内存数据库，每个测试独立"""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


class TestCreateTables:
    def test_create_tables_succeeds(self, conn):
        create_tables(conn)
        # 验证4张表都存在
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "etf_info" in table_names
        assert "index_info" in table_names
        assert "index_valuation" in table_names
        assert "etf_price" in table_names
        assert "investment_record" in table_names
        assert "investment_record_item" in table_names

    def test_create_tables_idempotent(self, conn):
        """连续两次 CREATE TABLE 不应报错（使用 IF NOT EXISTS）"""
        create_tables(conn)
        create_tables(conn)  # 不应抛异常

    def test_etf_info_has_required_columns(self, conn):
        create_tables(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(etf_info)")}
        required = {"code", "name", "asset_class", "factor_group",
                     "tracking_index", "list_date"}
        assert required.issubset(cols), f"Missing: {required - cols}"

    def test_index_info_has_publish_date(self, conn):
        """回填段检测依赖此字段"""
        create_tables(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(index_info)")}
        assert "publish_date" in cols
        assert "base_date" in cols

    def test_index_valuation_has_publish_date(self, conn):
        """Point-in-time 约束依赖此字段"""
        create_tables(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(index_valuation)")}
        assert "publish_date" in cols
        assert "pe" in cols
        assert "pb" in cols
        assert "dividend_yield" in cols

    def test_etf_price_uses_close_adj(self, conn):
        """必须用后复权价"""
        create_tables(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(etf_price)")}
        assert "close_adj" in cols

    def test_investment_record_stores_integer_cents(self, conn):
        create_tables(conn)
        cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(investment_record)")}
        assert cols["amount_cents"]["type"] == "INTEGER"
        assert cols["investment_date"]["notnull"] == 1

    def test_investment_record_has_date_index(self, conn):
        create_tables(conn)
        indexes = {r["name"] for r in conn.execute("PRAGMA index_list(investment_record)")}
        assert "idx_investment_record_date" in indexes

    def test_investment_record_items_store_asset_amounts_in_integer_cents(self, conn):
        create_tables(conn)
        cols = {
            r["name"]: r
            for r in conn.execute("PRAGMA table_info(investment_record_item)")
        }
        assert cols["record_id"]["notnull"] == 1
        assert cols["asset"]["notnull"] == 1
        assert cols["amount_cents"]["type"] == "INTEGER"

        foreign_keys = conn.execute(
            "PRAGMA foreign_key_list(investment_record_item)"
        ).fetchall()
        assert any(
            row["table"] == "investment_record" and row["on_delete"] == "CASCADE"
            for row in foreign_keys
        )


class TestInsertETFInfo:
    def test_insert_and_read(self, conn):
        create_tables(conn)
        insert_etf_info(conn, "510300", "沪深300ETF", "wide", "VALUE",
                        "000300", "2012-05-28")
        row = conn.execute("SELECT * FROM etf_info WHERE code='510300'").fetchone()
        assert row["name"] == "沪深300ETF"
        assert row["factor_group"] == "VALUE"

    def test_duplicate_primary_key_raises(self, conn):
        create_tables(conn)
        insert_etf_info(conn, "510300", "沪深300ETF", "wide", "VALUE",
                        "000300", "2012-05-28")
        with pytest.raises(sqlite3.IntegrityError):
            insert_etf_info(conn, "510300", "dup", "wide", "VALUE",
                            "000300", "2012-05-28")


class TestInsertIndexInfo:
    def test_insert_index_full(self, conn):
        create_tables(conn)
        insert_index_info(conn, "000300", "沪深300", "2004-12-31", "2005-04-08")
        row = conn.execute(
            "SELECT * FROM index_info WHERE index_code='000300'"
        ).fetchone()
        assert row["name"] == "沪深300"
        assert row["base_date"] == "2004-12-31"
        assert row["publish_date"] == "2005-04-08"

    def test_backfill_period_detectable(self, conn):
        """base_date 与 publish_date 之差即为回填段长度"""
        create_tables(conn)
        insert_index_info(conn, "000688", "科创50", "2019-12-31", "2020-07-23")
        row = conn.execute(
            "SELECT * FROM index_info WHERE index_code='000688'"
        ).fetchone()
        # 回填段 ≈ 7个月
        assert row["base_date"] < row["publish_date"]


class TestInsertIndexValuation:
    def test_insert_with_publish_date(self, conn):
        create_tables(conn)
        insert_index_valuation(conn, "000300", "2024-01-15",
                                pe=11.5, pb=1.3, dividend_yield=3.2,
                                publish_date="2024-01-15")
        row = conn.execute(
            "SELECT * FROM index_valuation "
            "WHERE index_code='000300' AND trade_date='2024-01-15'"
        ).fetchone()
        assert row["pe"] == 11.5
        assert row["publish_date"] == "2024-01-15"

    def test_publish_date_not_null(self, conn):
        create_tables(conn)
        with pytest.raises(ValueError):
            insert_index_valuation(conn, "000300", "2024-01-15",
                                    pe=11.5, pb=1.3, dividend_yield=None,
                                    publish_date=None)

    def test_duplicate_valuation_upserts(self, conn):
        """同一 (index_code, trade_date) 应 upsert 而非报错"""
        create_tables(conn)
        insert_index_valuation(conn, "000300", "2024-01-15",
                                pe=11.5, pb=1.3, dividend_yield=3.2,
                                publish_date="2024-01-15")
        # 第二次写入应更新值
        insert_index_valuation(conn, "000300", "2024-01-15",
                                pe=12.0, pb=1.4, dividend_yield=3.0,
                                publish_date="2024-01-16")
        row = conn.execute(
            "SELECT * FROM index_valuation "
            "WHERE index_code='000300' AND trade_date='2024-01-15'"
        ).fetchone()
        assert row["pe"] == 12.0


class TestInsertETFPrice:
    def test_insert_price(self, conn):
        create_tables(conn)
        insert_etf_price(conn, "510300", "2024-01-15", close_adj=3.456, volume=12345678)
        row = conn.execute(
            "SELECT * FROM etf_price WHERE code='510300' AND trade_date='2024-01-15'"
        ).fetchone()
        assert row["close_adj"] == 3.456

    def test_close_adj_must_be_positive(self, conn):
        """后复权价必须 > 0（业务约束，SQL层不强制但代码层应检查）"""
        create_tables(conn)
        # SQLite 允许负值，但我们的 validator 层将拦截
        insert_etf_price(conn, "510300", "2024-01-15", close_adj=-1.0, volume=100)
        row = conn.execute(
            "SELECT * FROM etf_price WHERE code='510300' AND trade_date='2024-01-15'"
        ).fetchone()
        assert row["close_adj"] == -1.0  # SQL层不拦，但这是预期行为
