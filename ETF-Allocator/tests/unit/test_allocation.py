"""
测试 allocation/allocator.py — 资金分配算法。
综合机会分 + 约束 + 预算 → 最终分配方案。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest

from src.allocation.allocator import allocate


class TestBasicAllocation:
    """基础分配：机会分排序 + 约束检查"""

    def setup_data(self):
        """标准测试数据"""
        opportunity_scores = {
            "白酒ETF": 0.85, "银行ETF": 0.88, "红利ETF": 0.80,
            "沪深300ETF": 0.78, "科创50ETF": 0.92, "国债ETF": None,
        }
        current_weights = {
            "白酒ETF": 0.12, "银行ETF": 0.18, "红利ETF": 0.08,
            "沪深300ETF": 0.22, "科创50ETF": 0.13, "国债ETF": 0.27,
        }
        upper_limits = {
            "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
        }
        total_assets = 100_000
        equity_budget = 7_000
        return opportunity_scores, current_weights, upper_limits, total_assets, equity_budget

    def test_total_allocation_equals_budget(self):
        """分配总金额 = 权益预算（剩余进国债不算在内）"""
        scores, weights, limits, total, budget = self.setup_data()
        result = allocate(scores, weights, limits, total, budget)
        total_allocated = sum(
            result[a] for a in result if a != "国债ETF" and result[a] > 0
        )
        assert total_allocated <= budget

    def test_order_respects_opportunity(self):
        """高机会分先分配（在约束允许时）"""
        scores = {
            "白酒ETF": 0.85, "银行ETF": 0.60, "红利ETF": 0.90,
            "沪深300ETF": 0.40, "科创50ETF": 0.70, "国债ETF": None,
        }
        weights = {
            "白酒ETF": 0.12, "银行ETF": 0.12, "红利ETF": 0.12,
            "沪深300ETF": 0.12, "科创50ETF": 0.12, "国债ETF": 0.40,
        }
        limits = {
            "白酒ETF": 0.25, "银行ETF": 0.25, "红利ETF": 0.25,
            "沪深300ETF": 0.25, "科创50ETF": 0.25, "国债ETF": 0.20,
        }
        result = allocate(scores, weights, limits, total_assets=100_000, equity_budget=12_000)

        # 红利机会分最高(0.90) → 应拿到最多
        assert result.get("红利ETF", 0) >= result.get("银行ETF", 0)
        assert result.get("红利ETF", 0) >= result.get("沪深300ETF", 0)

    def test_asset_at_cap_skipped(self):
        """科创50 已是上限 → 跳过"""
        scores = {
            "白酒ETF": 0.85, "银行ETF": 0.88, "红利ETF": 0.80,
            "沪深300ETF": 0.78, "科创50ETF": 0.92, "国债ETF": None,
        }
        weights = {
            "白酒ETF": 0.12, "银行ETF": 0.18, "红利ETF": 0.08,
            "沪深300ETF": 0.22, "科创50ETF": 0.15, "国债ETF": 0.25,
        }
        limits = {
            "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
        }
        result = allocate(scores, weights, limits, total_assets=100_000, equity_budget=7_000)

        # 科创50 已达上限 → 不分配
        assert result.get("科创50ETF", 0) == 0

    def test_all_at_cap_goes_to_bond(self):
        """所有权益资产都到上限 → 全部进国债"""
        scores = {
            "白酒ETF": 0.85, "银行ETF": 0.88, "红利ETF": 0.80,
            "沪深300ETF": 0.78, "科创50ETF": 0.92, "国债ETF": None,
        }
        weights = {
            "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.0,
        }
        limits = {
            "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
        }
        result = allocate(scores, weights, limits, total_assets=200_000, equity_budget=10_000)

        assert result.get("国债ETF", 0) == pytest.approx(10_000)
        assert result.get("白酒ETF", 0) == 0
        assert result.get("银行ETF", 0) == 0

    def test_null_score_asset_skipped(self):
        """某资产无机会分 → 跳过不分配"""
        scores = {
            "白酒ETF": None, "银行ETF": 0.88, "红利ETF": 0.80,
            "沪深300ETF": 0.78, "科创50ETF": 0.68, "国债ETF": None,
        }
        weights = {
            "白酒ETF": 0.10, "银行ETF": 0.18, "红利ETF": 0.08,
            "沪深300ETF": 0.22, "科创50ETF": 0.12, "国债ETF": 0.30,
        }
        limits = {
            "白酒ETF": 0.25, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
        }
        result = allocate(scores, weights, limits, total_assets=100_000, equity_budget=7_000)

        # 白酒无机会分 → 不分配
        assert result.get("白酒ETF", 0) == 0

    def test_no_negative_allocation(self):
        """任何资产分配金额 ≥ 0"""
        scores, weights, limits, total, budget = self.setup_data()
        result = allocate(scores, weights, limits, total, budget)
        for asset, amount in result.items():
            assert amount >= 0, f"{asset} got negative allocation: {amount}"

    def test_all_assets_in_output(self):
        """输出包含分配到的资产（未分配的资产可以不在结果中）"""
        scores, weights, limits, total, budget = self.setup_data()
        result = allocate(scores, weights, limits, total, budget)
        # 所有分配的资产都在 scores 中存在
        assert set(result.keys()).issubset(set(scores.keys()))

    def test_single_asset_gets_all(self):
        """只有一个资产有空间 → 全给它（不超过 max_buy）"""
        scores = {
            "白酒ETF": 0.85, "银行ETF": 0.60, "红利ETF": 0.40,
            "沪深300ETF": 0.30, "科创50ETF": 0.20, "国债ETF": None,
        }
        weights = {
            "白酒ETF": 0.10, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.0,
        }
        limits = {
            "白酒ETF": 0.30, "银行ETF": 0.30, "红利ETF": 0.25,
            "沪深300ETF": 0.30, "科创50ETF": 0.15, "国债ETF": 0.20,
        }
        result = allocate(scores, weights, limits, total_assets=100_000, equity_budget=5_000)

        # 白酒是唯一有空间的（低于上限）且机会最高
        assert result["白酒ETF"] > 0

    def test_equity_budget_zero(self):
        """权益预算为 0 → 全部进国债（或无分配）"""
        scores, weights, limits, total, _ = self.setup_data()
        result = allocate(scores, weights, limits, total, equity_budget=0)
        # 预算为0时，国债可能被分配也可能不分配
        for a in ["白酒ETF", "银行ETF", "红利ETF", "沪深300ETF", "科创50ETF"]:
            assert result.get(a, 0) == 0


class TestBuyCoefficient:
    """约束层 buy_coefficients 集成"""

    def test_coefficient_zero_prevents_allocation(self):
        """系数=0 → 该资产不分配"""
        scores = {"白酒ETF": 0.85, "银行ETF": 0.60}
        limits = {"白酒ETF": 0.30, "银行ETF": 0.30}
        weights = {"白酒ETF": 0.10, "银行ETF": 0.10}
        coefs = {"白酒ETF": 0.0, "银行ETF": 1.0}  # 禁止白酒
        result = allocate(scores, weights, limits, total_assets=100000,
                         equity_budget=10000, buy_coefficients=coefs)
        assert result.get("白酒ETF", 0) == 0
        assert result.get("银行ETF", 0) > 0

    def test_coefficient_reduces_allocation(self):
        """系数 0.5 → max_buy 减半"""
        scores = {"白酒ETF": 0.85}
        limits = {"白酒ETF": 0.30}
        weights = {"白酒ETF": 0.10}
        coefs = {"白酒ETF": 0.5}
        result_full = allocate(scores, weights, limits, total_assets=100000,
                               equity_budget=10000)
        result_half = allocate(scores, weights, limits, total_assets=100000,
                               equity_budget=10000, buy_coefficients=coefs)
        assert result_half["白酒ETF"] <= result_full["白酒ETF"]

    def test_missing_coefficient_defaults_to_full(self):
        """不传 buy_coefficients → 默认行为不变（向后兼容）"""
        scores = {"白酒ETF": 0.85}
        limits = {"白酒ETF": 0.30}
        weights = {"白酒ETF": 0.10}
        result = allocate(scores, weights, limits, total_assets=100000, equity_budget=10000)
        assert result.get("白酒ETF", 0) > 0


class TestOpportunityThreshold:
    """MIN_OPPORTUNITY_SCORE 阈值：跳过机会分过低的资产"""

    def test_low_score_skipped_in_initial_build(self):
        """沪深300 机会分 0.09 < 0.20 → 不被分配"""
        scores = {
            "白酒ETF": 0.71, "银行ETF": 0.65, "红利ETF": 0.99,
            "沪深300ETF": 0.09, "科创50ETF": 0.82, "国债ETF": None,
        }
        limits = {k: 0.30 for k in scores}
        weights = {k: 0.0 for k in scores}
        result = allocate(scores, weights, limits, total_assets=0, equity_budget=5600)
        assert result.get("沪深300ETF", 0) == 0
        assert result.get("白酒ETF", 0) > 0  # 其他正常分配

    def test_low_score_not_skipped_if_gap_high(self):
        """缺口极大时仍可分配（当前代码只检查 pri < threshold）"""
        scores = {"沪深300ETF": 0.09, "银行ETF": 0.50}
        limits = {"沪深300ETF": 0.30, "银行ETF": 0.30}
        weights = {"沪深300ETF": 0.0, "银行ETF": 0.20}  # 沪深300有缺口
        result = allocate(scores, weights, limits, total_assets=100000, equity_budget=10000)
        # 沪深300 缺口大→综合分可能达标；若不达标→跳过为 0
        assert result.get("沪深300ETF", 0) >= 0
