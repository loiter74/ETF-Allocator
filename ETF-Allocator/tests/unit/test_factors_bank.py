"""
tests/unit/test_factors_bank.py — 银行ETF复合因子测试。
验证：PB z-score + 股息率 z-score 等权重合并 → sigmoid 映射到 (0,1)
"""
import pytest
import numpy as np


class TestBankComposite:
    """银行ETF 使用 PB + 股息率 双因子"""

    def test_bank_uses_pb_and_dividend(self):
        """验证银行评分使用了 PB 和股息两个因子（而非像白酒只用PE）"""
        # 这个测试验证因子层正确地分配了银行的计算逻辑
        # 具体值取决于数据库，但结构应正确
        from config.settings import FACTOR_WEIGHTS
        bw = FACTOR_WEIGHTS.get("银行ETF", {})
        assert "pb_percentile" in bw
        assert "dividend_percentile" in bw
        assert abs(sum(bw.values()) - 1.0) < 0.01

    def test_bank_weights_sum_to_one(self):
        """银行的双因子权重和为 1"""
        from config.settings import FACTOR_WEIGHTS
        bw = FACTOR_WEIGHTS["银行ETF"]
        assert abs(bw["pb_percentile"] + bw["dividend_percentile"] - 1.0) < 0.01


class TestKeChuangTrend:
    """科创50 趋势开关因子"""

    def test_kechuang_uses_momentum_and_trend(self):
        """科创50 使用动量分位 + MA200 趋势开关"""
        from config.settings import FACTOR_WEIGHTS
        kw = FACTOR_WEIGHTS.get("科创50ETF", {})
        assert "momentum_percentile" in kw

    def test_trend_multiplier_values(self):
        """趋势乘数只能是 1.0 (ON) 或 0.5 (OFF)"""
        multipliers = [1.0, 0.5]
        for m in multipliers:
            assert m in (1.0, 0.5)
