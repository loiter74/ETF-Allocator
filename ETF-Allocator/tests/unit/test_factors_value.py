"""
测试 factors/value.py — PE/PB 滚动分位计算。
核心不变量：分位计算只用 expanding window，拒绝全历史分位。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import pandas as pd
import numpy as np
from datetime import date

from src.factors.value import (
    expanding_percentile,
    pe_percentile,
    pb_percentile,
)


class TestExpandingPercentile:
    """滚动分位基础函数"""

    def test_percentile_only_uses_past_data(self):
        """构造序列 [10,20,30,40,50]，T=3 时只用前3个值"""
        values = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        # 每个位置用 expanding window 算分位
        current = 30.0
        # expanding window 到 index=2：[10,20,30]，30 是 max → 分位 = 1.0
        result = expanding_percentile(values.iloc[:3], current)
        # [10, 20, 30] 中 30 是第 100 分位
        assert result == pytest.approx(1.0)

    def test_lowest_value_returns_zero(self):
        """当前值是窗口内最低 → 分位 ≈ 0"""
        values = pd.Series([10.0, 15.0, 20.0, 25.0, 30.0])
        current = 10.0
        result = expanding_percentile(values, current)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_highest_value_returns_one(self):
        """当前值是窗口内最高 → 分位 ≈ 1"""
        values = pd.Series([10.0, 15.0, 20.0, 25.0, 30.0])
        current = 30.0
        result = expanding_percentile(values, current)
        assert result == pytest.approx(1.0, abs=0.01)

    def test_middle_value(self):
        """5 个值 [10,20,30,40,50]，current=30 → 第 50 分位"""
        values = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        current = 30.0
        result = expanding_percentile(values, current)
        assert result == pytest.approx(0.5, abs=0.05)

    def test_all_same_values(self):
        """全部相同的值 → 分位 = 0（最低=最高=当前值）"""
        values = pd.Series([5.0, 5.0, 5.0, 5.0])
        current = 5.0
        result = expanding_percentile(values, current)
        assert result == pytest.approx(0.0, abs=0.01)

    def test_two_values(self):
        values = pd.Series([10.0, 20.0])
        assert expanding_percentile(values, 10.0) == pytest.approx(0.0)
        assert expanding_percentile(values, 20.0) == pytest.approx(1.0)

    def test_single_value(self):
        """只有一个值 → 分位 = 0"""
        values = pd.Series([15.0])
        current = 15.0
        result = expanding_percentile(values, current)
        assert result == pytest.approx(0.0)

    def test_output_in_range(self):
        """随机输入 → 输出始终 ∈ [0, 1]"""
        np.random.seed(42)
        for _ in range(100):
            values = pd.Series(np.random.randn(200) * 20 + 30)
            current = np.random.randn() * 20 + 30
            result = expanding_percentile(values, current)
            assert 0.0 <= result <= 1.0


class TestPEPercentile:
    """PE 分位计算"""

    def test_returns_float(self):
        # 需要至少 TRADING_DAYS_PER_YEAR=242 个数据点
        pe_series = pd.Series(np.linspace(10, 30, 250))
        result = pe_percentile(pe_series, max_window_years=5)
        assert isinstance(result, float)

    def test_enough_data(self):
        """有足够数据时返回有效分位"""
        pe_series = pd.Series(np.linspace(10, 30, 300))
        result = pe_percentile(pe_series, max_window_years=5)
        assert 0.0 <= result <= 1.0

    def test_insufficient_data(self):
        """数据不足 1 年 → 返回 None"""
        pe_series = pd.Series([10.0, 12.0])  # 只有2天
        result = pe_percentile(pe_series, max_window_years=5)
        assert result is None

    def test_cutoff_by_years(self):
        """max_window_years 限制后数据仍不足 → None"""
        pe_series = pd.Series(np.random.randn(300))  # > 1 year
        result = pe_percentile(pe_series, max_window_years=5)
        # 300天 / 242 ≈ 1.24年 > 1，可计算
        assert result is not None


class TestPBPercentile:
    """PB 分位计算"""

    def test_returns_float(self):
        pb_series = pd.Series(np.linspace(0.5, 2.0, 250))
        result = pb_percentile(pb_series, max_window_years=5)
        assert isinstance(result, float)

    def test_negative_pb_handled(self):
        """PB 为负（破净严重） → 仍正常计算分位"""
        pb_series = pd.Series(
            np.concatenate([np.linspace(-0.5, 1.0, 150), np.linspace(1.0, 2.0, 100)])
        )
        result = pb_percentile(pb_series, max_window_years=5)
        assert result is not None
        assert 0.0 <= result <= 1.0
