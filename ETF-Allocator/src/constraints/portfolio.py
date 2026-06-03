"""
constraints/portfolio.py — 组合约束层。

两层约束：
1. 单标的带（上下限 + 惩罚函数）
2. 因子组带（防伪分散：VALUE组 ≤ 60%，GROWTH组 ≤ 15%）
"""
from typing import Dict, Optional

from config.settings import (
    TARGET_BANDS,
    GROUP_CAPS,
    PENALTY_BUFFER,
    ASSETS,
)


def buy_coefficient(
    current_weight: float,
    upper_limit: float,
    buffer: float = PENALTY_BUFFER,
) -> float:
    """
    惩罚函数：当前权重 → 可买系数 [0, 1]。

    buffer 定义了"缓冲带"：
    - 权重 < 上限 - buffer  → 系数 = 1（完全自由）
    - 上限 - buffer ≤ 权重 < 上限 → 系数线性递减 1→0
    - 权重 ≥ 上限 → 系数 = 0

    不记忆旧值，直接基于当前持仓和当前上限计算。
    """
    if buffer <= 0:
        return 1.0 if current_weight < upper_limit else 0.0
    if current_weight < upper_limit - buffer:
        return 1.0
    if current_weight < upper_limit:
        return max(0.0, (upper_limit - current_weight) / buffer)
    return 0.0


def max_buy_amount(
    current_value: float,
    total_assets: float,
    upper_limit: float,
) -> float:
    """
    该资产本月最多可买入的金额。

    max_buy = upper_limit × total_assets - current_value
    结果永不 < 0。
    """
    target_value = upper_limit * total_assets
    result = target_value - current_value
    return max(0.0, result)


def group_weight(
    weights: Dict[str, float],
    group: str,
) -> float:
    """
    计算某因子组的当前组合权重。

    Args:
        weights: {asset_name: weight}
        group: "VALUE" / "GROWTH" / "DEFENSE"

    Returns:
        因子组总权重 ∈ [0, 1]
    """
    total = 0.0
    for name, w in weights.items():
        cfg = ASSETS.get(name)
        if cfg and cfg["factor_group"] == group:
            total += w
    return total


def check_factor_group_constraint(
    allocations: Dict[str, float],
    current_weights: Dict[str, float],
    total_assets: float,
) -> Dict:
    """
    检查因子组约束是否触发。

    如果某组的当前权重 + 本次分配 > 组上限，则在组内等比缩减。

    Returns:
        {
            "status": "ok" | "scale_down",
            "group": 触发的组名(if scale_down),
            "scaled_allocations": 缩减后的分配方案,
        }

    注意：上限波动时，本函数直接基于当前持仓和当前上限计算，不记忆旧值。
    """
    # 计算新权重
    new_weights = {}
    for name in current_weights:
        new_val = current_weights[name] * total_assets + allocations.get(name, 0)
        new_weights[name] = new_val / (total_assets + sum(allocations.values()))

    for grp, cap in GROUP_CAPS.items():
        gw = group_weight(new_weights, grp)
        if gw > cap:
            # 需要缩减该组
            group_assets = [
                n for n, cfg in ASSETS.items()
                if cfg["factor_group"] == grp and allocations.get(n, 0) > 0
            ]
            if not group_assets:
                continue

            # 当前组市值
            current_group_value = sum(
                current_weights[a] * total_assets for a in group_assets
            )
            # 允许的组上限
            allowed_group_value = cap * (total_assets + sum(allocations.values()))
            # 允许新增的组金额
            allowed_new = max(0.0, allowed_group_value - current_group_value)
            current_new_total = sum(allocations.get(a, 0) for a in group_assets)

            if current_new_total <= allowed_new:
                continue

            # 等比缩减
            scale = allowed_new / current_new_total if current_new_total > 0 else 0
            scaled = dict(allocations)
            for a in group_assets:
                scaled[a] = allocations[a] * scale
            # 溢出部分进国债
            overflow = sum(allocations[a] for a in group_assets) - sum(
                scaled[a] for a in group_assets
            )
            scaled["国债ETF"] = scaled.get("国债ETF", 0) + overflow

            return {
                "status": "scale_down",
                "group": grp,
                "scaled_allocations": scaled,
            }

    return {"status": "ok"}


def apply_constraints(
    current_weights: Dict[str, float],
    upper_limits: Dict[str, float],
    total_assets: float,
) -> Dict:
    """
    综合应用所有约束，输出可买系数和最大买入金额。

    Args:
        current_weights: {asset_name: 当前权重}
        upper_limits: {asset_name: 有效上限（风险层已调整）}
        total_assets: 总资产金额

    Returns:
        {
            "buy_coefficients": {asset: coef},
            "max_buy": {asset: max_amount},
            "group_weights": {group: weight},
            "group_caps": GROUP_CAPS,
        }
    """
    coefs = {}
    max_buys = {}
    current_values = {
        name: current_weights.get(name, 0) * total_assets
        for name in upper_limits
    }

    for name, limit in upper_limits.items():
        cw = current_weights.get(name, 0.0)
        coefs[name] = buy_coefficient(cw, limit)
        max_buys[name] = max_buy_amount(current_values[name], total_assets, limit)

    groups = {grp: group_weight(current_weights, grp) for grp in GROUP_CAPS}

    return {
        "buy_coefficients": coefs,
        "max_buy": max_buys,
        "group_weights": groups,
        "group_caps": dict(GROUP_CAPS),
    }
