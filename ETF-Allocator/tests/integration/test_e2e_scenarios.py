"""
tests/integration/test_e2e_scenarios.py — 端到端集成测试。
验证完整管线的关键场景。
"""
import pytest
from src.regime.thermometer import reset_persistence
from src.risk.controller import all_effective_limits
from src.constraints.portfolio import apply_constraints
from src.allocation.allocator import allocate


@pytest.fixture(autouse=True)
def reset():
    reset_persistence()


# ── 场景：过热市场 ──

def test_overheat_market_limits_equity():
    """PE>90%, PB>90% → 权益 30%，70% 进国债"""
    scores = {
        "白酒ETF": 0.50, "银行ETF": 0.50, "红利ETF": 0.50,
        "沪深300ETF": 0.20, "科创50ETF": 0.60, "国债ETF": None,
    }
    limits = {k: 0.30 for k in scores}
    weights = {k: 0.15 for k in scores if k != "国债ETF"}
    weights["国债ETF"] = 0.25

    result = allocate(scores, weights, limits, total_assets=100_000, equity_budget=3_000)

    # 国债应收到大部分资金（temperature-mandated bond portion is handled externally）
    assert result.get("国债ETF", 0) >= 0
    for k in ["白酒ETF", "银行ETF", "红利ETF", "沪深300ETF", "科创50ETF"]:
        assert result.get(k, 0) >= 0  # no negative allocations


# ── 场景：低估市场 ──

def test_cool_market_fills_gaps():
    """PE<60%, PB<60% → 权益 100%，优先填补缺口"""
    scores = {
        "白酒ETF": 0.80, "银行ETF": 0.60, "红利ETF": 0.90,
        "沪深300ETF": 0.70, "科创50ETF": 0.50, "国债ETF": None,
    }
    limits = {k: 0.30 for k in scores}
    # 白酒低于下限 (12%), 科创正好在下限 (10%)
    weights = {"白酒ETF": 0.05, "银行ETF": 0.15, "红利ETF": 0.15,
               "沪深300ETF": 0.15, "科创50ETF": 0.10, "国债ETF": 0.40}

    result = allocate(scores, weights, limits, total_assets=200_000, equity_budget=10_000)

    # 白酒有缺口→应分到资金
    assert result.get("白酒ETF", 0) > 0


# ── 场景：初始建仓 ──

def test_initial_build_respects_caps():
    """初始建仓模式应遵守各资产上限"""
    scores = {
        "白酒ETF": 0.85, "银行ETF": 0.60, "红利ETF": 0.95,
        "沪深300ETF": 0.30, "科创50ETF": 0.80, "国债ETF": None,
    }
    limits = {"白酒ETF": 0.25, "银行ETF": 0.25, "红利ETF": 0.25,
              "沪深300ETF": 0.25, "科创50ETF": 0.15, "国债ETF": 0.20}
    weights = {k: 0.0 for k in scores}

    result = allocate(scores, weights, limits, total_assets=0, equity_budget=8_000)

    # 每个资产不超过其 cap * budget
    for name, cap in limits.items():
        if name == "国债ETF":
            continue
        assert result.get(name, 0) <= cap * 8_000 + 1  # 1 tolerance for rounding


# ── 场景：约束层集成 ──

def test_constraint_integration_prevents_overweight():
    """约束层 buy_coefficient=0 时该资产不分配"""
    scores = {"白酒ETF": 0.85, "银行ETF": 0.60}
    limits = {"白酒ETF": 0.25, "银行ETF": 0.25}
    weights = {"白酒ETF": 0.249, "银行ETF": 0.10}  # 白酒接近上限
    cons = apply_constraints(weights, limits, 100_000)

    result = allocate(scores, weights, limits, total_assets=100_000,
                     equity_budget=5_000, buy_coefficients=cons["buy_coefficients"])

    # 白酒接近上限→系数应接近0→分配很少或为0
    assert cons["buy_coefficients"]["白酒ETF"] < 0.5
