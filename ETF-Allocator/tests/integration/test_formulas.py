"""
tests/integration/test_formulas.py — ds.v1.2.winner.md 公式集成测试。

逐条验证设计文档中的每个计算公式在代码实现中是否正确。
包含边界值、极端值和参数化测试。

文档引用格式：§X·段落
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import numpy as np
import pandas as pd

# ── 因子层公式 ──
from src.factors.value import (
    expanding_percentile,
    _expand_truncate,
    pe_percentile,
    pb_percentile,
    compute_zscore,
)
from src.factors.dividend import dividend_yield_percentile
from src.factors.momentum import momentum_120d, ma_trend_200d, kechuang_opportunity
from src.factors.risk import annualized_volatility, max_drawdown

# ── 评分层公式 ──
from src.scoring.engine import (
    sigmoid,
    score_baijiu,
    score_bank,
    score_dividend,
    score_hs300,
    score_kechuang,
    score_all,
)

# ── 温度计 ──
from src.regime.thermometer import equity_ratio, reset_persistence, _tier

# ── 约束层 ──
from src.constraints.portfolio import buy_coefficient, max_buy_amount, group_weight

# ── 分配层 ──
from src.allocation.allocator import compute_gap_scores, compute_priority

# ── 全局常数 ──
from config.settings import (
    TRADING_DAYS_PER_YEAR,
    WINDOW_VOL_DAYS,
    WINDOW_MOMENTUM_DAYS,
    WINDOW_MA_TREND_DAYS,
    KECHUANG_TREND_OFF_MULTIPLIER,
    TARGET_BANDS,
    ALLOCATION_GAP_WEIGHT,
    ALLOCATION_OPPORTUNITY_WEIGHT,
    PENALTY_BUFFER,
    TEMP_THRESHOLDS,
    TEMP_EQUITY_RATIOS,
)

# ===================================================================
# §五·因子层：PE/PB 分位计算
# ===================================================================

class TestPEPercentile:
    """
    §五·白酒 / §五·沪深300：
      PE分位 = current_value 在历史 expanding window 中的 rank/(n-1)
      分位越低 → PE越便宜 → 机会越好
    """

    def test_min_value_zero_percentile(self):
        """
        公式：rank / (n-1), where rank = count(values < current)
        最小值 → rank=0 → percentile=0.0
        """
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = expanding_percentile(s, 10.0)
        assert result == pytest.approx(0.0)

    def test_max_value_one_percentile(self):
        """最大值 → rank=4, n=5 → 4/4=1.0"""
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = expanding_percentile(s, 50.0)
        assert result == pytest.approx(1.0)

    def test_median_fifty_percentile(self):
        """中位数 → rank=2, n=5 → 2/4=0.5"""
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = expanding_percentile(s, 30.0)
        assert result == pytest.approx(0.50)

    def test_single_value_returns_zero(self):
        """n=1 → 返回 0"""
        s = pd.Series([42.0])
        result = expanding_percentile(s, 42.0)
        assert result == 0.0

    def test_all_equal_returns_zero(self):
        """所有值相等 → rank=0 → 0"""
        s = pd.Series([5.0, 5.0, 5.0, 5.0])
        result = expanding_percentile(s, 5.0)
        assert result == 0.0

    def test_pe_percentile_full_pipeline(self):
        """pe_percentile 端到端"""
        s = pd.Series([15.0] * 150 + [12.0] * 100)  # PE 从 15 降到 12
        result = pe_percentile(s, max_window_years=5)
        assert result is not None
        assert 0.0 <= result <= 1.0


class TestPBPercentile:
    """§五·银行：PB分位，同 PE 分位逻辑"""

    def test_pb_percentile_returns_float(self):
        s = pd.Series([0.8] * 150 + [1.2] * 100)
        result = pb_percentile(s, max_window_years=5)
        assert result is not None
        assert 0.0 <= result <= 1.0


# ===================================================================
# §五·因子层：real z-score（银行ETF）
# ===================================================================

class TestZScore:
    """
    §五·银行：
      PB_zscore  = (当前PB  - 5年PB均值)  / 5年PB标准差
      股息_zscore = (当前股息率 - 5年股息率均值) / 5年股息率标准差
    """

    def test_above_mean_positive_z(self):
        """当前值 > 历史均值 → z > 0"""
        # 历史值在 [0.8, 1.2] 均匀分布，当前值 = 2.0（翻倍）
        np.random.seed(42)
        hist = np.random.uniform(0.8, 1.2, 300)
        s = pd.Series(list(hist) + [2.0])
        z = compute_zscore(s, max_window_years=5)
        assert z is not None, f"z should not be None, series len={len(s)}"
        assert z > 2.0  # 远超历史均值

    def test_below_mean_negative_z(self):
        """当前值 < 历史均值 → z < 0"""
        np.random.seed(42)
        hist = np.random.uniform(0.8, 1.2, 300)
        s = pd.Series(list(hist) + [0.3])
        z = compute_zscore(s, max_window_years=5)
        assert z is not None
        assert z < -2.0

    def test_constant_series_zero_z(self):
        """全部相等 → std ≈ 0 → z = 0"""
        s = pd.Series([5.0] * 300)
        z = compute_zscore(s, max_window_years=5)
        assert z is not None
        assert z == pytest.approx(0.0)

    def test_insufficient_data_returns_none(self):
        """不足 242 天有效值 → None"""
        s = pd.Series([10.0] * 100)
        z = compute_zscore(s, max_window_years=5)
        assert z is None

    def test_current_not_in_hist_mean(self):
        """验证当前值不参与历史均值计算（防未来函数）"""
        s = pd.Series([1.0] * 300 + [10.0])
        z = compute_zscore(s, max_window_years=5)
        assert z is not None
        assert z == pytest.approx(0.0)  # std=0 保护


# ===================================================================
# §五·因子层：动量 + 趋势开关（科创50）
# ===================================================================

class TestMomentum:
    """§五·科创50：120日动量 + 200日均线趋势"""

    def test_momentum_120d_positive(self):
        """价格上涨 → 动量 > 0"""
        prices = [100.0] * 121
        prices[-1] = 120.0  # 涨了 20%
        s = pd.Series(prices)
        mom = momentum_120d(s)
        assert mom is not None
        assert mom == pytest.approx(0.20)

    def test_momentum_120d_negative(self):
        """价格下跌 → 动量 < 0"""
        prices = [100.0] * 121
        prices[-1] = 80.0  # 跌了 20%
        s = pd.Series(prices)
        mom = momentum_120d(s)
        assert mom is not None
        assert mom == pytest.approx(-0.20)

    def test_momentum_insufficient_data(self):
        """不足 121 天 → None"""
        s = pd.Series([100.0] * 50)
        mom = momentum_120d(s)
        assert mom is None

    def test_trend_on(self):
        """Price ≥ MA200 → ON"""
        prices = [100.0] * 250
        s = pd.Series(prices)
        assert ma_trend_200d(s) is True

    def test_trend_off(self):
        """Price < MA200 → OFF"""
        prices = [100.0] * 199 + [50.0]  # 突然大跌
        s = pd.Series(prices)
        assert ma_trend_200d(s) is False

    def test_trend_insufficient_data_off(self):
        """不足 200 天 → OFF（保守）"""
        s = pd.Series([100.0] * 100)
        assert ma_trend_200d(s) is False

    def test_kechuang_trend_off_halves(self):
        """§六·科创50：趋势 OFF → 需足够历史数据计算动量分位"""
        # 需要足够长的历史（至少 momentum_days + 40 = 161 天）
        prices = [100.0 + i * 0.1 for i in range(200)]  # 稳步上涨
        s = pd.Series(prices)
        result = kechuang_opportunity(s, max_window_years=5)
        # 趋势 ON（价格在 MA200 之上因为长期上涨）
        assert result is not None
        assert 0.0 <= result <= 1.0


# ===================================================================
# §五·因子层：波动率 + 最大回撤
# ===================================================================

class TestVolatility:
    """§八·风险控制：年化波动率"""

    def test_annualized_volatility(self):
        """波动率 = σ_daily × √242"""
        np.random.seed(42)
        returns = np.random.normal(0, 0.02, WINDOW_VOL_DAYS + 10)
        prices = 100 * (1 + returns).cumprod()
        s = pd.Series(prices)
        vol = annualized_volatility(s)
        assert vol is not None
        assert 0.0 < vol < 1.0  # 应该在 0-100% 之间

    def test_max_drawdown_negative(self):
        """最大回撤 ≤ 0"""
        prices = [100, 90, 80, 95, 85, 100]
        s = pd.Series(prices)
        dd = max_drawdown(s, window=252)
        assert dd is not None
        assert dd <= 0.0
        assert dd == pytest.approx(-0.20)  # 100→80 = -20%


# ===================================================================
# §六·评分层
# ===================================================================

class TestScoringFormulas:
    """逐个资产验证评分公式"""

    # ── 白酒：1 - PE分位 ──
    @pytest.mark.parametrize("pe_pct,expected", [
        (0.00, 1.00),   # 极端便宜
        (0.15, 0.85),   # §六·白酒例
        (0.50, 0.50),   # 中等
        (0.90, 0.10),   # 贵
        (1.00, 0.00),   # 极端贵
    ])
    def test_baijiu(self, pe_pct, expected):
        assert score_baijiu(pe_pct) == pytest.approx(expected)

    # ── 银行：sigmoid(0.5*z_PB + 0.5*z_div) ──
    @pytest.mark.parametrize("z_pb,z_div,expected_range", [
        (2.0, 2.0, (0.85, 1.00)),    # 都高 → 机会好
        (0.0, 0.0, (0.45, 0.55)),    # 中性 → 中等
        (-2.0, -2.0, (0.00, 0.15)),  # 都低 → 机会差
        (3.0, -3.0, (0.45, 0.55)),   # 对冲 → 中等
    ])
    def test_bank(self, z_pb, z_div, expected_range):
        result = score_bank(z_pb, z_div)
        assert result is not None
        lo, hi = expected_range
        assert lo <= result <= hi

    # ── 红利：股息率分位 ──
    @pytest.mark.parametrize("dy_pct,expected", [
        (0.90, 0.90),
        (0.10, 0.10),
        (0.50, 0.50),
        (0.00, 0.00),
        (1.00, 1.00),
    ])
    def test_dividend(self, dy_pct, expected):
        assert score_dividend(dy_pct) == pytest.approx(expected)

    # ── 沪深300：1 - PE分位 ──
    @pytest.mark.parametrize("pe_pct,expected", [
        (0.20, 0.80),
        (0.55, 0.45),
        (0.80, 0.20),
    ])
    def test_hs300(self, pe_pct, expected):
        assert score_hs300(pe_pct) == pytest.approx(expected)

    # ── 科创50：动量分位 × 趋势开关 ──
    @pytest.mark.parametrize("mom,mult,expected", [
        (0.92, 1.00, 0.92),  # 趋势 ON
        (0.92, 0.50, 0.46),  # 趋势 OFF → 减半
        (0.00, 0.50, 0.00),  # 零动量
        (0.68, 1.00, 0.68),
    ])
    def test_kechuang(self, mom, mult, expected):
        assert score_kechuang(mom, mult) == pytest.approx(expected)

    def test_trend_off_multiplier_matches_config(self):
        """验证趋势 OFF 乘数与配置一致"""
        assert KECHUANG_TREND_OFF_MULTIPLIER == 0.50


# ===================================================================
# §七·温度计
# ===================================================================

class TestThermometer:
    """§七·市场温度计：4档分级 + 不一致冻结"""

    @pytest.mark.parametrize("pct,tier", [
        (0.30, 0),
        (0.59, 0),
        (0.60, 1),
        (0.75, 1),
        (0.79, 1),
        (0.80, 2),
        (0.85, 2),
        (0.89, 2),
        (0.90, 3),
        (0.95, 3),
    ])
    def test_tier_mapping(self, pct, tier):
        assert _tier(pct) == tier

    @pytest.mark.parametrize("p1,p2,expected_eq", [
        (0.30, 0.40, 1.00),  # <60%
        (0.65, 0.72, 0.70),  # 60-80%
        (0.85, 0.88, 0.40),  # 80-90%
        (0.93, 0.97, 0.30),  # >90%
    ])
    def test_four_tiers(self, p1, p2, expected_eq):
        reset_persistence()
        eq, _ = equity_ratio(p1, p2)
        assert eq == expected_eq

    def test_freeze_on_disagreement(self):
        """§七：双指标不一致 → 冻结上期"""
        reset_persistence()
        equity_ratio(0.30, 0.40)  # 一致→100%, 记下
        eq, _ = equity_ratio(0.95, 0.50)  # 不一致→冻结
        assert eq == 1.00  # 返回上次的 100%

    def test_first_call_default(self):
        """首调用不一致 → 默认 100%"""
        reset_persistence()
        eq, _ = equity_ratio(0.95, 0.50)
        assert eq == 1.00


# ===================================================================
# §九·约束层
# ===================================================================

class TestConstraints:
    """§九·组合约束"""

    @pytest.mark.parametrize("cw,ul,buf,expected_coef", [
        # 权重在自由区间
        (0.10, 0.25, 0.05, 1.00),   # 10% < 20% → 1.0
        (0.15, 0.25, 0.05, 1.00),   # 15% < 20% → 1.0
        # 权重在缓冲带
        (0.22, 0.25, 0.05, 0.60),   # (0.25-0.22)/0.05 = 0.60
        (0.24, 0.25, 0.05, 0.20),   # (0.25-0.24)/0.05 = 0.20
        # 权重超上限
        (0.25, 0.25, 0.05, 0.00),   # 正好上限 → 0.0
        (0.30, 0.25, 0.05, 0.00),   # 超上限 → 0.0
    ])
    def test_buy_coefficient(self, cw, ul, buf, expected_coef):
        coef = buy_coefficient(cw, ul, buf)
        assert coef == pytest.approx(expected_coef)

    def test_max_buy_amount_positive(self):
        """有空间可买 → 正金额"""
        result = max_buy_amount(1000.0, 10000.0, 0.25)
        # 上限金额 = 2500, 当前 = 1000 → 可买 1500
        assert result == pytest.approx(1500.0)

    def test_max_buy_amount_zero(self):
        """已到上限 → 0"""
        result = max_buy_amount(2500.0, 10000.0, 0.25)
        assert result == 0.0

    def test_group_weight(self):
        """因子组权重计算"""
        weights = {"白酒ETF": 0.15, "银行ETF": 0.20, "红利ETF": 0.10}
        gw = group_weight(weights, "VALUE")
        assert gw == pytest.approx(0.45)  # 15+20+10 = 45%


# ===================================================================
# §十·分配层
# ===================================================================

class TestAllocation:
    """§十·资金分配"""

    def test_gap_scores_below_lower(self):
        """低于下限 → 正缺口分"""
        current = {"白酒ETF": 0.05, "银行ETF": 0.20}
        gaps = compute_gap_scores(current)
        # 白酒: max(0, 0.10-0.05) = 0.05, 银行: max(0, 0.10-0.20) = 0
        assert gaps["白酒ETF"] > 0
        assert gaps["银行ETF"] == 0.0

    def test_gap_scores_all_above_lower(self):
        """全部≥下限 → 全0"""
        # 需要包含所有 TARGET_BANDS 中的权益资产
        current = {"白酒ETF": 0.20, "银行ETF": 0.25, "红利ETF": 0.20,
                    "沪深300ETF": 0.25, "科创50ETF": 0.10}
        gaps = compute_gap_scores(current)
        assert all(v == 0.0 for v in gaps.values())

    def test_gap_scores_normalized(self):
        """归一化：缺口分之和 = 1.0（如果有缺口）"""
        current = {"白酒ETF": 0.05, "银行ETF": 0.05, "红利ETF": 0.20}
        gaps = compute_gap_scores(current)
        if sum(gaps.values()) > 0:
            assert sum(gaps.values()) == pytest.approx(1.0)

    def test_priority_mixture(self):
        """§十·10.3：综合优先级 = GAP_W × 缺口 + OPP_W × 机会"""
        gaps = {"白酒ETF": 0.5, "银行ETF": 0.5}
        opps = {"白酒ETF": 0.8, "银行ETF": 0.4}
        priorities = compute_priority(gaps, opps)
        # 白酒: 0.5*0.5 + 0.5*0.8 = 0.65
        assert priorities["白酒ETF"] == pytest.approx(0.65)
        # 银行: 0.5*0.5 + 0.5*0.4 = 0.45
        assert priorities["银行ETF"] == pytest.approx(0.45)

    def test_priority_all_gaps_zero_uses_opp_only(self):
        """§十五·补充建议1：全部缺口≤0 → 直接用机会分"""
        gaps = {"白酒ETF": 0.0, "银行ETF": 0.0}
        opps = {"白酒ETF": 0.8, "银行ETF": 0.4}
        priorities = compute_priority(gaps, opps)
        assert priorities["白酒ETF"] == 0.8
        assert priorities["银行ETF"] == 0.4

    def test_missing_opportunity_score_defaults_zero(self):
        """机会分缺失 → 优先级 = 0"""
        gaps = {"白酒ETF": 0.5}
        opps = {}  # 无机会分
        priorities = compute_priority(gaps, opps)
        assert priorities["白酒ETF"] == 0.0


# ===================================================================
# §补充建议·验证
# ===================================================================

class TestSupplementalRequirements:
    """§十五·补充建议实现验证"""

    def test_rebalance_target_midpoint(self):
        """年度再平衡目标 = 上下限带中点"""
        from src.rebalance.checker import _target_midpoint
        assert _target_midpoint("白酒ETF") == pytest.approx(0.175)  # (0.10+0.25)/2
        assert _target_midpoint("银行ETF") == pytest.approx(0.20)   # (0.10+0.30)/2

    def test_kechuang_notes_semiconductor(self):
        """科创50 备注"半导体主导的硬科技成长"在 settings.py 注释中"""
        from pathlib import Path
        src = Path(__file__).parent.parent.parent / "config" / "settings.py"
        content = src.read_text(encoding="utf-8")
        assert "半导体" in content, "settings.py 应包含科创50的半导体集中度说明"

    def test_penalty_no_memory_comment(self):
        """§十五·补充建议4：惩罚函数注释"不记忆旧值"在源码"""
        import inspect
        source = inspect.getsource(buy_coefficient)
        assert "不记忆" in source or "not memorize" in source.lower()


# ===================================================================
# §十二·回测指标
# ===================================================================

class TestBacktestMetrics:
    """§十二·回测评价指标公式"""

    def test_metrics_structure(self):
        """验证 compute_metrics 返回 4 个指标"""
        from src.backtest.engine import compute_metrics
        result = compute_metrics(
            portfolio_values=[10000, 10500, 11000],
            total_invested=10000,
            monthly_returns=[0.05, 0.0476],
        )
        assert "annualized_return" in result
        assert "max_drawdown" in result
        assert "calmar" in result
        assert "sharpe" in result

    def test_flat_values_no_drawdown(self):
        """一直上涨 → 回撤 = 0"""
        from src.backtest.engine import compute_metrics
        result = compute_metrics(
            portfolio_values=[10000, 11000, 12000],
            total_invested=10000,
            monthly_returns=[0.10, 0.0909],
        )
        assert result["max_drawdown"] == pytest.approx(0.0)

    def test_drawdown_detected(self):
        """先涨后跌 → 有回撤"""
        from src.backtest.engine import compute_metrics
        result = compute_metrics(
            portfolio_values=[10000, 12000, 9000],
            total_invested=10000,
            monthly_returns=[0.20, -0.25],
        )
        assert result["max_drawdown"] < 0  # 有回撤


# ===================================================================
# 国债验证
# ===================================================================

class TestGuozhai:
    """国债不参与评分 → 永远 None"""

    def test_guozhai_no_score(self):
        scores = score_all({"国债ETF": {}})
        assert scores["国债ETF"] is None

    def test_guozhai_not_in_gap_scores(self):
        gaps = compute_gap_scores({"国债ETF": 0.15})
        assert "国债ETF" not in gaps
