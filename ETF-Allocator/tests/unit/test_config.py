"""
测试 config/settings.py 中所有参数的有效性。
不测试业务逻辑，只测试参数本身是否合法。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from config import settings


class TestWindowsPositive:
    """所有窗口参数必须 > 0"""

    def test_pe_percentile_window_positive(self):
        assert settings.WINDOW_PE_PERCENTILE_YEARS > 0

    def test_momentum_window_positive(self):
        assert settings.WINDOW_MOMENTUM_DAYS > 0

    def test_ma_trend_window_positive(self):
        assert settings.WINDOW_MA_TREND_DAYS > 0

    def test_vol_window_positive(self):
        assert settings.WINDOW_VOL_DAYS > 0

    def test_drawdown_window_positive(self):
        assert settings.WINDOW_MAX_DRAWDOWN_DAYS > 0

    def test_trading_days_positive(self):
        assert settings.TRADING_DAYS_PER_YEAR > 0


class TestAssetPool:
    """资产池定义完整性检查"""

    def test_all_asset_classes_defined(self):
        for name, asset in settings.ASSETS.items():
            assert asset["asset_class"] in (
                "value", "value_dividend", "dividend", "wide", "growth", "defense"
            ), f"{name} has invalid asset_class: {asset['asset_class']}"

    def test_all_factor_groups_defined(self):
        for name, asset in settings.ASSETS.items():
            assert asset["factor_group"] in (
                "VALUE", "GROWTH", "DEFENSE"
            ), f"{name} has invalid factor_group: {asset['factor_group']}"

    def test_factor_group_caps_cover_all_groups(self):
        """GROUP_CAPS 覆盖了所有资产池中出现的 factor_group"""
        used_groups = {a["factor_group"] for a in settings.ASSETS.values()}
        for g in used_groups:
            if g != "DEFENSE":  # 防御组可以没有硬上限
                assert g in settings.GROUP_CAPS, f"factor_group '{g}' missing from GROUP_CAPS"

    def test_value_group_contains_expected_assets(self):
        """VALUE组应包含白酒、银行、红利、沪深300（不含科创50和国债）"""
        value_assets = [
            name for name, a in settings.ASSETS.items()
            if a["factor_group"] == "VALUE"
        ]
        assert "白酒ETF" in value_assets
        assert "银行ETF" in value_assets
        assert "红利ETF" in value_assets
        assert "沪深300ETF" in value_assets
        assert "科创50ETF" not in value_assets
        assert "国债ETF" not in value_assets

    def test_growth_group_is_kc50_only(self):
        growth_assets = [
            name for name, a in settings.ASSETS.items()
            if a["factor_group"] == "GROWTH"
        ]
        assert growth_assets == ["科创50ETF"]

    def test_defense_group_is_bond_only(self):
        defense_assets = [
            name for name, a in settings.ASSETS.items()
            if a["factor_group"] == "DEFENSE"
        ]
        assert defense_assets == ["国债ETF"]


class TestTargetBands:
    """目标权重上下限带合法性"""

    def test_lower_less_or_equal_upper(self):
        for name, (lower, upper) in settings.TARGET_BANDS.items():
            assert lower <= upper, f"{name}: lower {lower} > upper {upper}"

    def test_bounds_in_range(self):
        for name, (lower, upper) in settings.TARGET_BANDS.items():
            assert 0.0 <= lower <= 1.0, f"{name}: lower {lower} out of [0,1]"
            assert 0.0 <= upper <= 1.0, f"{name}: upper {upper} out of [0,1]"

    def test_target_bands_cover_all_assets(self):
        for name in settings.ASSETS:
            assert name in settings.TARGET_BANDS, f"{name} missing from TARGET_BANDS"

    def test_single_asset_cap_within_group_cap(self):
        """每个单标的上限不应超过其因子组上限（否则约束无意义）"""
        for name, (_, upper) in settings.TARGET_BANDS.items():
            group = settings.ASSETS[name]["factor_group"]
            if group in settings.GROUP_CAPS:
                assert upper <= settings.GROUP_CAPS[group], (
                    f"{name} single upper {upper} > group cap {settings.GROUP_CAPS[group]}"
                )


class TestGroupCaps:
    """因子组上限合法性"""

    def test_all_caps_in_range(self):
        for group, cap in settings.GROUP_CAPS.items():
            assert 0.0 < cap <= 1.0, f"{group} cap {cap} out of (0, 1]"

    def test_value_growth_sum_reasonable(self):
        """VALUE + GROWTH 合计不应超过 100%（否则无意义）"""
        total = settings.GROUP_CAPS.get("VALUE", 0) + settings.GROUP_CAPS.get("GROWTH", 0)
        assert total <= 1.0, f"VALUE+GROWTH cap sum {total} > 1.0"


class TestTemperatureThresholds:
    """温度计参数合法性 — ds.v1.2 4档分级"""

    def test_thresholds_monotonic(self):
        """阈值递增"""
        for i in range(len(settings.TEMP_THRESHOLDS) - 1):
            assert settings.TEMP_THRESHOLDS[i] < settings.TEMP_THRESHOLDS[i+1], (
                f"Thresholds must be strictly increasing"
            )

    def test_ratios_decreasing(self):
        """权益比例随档位递减（更高温度 → 更低权益）"""
        for i in range(len(settings.TEMP_EQUITY_RATIOS) - 1):
            assert settings.TEMP_EQUITY_RATIOS[i] > settings.TEMP_EQUITY_RATIOS[i+1], (
                f"Equity ratios must decrease as temperature rises, "
                f"got {settings.TEMP_EQUITY_RATIOS[i]} before {settings.TEMP_EQUITY_RATIOS[i+1]}"
            )

    def test_ratios_in_range(self):
        """所有权益比例在 [0, 1]"""
        for ratio in settings.TEMP_EQUITY_RATIOS:
            assert 0.0 <= ratio <= 1.0

    def test_thresholds_in_range(self):
        """所有阈值在 (0, 1)"""
        for threshold in settings.TEMP_THRESHOLDS:
            assert 0.0 < threshold < 1.0


class TestKeChuangTrendOff:
    """科创50趋势关闭参数"""

    def test_multiplier_in_range(self):
        """减半意味着 multiplier = 0.5"""
        assert 0.0 < settings.KECHUANG_TREND_OFF_MULTIPLIER < 1.0
        # 按 ds.v1.2 正文，应等于 0.5
        assert settings.KECHUANG_TREND_OFF_MULTIPLIER == 0.50


class TestRebalanceConfig:
    """年度再平衡参数（默认开启）"""

    def test_rebalance_enabled(self):
        assert settings.ANNUAL_REBALANCE_ENABLED is True

    def test_deviation_threshold_in_range(self):
        assert 0.0 < settings.REBALANCE_DEVIATION_THRESHOLD < 1.0

    def test_tolerance_smaller_than_threshold(self):
        assert settings.REBALANCE_TOLERANCE < settings.REBALANCE_DEVIATION_THRESHOLD


class TestBacktestSplit:
    """训练/测试切分合法性"""

    def test_train_before_test(self):
        assert settings.TRAIN_END < settings.TEST_START

    def test_test_before_end(self):
        assert settings.TEST_START < settings.TEST_END

    def test_exclude_backfill_flag(self):
        assert isinstance(settings.EXCLUDE_INDEX_BACKFILL, bool)


class TestPenaltyBuffer:
    """惩罚函数缓冲带"""

    def test_buffer_positive(self):
        assert settings.PENALTY_BUFFER > 0

    def test_buffer_less_than_min_band(self):
        """缓冲带应小于最窄的目标带宽度，否则毫无意义"""
        min_band_width = min(upper - lower for lower, upper in settings.TARGET_BANDS.values())
        assert settings.PENALTY_BUFFER < min_band_width, (
            f"PENALTY_BUFFER {settings.PENALTY_BUFFER} >= min band width {min_band_width}"
        )
