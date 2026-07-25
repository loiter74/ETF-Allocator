"""
risk/controller.py — 风险控制层。
读波动率 → 输出各资产本月有效仓位上限。
风险不进评分。

支持高波动恢复逻辑：波动率回落到阈值以下持续 20 个交易日后恢复正常上限。
"""
from typing import Optional, Dict

from config.settings import RISK_CONTROL, RISK_RECOVERY_DAYS

# 持久化：记录每个资产连续低于阈值的交易日数
# 用于实现"波动率回落后持续 N 天，才恢复正常上限"
# 初始值 = RISK_RECOVERY_DAYS，表示假设此前一直处于常态（首次运行不惩罚）
_low_vol_days: Dict[str, int] = {}
_RECOVERY_DAYS = RISK_RECOVERY_DAYS


def effective_upper_limit(
    asset_name: str,
    volatility: Optional[float],
) -> Optional[float]:
    """
    根据波动率调整仓位上限。

    高波动时降上限。波动率回落到阈值以下后，
    需持续 _RECOVERY_DAYS 个交易日才恢复常态上限。

    Args:
        asset_name: 资产名（如 "白酒ETF"）
        volatility: 年化波动率（小数，如 0.35 表示 35%）

    Returns:
        有效仓位上限（小数），未知资产返回 None
    """
    if asset_name not in RISK_CONTROL:
        return None

    normal_cap, high_vol_cap, threshold = RISK_CONTROL[asset_name]

    # 国债不受波动率影响
    if threshold is None:
        return normal_cap

    # 缺少波动率数据 → 保持常态上限
    if volatility is None:
        return normal_cap

    current_days = _low_vol_days.get(asset_name, _RECOVERY_DAYS)

    if volatility > threshold:
        # 高波动 → 强制降到高波动上限，重置计数
        _low_vol_days[asset_name] = 0
        return high_vol_cap

    # 波动率已低于阈值 → 递增恢复计数
    new_days = current_days + 1
    _low_vol_days[asset_name] = new_days

    if new_days >= _RECOVERY_DAYS:
        return normal_cap

    # 还在恢复观察期内 → 维持高波动上限
    return high_vol_cap


def all_effective_limits(
    volatilities: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    """
    批量计算所有资产的有效上限。

    Args:
        volatilities: {asset_name: annualized_vol}

    Returns:
        {asset_name: effective_upper_limit}
    """
    return {
        name: effective_upper_limit(name, vol)
        for name, vol in volatilities.items()
    }


def reset_recovery_tracking() -> None:
    """重置恢复跟踪状态（用于测试）。"""
    _low_vol_days.clear()
