"""
测试 factors/risk.py — 波动率与最大回撤计算。
风险因子不进评分，只给 risk controller 使用。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import pandas as pd
import numpy as np

from src.factors.risk import (
    annualized_volatility,
    max_drawdown,
)


def _make_price_series(prices: list) -> pd.Series:
    dates = pd.date_range(start="2023-01-01", periods=len(prices), freq="B")
    return pd.Series(prices, index=dates)


class TestAnnualizedVolatility:
    def test_constant_price_zero_vol(self):
        prices = [10.0] * 100
        s = _make_price_series(prices)
        result = annualized_volatility(s, window=60)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_volatile_price_positive_vol(self):
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(200) * 2)
        s = _make_price_series(prices)
        result = annualized_volatility(s, window=60)
        assert result > 0.0

    def test_insufficient_data_returns_none(self):
        prices = [10.0] * 30  # < 60
        s = _make_price_series(prices)
        result = annualized_volatility(s, window=60)
        assert result is None

    def test_annualized_scale(self):
        """年化波动率 > 日波动率"""
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(500) * 2)
        s = _make_price_series(prices)
        ann_vol = annualized_volatility(s, window=60)
        # 日收益率 std
        daily_std = s.pct_change().dropna().std()
        assert ann_vol > daily_std  # 年化 = daily * sqrt(242)


class TestMaxDrawdown:
    def test_known_drawdown(self):
        """价格序列 [100,80,90,70,95] → 最大回撤 -30%"""
        prices = [100.0, 80.0, 90.0, 70.0, 95.0]
        s = _make_price_series(prices)
        result = max_drawdown(s, window=252)
        # (70-100)/100 = -0.30
        assert result == pytest.approx(-0.30, abs=0.01)

    def test_no_drawdown(self):
        """一直上涨 → 最大回撤 ≈ 0"""
        prices = list(np.linspace(100, 200, 100))
        s = _make_price_series(prices)
        result = max_drawdown(s, window=252)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_always_down(self):
        """一直下跌 → 最大回撤 = 总跌幅"""
        prices = [100.0, 90.0, 80.0, 70.0, 60.0]
        s = _make_price_series(prices)
        result = max_drawdown(s, window=252)
        assert result == pytest.approx(-0.40, abs=0.01)

    def test_output_never_positive(self):
        """最大回撤 ≤ 0"""
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(500))
        s = _make_price_series(prices)
        result = max_drawdown(s, window=252)
        assert result <= 0.0

    def test_insufficient_data_returns_none(self):
        """1 个数据点不足以算回撤"""
        prices = [100.0]
        s = _make_price_series(prices)
        result = max_drawdown(s, window=252)
        assert result is None
