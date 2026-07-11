"""
测试 regime/thermometer.py — 市场温度计（4档分级 + 不一致冻结）。

ds.v1.2 §七 设计：
  双 <60%  → 权益 100%
  双 60-80% → 权益 70%
  双 80-90% → 权益 40%
  双 >90%  → 权益 30%
  不一致    → 冻结上期比例
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from src.regime.thermometer import equity_ratio, reset_persistence


class TestEquityRatio:
    """4档分级温度计"""

    # ── 四档各自测试 ──

    def test_both_under_60_full_equity(self):
        reset_persistence()
        r, bond = equity_ratio(0.30, 0.50)
        assert r == 1.00
        assert bond == 0.00

    def test_both_60_to_80_mild_cool(self):
        reset_persistence()
        r, bond = equity_ratio(0.65, 0.72)
        assert r == 0.70
        assert bond == pytest.approx(0.30)

    def test_both_80_to_90_strong_cool(self):
        reset_persistence()
        r, bond = equity_ratio(0.85, 0.88)
        assert r == 0.40
        assert bond == pytest.approx(0.60)

    def test_both_above_90_max_cool(self):
        reset_persistence()
        r, bond = equity_ratio(0.93, 0.97)
        assert r == 0.30
        assert bond == pytest.approx(0.70)

    # ── 边界值 ──

    def test_exact_60_boundary(self):
        """精确 0.60 → 属于 [0.60, 0.80) 档 → 70%"""
        reset_persistence()
        r, _ = equity_ratio(0.60, 0.60)
        assert r == 0.70

    def test_exact_80_boundary(self):
        """精确 0.80 → 属于 [0.80, 0.90) 档 → 40%"""
        reset_persistence()
        r, _ = equity_ratio(0.80, 0.80)
        assert r == 0.40

    def test_exact_90_boundary(self):
        """精确 0.90 → 属于 >=0.90 档 → 30%"""
        reset_persistence()
        r, _ = equity_ratio(0.90, 0.90)
        assert r == 0.30

    # ── 不一致冻结 ──

    def test_disagreement_freezes_last(self):
        """不一致时返回上次记住的比例"""
        reset_persistence()
        # 先建立一致状态
        equity_ratio(0.30, 0.40)  # 双<60% → 100%
        # 不一致 → 冻结上次的 100%
        r, bond = equity_ratio(0.95, 0.50)
        assert r == 1.00
        assert bond == 0.00

    def test_disagreement_first_call_default_full(self):
        """首调用不一致 → 默认 100%。"""
        reset_persistence()
        r, bond = equity_ratio(0.95, 0.50)
        assert r == 1.00
        assert bond == pytest.approx(0.00)

    def test_freeze_then_reagree(self):
        """冻结后双指标重新一致 → 用新档位"""
        reset_persistence()
        equity_ratio(0.30, 0.40)   # 100%
        equity_ratio(0.95, 0.50)   # 不一致 → 冻结 100%
        r, bond = equity_ratio(0.93, 0.97)  # 重新一致 >90% → 30%
        assert r == 0.30

    # ── 缺失数据 ──

    def test_none_freezes(self):
        """任一 None → 冻结上次"""
        reset_persistence()
        equity_ratio(0.30, 0.40)   # 100%
        r, bond = equity_ratio(None, 0.95)
        assert r == 1.00

    def test_none_first_call_default(self):
        """首调用 None → 默认 100%。"""
        reset_persistence()
        r, bond = equity_ratio(None, 0.95)
        assert r == 1.00

    # ── 类型 ──

    def test_ratio_is_float(self):
        reset_persistence()
        r, bond = equity_ratio(0.91, 0.91)
        assert isinstance(r, float)
        assert isinstance(bond, float)


class TestResetPersistence:
    """reset_persistence() 清理状态"""

    def test_reset_clears_state(self):
        equity_ratio(0.30, 0.40)  # 100%
        reset_persistence()
        # 重置后首调用，不一致 → 默认 100%
        r, _ = equity_ratio(0.95, 0.50)
        assert r == 1.00

    def test_reset_then_new_call_is_first(self):
        reset_persistence()
        equity_ratio(0.85, 0.88)  # 40%
        reset_persistence()
        # 重置后不一致 → 默认 100%
        r, _ = equity_ratio(0.95, 0.50)
        assert r == 1.00
