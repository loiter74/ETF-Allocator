"""
测试 scoring/engine.py — 因子 → 统一 [0,1] 机会分。

规则：风险不进评分；国债不参与评分；输出永远 ∈ [0,1]。
ds.v1.2 §六：银行用真实 z-score + sigmoid（非分位线性映射）。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import numpy as np

from src.scoring.engine import (
    sigmoid,
    score_baijiu,
    score_bank,
    score_dividend,
    score_hs300,
    score_kechuang,
    score_all,
)


class TestSigmoid:
    """sigmoid 基础函数"""

    def test_zero_input_half(self):
        assert sigmoid(0.0) == pytest.approx(0.50)

    def test_positive_above_half(self):
        assert sigmoid(2.0) > 0.85

    def test_negative_below_half(self):
        assert sigmoid(-2.0) < 0.15

    def test_large_positive_near_one(self):
        assert sigmoid(10.0) > 0.999

    def test_large_negative_near_zero(self):
        assert sigmoid(-10.0) < 0.001


class TestScoreBaijiu:
    """白酒：1 - PE分位"""

    def test_low_pe_high_score(self):
        assert score_baijiu(0.15) == pytest.approx(0.85)

    def test_high_pe_low_score(self):
        assert score_baijiu(0.90) == pytest.approx(0.10)

    def test_none_input_returns_none(self):
        assert score_baijiu(None) is None

    def test_output_in_range(self):
        for pe in [0.0, 0.25, 0.50, 0.75, 1.0]:
            result = score_baijiu(pe)
            assert 0.0 <= result <= 1.0


class TestScoreBank:
    """
    银行：sigmoid(0.5 * PB_zscore + 0.5 * 股息_zscore)

    ds.v1.2 §五·银行：
      z = (当前值 - 均值) / std，然后等权 + sigmoid。
      z > 0 → 当前值高于历史平均（便宜/高股息）→ sigmoid > 0.5
      z < 0 → 当前值低于历史平均（贵/低股息）→ sigmoid < 0.5
    """

    def test_both_positive_zscores_high_score(self):
        """z > 0 → sigmoid > 0.5"""
        result = score_bank(2.0, 1.5)  # PB偏高(=便宜), 股息偏高(=好)
        assert result is not None
        assert result > 0.80  # sigmoid(1.75) ≈ 0.85

    def test_both_negative_zscores_low_score(self):
        """z < 0 → sigmoid < 0.5"""
        result = score_bank(-2.0, -1.5)
        assert result is not None
        assert result < 0.20  # sigmoid(-1.75) ≈ 0.15

    def test_neutral_zscores_mid_score(self):
        """z = 0 → sigmoid = 0.5"""
        result = score_bank(0.0, 0.0)
        assert result == pytest.approx(0.50)

    def test_none_input_returns_none(self):
        assert score_bank(None, 1.0) is None
        assert score_bank(1.0, None) is None

    def test_output_in_range(self):
        np.random.seed(42)
        for _ in range(100):
            z_pb = np.random.normal(0, 2)
            z_div = np.random.normal(0, 2)
            result = score_bank(z_pb, z_div)
            assert result is not None
            assert 0.0 <= result <= 1.0

    def test_extreme_low_score(self):
        """极端便宜 → 接近 1"""
        result = score_bank(4.0, 4.0)
        assert result > 0.97  # sigmoid(4) ≈ 0.982

    def test_extreme_high_score(self):
        """极端贵 → 接近 0"""
        result = score_bank(-4.0, -4.0)
        assert result < 0.03


class TestScoreDividend:
    """红利：股息率分位（越高越好）"""

    def test_high_div_high_score(self):
        assert score_dividend(0.90) == pytest.approx(0.90)

    def test_low_div_low_score(self):
        assert score_dividend(0.10) == pytest.approx(0.10)

    def test_none_returns_none(self):
        assert score_dividend(None) is None


class TestScoreHS300:
    """沪深300：1 - PE分位"""

    def test_low_pe_high_score(self):
        assert score_hs300(0.20) == pytest.approx(0.80)

    def test_none_returns_none(self):
        assert score_hs300(None) is None


class TestScoreKeChuang:
    """科创50：动量分位 × 趋势开关(ds.v1.2: OFF时减半)"""

    def test_trend_on_full_score(self):
        assert score_kechuang(0.92, 1.0) == pytest.approx(0.92)

    def test_trend_off_halved(self):
        assert score_kechuang(0.92, 0.50) == pytest.approx(0.46)

    def test_trend_off_zero_momentum_zero_score(self):
        assert score_kechuang(0.0, 0.50) == pytest.approx(0.0)

    def test_none_returns_none(self):
        assert score_kechuang(None, 1.0) is None
        assert score_kechuang(0.5, None) is None


class TestScoreAll:
    """批量评分 — ds.v1.2 银行用 z-score"""

    def test_all_assets_present(self):
        """输出包含所有 6 个资产"""
        factors = {
            "白酒ETF": {"pe_percentile": 0.15},
            "银行ETF": {"pb_zscore": 2.0, "dividend_zscore": 1.5},
            "红利ETF": {"dividend_percentile": 0.70},
            "沪深300ETF": {"pe_percentile": 0.55},
            "科创50ETF": {"momentum_percentile": 0.68, "trend_multiplier": 1.0},
            "国债ETF": {},
        }
        scores = score_all(factors)
        assert set(scores.keys()) == set(factors.keys())

    def test_guozhai_always_none(self):
        """国债不参与评分 → 永远 None"""
        scores = score_all({"国债ETF": {}})
        assert scores["国债ETF"] is None

    def test_all_scores_in_range(self):
        """100组随机因子 → 所有结果 ∈ [0,1] 或 None"""
        np.random.seed(42)
        for _ in range(100):
            pe_b = np.random.random()
            z_pb = np.random.normal(0, 2)
            z_div = np.random.normal(0, 2)
            factors = {
                "白酒ETF": {"pe_percentile": pe_b},
                "银行ETF": {"pb_zscore": z_pb, "dividend_zscore": z_div},
                "红利ETF": {"dividend_percentile": np.random.random()},
                "沪深300ETF": {"pe_percentile": np.random.random()},
                "科创50ETF": {
                    "momentum_percentile": np.random.random(),
                    "trend_multiplier": np.random.choice([0.50, 1.00]),
                },
                "国债ETF": {},
            }
            scores = score_all(factors)
            for asset, s in scores.items():
                if asset == "国债ETF":
                    assert s is None
                else:
                    assert 0.0 <= s <= 1.0

    def test_risk_data_not_used(self):
        """评分层不读取也不使用波动率/回撤数据"""
        factors = {
            "白酒ETF": {
                "pe_percentile": 0.15,
                "volatility": 0.25,
                "max_drawdown": -0.15,
            }
        }
        scores = score_all(factors)
        assert scores["白酒ETF"] == pytest.approx(0.85)
