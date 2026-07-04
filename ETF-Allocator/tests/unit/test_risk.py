"""
测试 risk/controller.py — 风险控制层。
风险不进评分，只调节仓位上限。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from src.risk.controller import effective_upper_limit


class TestEffectiveUpperLimit:
    """波动率 → 有效仓位上限"""

    def test_normal_vol_no_change(self):
        """白酒 60日波动率 18% < 30%阈值 → 上限保持 25%"""
        result = effective_upper_limit("白酒ETF", 0.18)
        assert result == 0.25

    def test_high_vol_reduces_cap(self):
        """白酒 60日波动率 35% > 30%阈值 → 上限从 25% 降到 20%"""
        result = effective_upper_limit("白酒ETF", 0.35)
        assert result == 0.20

    def test_kechuang_high_threshold(self):
        """科创50 波动率 35% < 40%阈值 → 不降上限（成长资产阈值更高）"""
        result = effective_upper_limit("科创50ETF", 0.35)
        assert result == 0.15

    def test_kechuang_exceeds_threshold(self):
        """科创50 波动率 45% > 40%阈值 → 上限从 15% 降到 10%"""
        result = effective_upper_limit("科创50ETF", 0.45)
        assert result == 0.10

    def test_bank_exceeds_threshold(self):
        """银行 波动率 30% > 25%阈值 → 上限从 30% 降到 25%"""
        result = effective_upper_limit("银行ETF", 0.30)
        assert result == 0.25

    def test_bond_no_vol_constraint(self):
        """v1.3: 国债已从RISK_CONTROL移除，不受波动率控制"""
        result = effective_upper_limit("国债ETF", 0.50)
        assert result is None  # 不在RISK_CONTROL中，返回None

    def test_none_vol_no_change(self):
        """波动率数据缺失 → 保持常态上限"""
        result = effective_upper_limit("白酒ETF", None)
        assert result == 0.25

    def test_unknown_asset_returns_none(self):
        result = effective_upper_limit("不存在的ETF", 0.20)
        assert result is None

    def test_upper_never_below_zero(self):
        """任何情况下有效上限 ≥ 0"""
        for asset in ["白酒ETF", "银行ETF", "红利ETF", "沪深300ETF", "科创50ETF", "国债ETF"]:
            for vol in [0.05, 0.20, 0.50, 1.00, None]:
                cap = effective_upper_limit(asset, vol)
                if cap is not None:
                    assert cap >= 0.0, f"{asset} with vol={vol} got cap={cap}"

    def test_output_type(self):
        result = effective_upper_limit("白酒ETF", 0.20)
        assert isinstance(result, float)
