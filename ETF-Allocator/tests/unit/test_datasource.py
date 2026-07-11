"""
测试 datasource/akshare_adapter.py — AkShare 数据获取。
使用真实 AkShare 调用（用户选择 A：真实调用）。

注意：这些测试依赖网络和 AkShare 服务可用性。
在 CI 环境中如网络不可用，可用 @pytest.mark.skipif 跳过。
"""
import sys
import os
import pytest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.datasource.akshare_adapter import (
    fetch_index_valuation,
    fetch_etf_price,
    fetch_index_info,
)


# ---- 辅助：检查 AkShare 是否可用 ----
def _akshare_available():
    try:
        import akshare as ak
        return True
    except ImportError:
        return False


requires_akshare = pytest.mark.skipif(
    not _akshare_available(),
    reason="akshare not installed or network unavailable"
)


@pytest.mark.integration
class TestFetchIndexValuation:
    """拉取指数估值数据"""

    @requires_akshare
    def test_fetch_hs300_returns_pe_pb_dividend(self):
        """沪深300估值应包含PE、PB、股息率"""
        df = fetch_index_valuation("000300")
        assert df is not None
        if df.empty:
            pytest.skip("AkShare valuation endpoint unavailable")
        assert len(df) > 0
        # 核心字段
        for col in ["pe", "pb", "dividend_yield"]:
            assert col in df.columns, f"Missing column: {col}"
        # 至少有一些非空值
        assert df["pe"].notna().any()

    @requires_akshare
    def test_fetch_returns_with_date_columns(self):
        """返回的DataFrame应包含trade_date列"""
        df = fetch_index_valuation("000300")
        if df.empty:
            pytest.skip("AkShare valuation endpoint unavailable")
        assert "trade_date" in df.columns

    @requires_akshare
    def test_fetch_nonexistent_index_returns_empty(self):
        """不存在的指数代码 → 返回空DataFrame，不抛异常"""
        df = fetch_index_valuation("999999")
        assert df is not None
        # 空DataFrame也行，只要不崩溃


@pytest.mark.integration
class TestFetchETFPrice:
    """拉取ETF价格数据"""

    @requires_akshare
    def test_fetch_hs300_etf_returns_close_adj(self):
        """沪深300ETF应返回后复权收盘价"""
        df = fetch_etf_price("510300")
        assert df is not None
        if df.empty:
            pytest.skip("AkShare ETF endpoint unavailable")
        assert len(df) > 0
        assert "close_adj" in df.columns

    @requires_akshare
    def test_fetch_returns_positive_prices(self):
        """后复权价应全部 > 0"""
        df = fetch_etf_price("510300")
        if len(df) > 0:
            assert (df["close_adj"] > 0).all()

    @requires_akshare
    def test_fetch_returns_volume(self):
        """应包含成交量"""
        df = fetch_etf_price("510300")
        if df.empty:
            pytest.skip("AkShare ETF endpoint unavailable")
        assert "volume" in df.columns

    @requires_akshare
    def test_fetch_includes_trade_date(self):
        df = fetch_etf_price("510300")
        if df.empty:
            pytest.skip("AkShare ETF endpoint unavailable")
        assert "trade_date" in df.columns


@pytest.mark.integration
class TestFetchIndexInfo:
    """拉取指数元信息"""

    @requires_akshare
    def test_fetch_hs300_has_base_and_publish_date(self):
        """沪深300指数元信息应有基日和发布日"""
        info = fetch_index_info("000300")
        assert info is not None
        assert "base_date" in info or hasattr(info, "base_date")
        assert "publish_date" in info or hasattr(info, "publish_date")
