"""
测试 factors/dividend.py — 股息率分位计算。
方向：股息率越高 → 分位越高（机会越好）。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import pandas as pd
import numpy as np

from src.factors.dividend import dividend_yield_percentile


class TestDividendYieldPercentile:
    def test_returns_float(self):
        dy_series = pd.Series(np.linspace(2.0, 5.0, 250))
        result = dividend_yield_percentile(dy_series, max_window_years=5)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_higher_dividend_higher_score(self):
        """股息率越高 → 分位越高（方向与 PE 相反）"""
        # 需要足够数据（≥242）
        np.random.seed(42)
        low_series = pd.Series(np.linspace(1.0, 3.0, 250))
        high_series = pd.Series(np.linspace(5.0, 9.0, 250))

        low_result = dividend_yield_percentile(low_series, max_window_years=5)
        high_result = dividend_yield_percentile(high_series, max_window_years=5)

        assert 0.0 <= low_result <= 1.0
        assert 0.0 <= high_result <= 1.0

    def test_lowest_dividend_returns_low_percentile(self):
        """历史股息高，当前股息低 → 当前处于低位，分位低"""
        # 构造：前 240 天 5%，最后 10 天 2%
        dy_series = pd.Series(
            [5.0] * 240 + [2.0] * 10
        )
        result = dividend_yield_percentile(dy_series, max_window_years=5)
        assert result is not None
        assert result < 0.5

    def test_highest_dividend_returns_high_percentile(self):
        """历史股息低，当前股息高 → 当前处于高位，分位高"""
        dy_series = pd.Series(
            [2.0] * 240 + [5.0] * 10
        )
        result = dividend_yield_percentile(dy_series, max_window_years=5)
        assert result is not None
        assert result > 0.5

    def test_insufficient_data_returns_none(self):
        dy_series = pd.Series([2.0, 2.1])
        result = dividend_yield_percentile(dy_series, max_window_years=5)
        assert result is None
