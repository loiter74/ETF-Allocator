"""
测试 constraints/portfolio.py — 组合约束层（最关键的模块）。
单标的带 + 因子组带 + 惩罚函数 → 可买系数 + 最大买入金额。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from src.constraints.portfolio import (
    buy_coefficient,
    max_buy_amount,
    group_weight,
    check_factor_group_constraint,
    apply_constraints,
)


class TestBuyCoefficient:
    """惩罚函数：权重 → 可买系数 [0, 1]"""

    def test_full_below_buffer(self):
        """当前权重 8%，上限 25%，buffer=5% → 8% < 20% → coef=1.0"""
        assert buy_coefficient(0.08, 0.25, buffer=0.05) == 1.0

    def test_partial_in_buffer(self):
        """当前权重 22%，上限 25%，buffer=5% → (25-22)/5 = 0.6"""
        assert buy_coefficient(0.22, 0.25, buffer=0.05) == pytest.approx(0.6)

    def test_at_upper_limit(self):
        assert buy_coefficient(0.25, 0.25, buffer=0.05) == 0.0

    def test_exceeds_upper_limit(self):
        """权重 26% > 上限 25% → coef=0"""
        assert buy_coefficient(0.26, 0.25, buffer=0.05) == 0.0

    def test_at_buffer_boundary(self):
        """正好在缓冲带边缘：20% = 25% - 5% → (25-20)/5 = 1.0"""
        assert buy_coefficient(0.20, 0.25, buffer=0.05) == pytest.approx(1.0)

    def test_just_above_buffer(self):
        """21% → (25-21)/5 = 0.8"""
        assert buy_coefficient(0.21, 0.25, buffer=0.05) == pytest.approx(0.8)

    def test_zero_buffer(self):
        """buffer=0 → 硬开关：<上限=1，≥上限=0"""
        assert buy_coefficient(0.24, 0.25, buffer=0.0) == 1.0
        assert buy_coefficient(0.25, 0.25, buffer=0.0) == 0.0

    def test_negative_weight(self):
        """不应出现负权重，但即使出现也不崩"""
        result = buy_coefficient(-0.05, 0.25, buffer=0.05)
        assert result == 1.0  # 远低于上限


class TestMaxBuyAmount:
    """最大可买金额计算"""

    def test_has_room(self):
        """当前持仓 12 万，总资产 100 万，上限 25% → 最多买 25-12=13 万"""
        assert max_buy_amount(120_000, 1_000_000, 0.25) == 130_000

    def test_no_room(self):
        """当前持仓 30 万，总资产 100 万，上限 25% → max_buy = 0"""
        assert max_buy_amount(300_000, 1_000_000, 0.25) == 0.0

    def test_exceeds_upper(self):
        """当前持仓 30 万 > 25 万上限 → max_buy = 0"""
        assert max_buy_amount(300_000, 1_000_000, 0.25) == 0.0

    def test_never_negative(self):
        """无论输入什么，max_buy 永不 < 0"""
        assert max_buy_amount(500_000, 100_000, 0.25) == 0.0
        assert max_buy_amount(0, 100_000, 0.25) >= 0.0

    def test_bond_no_max_buy_constraint(self):
        """国债的上限计算同样适用公式"""
        result = max_buy_amount(50_000, 1_000_000, 0.20)
        assert result == 150_000


class TestGroupWeight:
    """因子组权重聚合"""

    def test_value_group_excludes_growth(self):
        weights = {
            "白酒ETF": 0.20, "银行ETF": 0.20, "红利ETF": 0.10,
            "沪深300ETF": 0.05, "科创50ETF": 0.15, "国债ETF": 0.30,
        }
        assert group_weight(weights, "VALUE") == pytest.approx(0.20+0.20+0.10)
        assert group_weight(weights, "CORE") == pytest.approx(0.05)

    def test_growth_group(self):
        weights = {
            "白酒ETF": 0.15, "科创50ETF": 0.12, "国债ETF": 0.10,
            "银行ETF": 0.15, "红利ETF": 0.10, "沪深300ETF": 0.38,
        }
        assert group_weight(weights, "GROWTH") == 0.12


class TestFactorGroupConstraint:
    """因子组上限检查"""

    def test_value_group_ok(self):
        weights = {
            "白酒ETF": 0.15, "银行ETF": 0.10, "红利ETF": 0.05,
            "沪深300ETF": 0.10, "科创50ETF": 0.08, "国债ETF": 0.52,
        }
        # VALUE = 15+10+5+10 = 40% < 60% → OK
        allocations = {
            "白酒ETF": 2000, "银行ETF": 1500, "红利ETF": 1000,
            "沪深300ETF": 1500, "科创50ETF": 1000, "国债ETF": 3000,
        }
        result = check_factor_group_constraint(allocations, weights, total_assets=100_000)
        assert result["status"] == "ok"

    def test_value_group_over_cap(self):
        """白酒+银行+红利 VALUE组 65% > 60% 上限 → 需缩减"""
        weights = {
            "白酒ETF": 0.25, "银行ETF": 0.25, "红利ETF": 0.15,
            "沪深300ETF": 0.05, "科创50ETF": 0.05, "国债ETF": 0.25,
        }
        allocations = {
            "白酒ETF": 3000, "银行ETF": 3000, "红利ETF": 2000,
            "沪深300ETF": 1500, "科创50ETF": 500, "国债ETF": 0,
        }
        result = check_factor_group_constraint(allocations, weights, total_assets=100_000)
        assert result["status"] == "scale_down"
        assert result["group"] == "VALUE"
        # 缩减后 VALUE 组合计应 ≤ 60%
        scaled = result["scaled_allocations"]
        value_sum = sum(
            scaled[a] for a in ["白酒ETF", "银行ETF", "红利ETF"]
        )
        # 60% × 100000 = 60000
        assert value_sum <= 60000

    def test_growth_group_over_cap(self):
        weights = {
            "白酒ETF": 0.10, "科创50ETF": 0.18, "国债ETF": 0.10,
            "银行ETF": 0.20, "红利ETF": 0.12, "沪深300ETF": 0.30,
        }
        allocations = {
            "白酒ETF": 0, "科创50ETF": 5000, "国债ETF": 0,
            "银行ETF": 0, "红利ETF": 0, "沪深300ETF": 0,
        }
        result = check_factor_group_constraint(allocations, weights, total_assets=30_000)
        # GROWTH: 0.18 × 30000 = 5400, cap = 15% × 30000 = 4500
        assert result["status"] == "scale_down"
        assert result["group"] == "GROWTH"


class TestApplyConstraints:
    """综合约束应用"""

    def test_all_assets_have_room(self):
        current_weights = {
            "白酒ETF": 0.12, "银行ETF": 0.18, "红利ETF": 0.08,
            "沪深300ETF": 0.22, "科创50ETF": 0.05, "国债ETF": 0.10,
        }
        total_assets = 100_000
        upper_limits = {
            "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
        }
        result = apply_constraints(current_weights, upper_limits, total_assets)

        # 所有资产都在上限以下 → 所有 coef = 1.0
        for asset in current_weights:
            assert result["buy_coefficients"][asset] == 1.0

    def test_one_at_cap_others_free(self):
        current_weights = {
            "白酒ETF": 0.12, "银行ETF": 0.18, "红利ETF": 0.08,
            "沪深300ETF": 0.22, "科创50ETF": 0.15, "国债ETF": 0.25,
        }
        upper_limits = {
            "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
        }
        result = apply_constraints(current_weights, upper_limits, total_assets=100_000)

        assert result["buy_coefficients"]["科创50ETF"] == 0.0
        assert result["buy_coefficients"]["国债ETF"] == 0.0
        assert result["buy_coefficients"]["白酒ETF"] == 1.0
        assert result["buy_coefficients"]["银行ETF"] == 1.0

    def test_max_buy_positive_for_underweight(self):
        """低配资产 → max_buy > 0"""
        result = apply_constraints(
            {"白酒ETF": 0.08},
            {"白酒ETF": 0.25},
            total_assets=100_000,
        )
        assert result["max_buy"]["白酒ETF"] == 17_000

    def test_max_buy_zero_for_overweight(self):
        result = apply_constraints(
            {"白酒ETF": 0.30},
            {"白酒ETF": 0.25},
            total_assets=100_000,
        )
        assert result["max_buy"]["白酒ETF"] == 0.0

    def test_output_keys_complete(self):
        result = apply_constraints(
            {"白酒ETF": 0.12},
            {"白酒ETF": 0.25},
            total_assets=100_000,
        )
        assert "buy_coefficients" in result
        assert "max_buy" in result
        assert "group_weights" in result
        assert "group_caps" in result
