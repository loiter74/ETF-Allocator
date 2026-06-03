"""
tests/unit/test_regression.py — 回归测试：边界条件与稳定性。
"""
import pytest
from src.regime.thermometer import equity_ratio, reset_persistence, _tier
from src.allocation.allocator import allocate
from src.constraints.portfolio import buy_coefficient


class TestBoundary:
    """参数边界测试"""

    def test_tier_boundaries(self):
        """档位边界值不出错"""
        assert _tier(0.0) == 0
        assert _tier(0.599) == 0
        assert _tier(0.60) == 1
        assert _tier(0.799) == 1
        assert _tier(0.80) == 2
        assert _tier(0.899) == 2
        assert _tier(0.90) == 3
        assert _tier(1.0) == 3

    def test_extreme_percentiles_no_crash(self):
        """极端分位值不崩溃"""
        reset_persistence()
        # All extreme combinations
        r, _ = equity_ratio(0.0, 0.0)
        assert r == 1.0
        r, _ = equity_ratio(1.0, 1.0)
        assert r == 0.30
        r, _ = equity_ratio(0.999, 0.001)
        assert 0 <= r <= 1  # 不一致但不崩

    def test_alloc_with_zero_budget(self):
        """预算为 0 不崩溃"""
        scores = {"白酒ETF": 0.5, "银行ETF": 0.5}
        limits = {"白酒ETF": 0.3, "银行ETF": 0.3}
        weights = {"白酒ETF": 0.1, "银行ETF": 0.1}
        result = allocate(scores, weights, limits, total_assets=100_000, equity_budget=0)
        for a in ["白酒ETF", "银行ETF"]:
            assert result.get(a, 0) == 0

    def test_missing_scores_handled(self):
        """某个资产机会分为 None → 跳过"""
        scores = {"白酒ETF": 0.5, "银行ETF": None, "红利ETF": 0.6}
        limits = {"白酒ETF": 0.3, "银行ETF": 0.3, "红利ETF": 0.3}
        weights = {"白酒ETF": 0.1, "银行ETF": 0.1, "红利ETF": 0.1}
        result = allocate(scores, weights, limits, total_assets=100_000, equity_budget=10_000)
        # 银行被跳过但其他正常分配
        assert result.get("银行ETF", 0) == 0
        assert result.get("白酒ETF", 0) >= 0
        assert result.get("红利ETF", 0) >= 0

    def test_negative_weights_clamped(self):
        """负权重被截断为 0"""
        coef = buy_coefficient(-0.05, 0.25)
        assert coef >= 0  # 系数非负

    def test_negative_allocation_clamped(self):
        """分配结果不含负值"""
        scores = {"白酒ETF": 0.0, "银行ETF": 0.0}
        limits = {"白酒ETF": 0.3, "银行ETF": 0.3}
        weights = {"白酒ETF": 1.0, "银行ETF": 0.0}  # 白酒远超上限
        result = allocate(scores, weights, limits, total_assets=10_000, equity_budget=1_000)
        for v in result.values():
            assert v >= 0


class TestOutlierFiltering:
    """异常值过滤"""

    def test_dividend_outlier_filtered(self):
        """股息率 > 1.0（100%）被过滤"""
        from src.factors.dividend import dividend_yield_percentile
        import pandas as pd
        from datetime import datetime, timedelta
        dates = pd.date_range(end=datetime.now(), periods=300, freq='D')
        # 正常股息率 3-5%，第300个点是正常值
        normal = pd.Series([0.03 + (i % 20) * 0.001 for i in range(300)], index=dates)
        # 插入一个异常值替换倒数第二个点
        normal.iloc[-2] = 4.39
        result = dividend_yield_percentile(normal, max_window_years=5)
        assert result is not None
        assert 0 <= result <= 1

    def test_pe_negative_filtered(self):
        """负 PE 被过滤"""
        from src.factors.value import pe_percentile
        import pandas as pd
        from datetime import datetime, timedelta
        dates = pd.date_range(end=datetime.now(), periods=300, freq='D')
        normal = pd.Series([10 + (i % 30) * 0.5 for i in range(300)], index=dates)
        # 倒数第二个点为负值异常
        normal.iloc[-2] = -5
        result = pe_percentile(normal, max_window_years=5)
        assert result is not None
        assert 0 <= result <= 1
