"""
tests/unit/test_scoring_sigmoid.py — 评分层 sigmoid 映射测试。
"""
import pytest
import numpy as np


def _sigmoid(x):
    """1 / (1 + exp(-x))"""
    return 1.0 / (1.0 + np.exp(-x))


class TestSigmoid:
    """sigmoid 函数将 z-score 映射到 (0,1)"""

    def test_sigmoid_zero_is_half(self):
        assert abs(_sigmoid(0.0) - 0.5) < 0.001

    def test_sigmoid_positive_large_approaches_one(self):
        assert _sigmoid(3.0) > 0.95

    def test_sigmoid_negative_large_approaches_zero(self):
        assert _sigmoid(-3.0) < 0.05

    def test_sigmoid_symmetric(self):
        """sigmoid(-x) = 1 - sigmoid(x)"""
        for x in [0.5, 1.0, 2.0]:
            assert abs(_sigmoid(-x) - (1 - _sigmoid(x))) < 0.001

    def test_sigmoid_monotonic(self):
        """sigmoid 单调递增"""
        vals = [_sigmoid(x) for x in [-2, -1, 0, 1, 2]]
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i + 1]

    def test_sigmoid_output_range(self):
        """输出在 (0,1) 严格开区间"""
        for x in [-5.0, -2.0, 0.0, 2.0, 5.0]:
            v = _sigmoid(x)
            assert 0.0 < v < 1.0
