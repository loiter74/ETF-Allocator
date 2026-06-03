"""
rebalance/checker.py — 年度再平衡检查器。

每年12月第一个交易日触发检查：
- 若某资产权重偏离目标中点 ≥ 10个百分点 → 标记需要卖出
- 卖出量旨在将权重拉回目标中点 ±5% 容忍带
"""
from datetime import date
from typing import Dict, Optional

from config.settings import (
    TARGET_BANDS,
    ANNUAL_REBALANCE_ENABLED,
    REBALANCE_DEVIATION_THRESHOLD,
    REBALANCE_TOLERANCE,
)


def _is_first_trading_day_of_december(current_date: date) -> bool:
    """
    判断是否是12月第一个交易日。
    
    简化实现：如果是12月且日 ≤ 3，视为第一个交易日附近。
    实际使用时应结合交易日历精确判断，但月度配置系统
    对"哪天"不敏感，三日内触发均可。
    """
    return current_date.month == 12 and current_date.day <= 3


def _target_midpoint(asset_name: str) -> float:
    """
    计算目标带中点。
    例如 白酒 10%-25% → 17.5%
    """
    bands = TARGET_BANDS.get(asset_name)
    if bands is None:
        return 0.0
    lower, upper = bands
    return (lower + upper) / 2.0


def check_rebalance(
    current_date: date,
    current_weights: Dict[str, float],
    total_assets: Optional[float] = None,
) -> Dict:
    """
    年度再平衡检查。

    如果当前日期是12月第一个交易日，检查各资产是否偏离目标中点
    超过 REBALANCE_DEVIATION_THRESHOLD（默认 0.10 = 10pp）。
    
    若偏离，计算 sell_amount 以将权重拉回目标中点 ±5% 容忍带。
    使用"只卖不买"的简化逻辑（不自动加仓低权重资产）。

    Args:
        current_date: 当前决策日期
        current_weights: {asset_name: weight ∈ [0, 1]}
        total_assets: 当前总资产金额（计算卖出金额时需要）

    Returns:
        {
            "rebalance_needed": bool,
            "trades": {asset_name: sell_amount},  # 正值表示卖出金额
            "detail": str,  # 人类可读的触发原因
        }
    """
    if not ANNUAL_REBALANCE_ENABLED:
        return {"rebalance_needed": False, "trades": {}, "detail": "再平衡已关闭"}

    if not _is_first_trading_day_of_december(current_date):
        return {"rebalance_needed": False, "trades": {}, "detail": "未触发"}

    trades: Dict[str, float] = {}
    details: list = []

    for asset_name, actual_weight in current_weights.items():
        if asset_name == "国债ETF":
            continue

        midpoint = _target_midpoint(asset_name)
        if midpoint <= 0:
            continue

        deviation = actual_weight - midpoint  # 正 = 偏高, 负 = 偏低

        if abs(deviation) > REBALANCE_DEVIATION_THRESHOLD:
            lower, upper = TARGET_BANDS[asset_name]

            if deviation > 0:
                # 偏高 → 需要卖出，拉回到 midpoint + tolerance
                upper_bound = midpoint + REBALANCE_TOLERANCE
                # 需要卖到 upper_bound 以下
                sell_weight = actual_weight - upper_bound
                if sell_weight > 0 and total_assets:
                    sell_amount = sell_weight * total_assets
                    trades[asset_name] = round(sell_amount, 2)
                    details.append(
                        f"{asset_name}: 权重 {actual_weight:.1%} 偏离中点 {midpoint:.1%} "
                        f"(偏差 +{deviation:.1%}) → 卖出约 {sell_amount:,.0f} 元"
                    )
                else:
                    details.append(
                        f"{asset_name}: 权重 {actual_weight:.1%} 偏离中点 {midpoint:.1%} "
                        f"(偏差 +{deviation:.1%}) → 建议卖出"
                    )
            else:
                # 偏低 → 不做自动买入（新钱分配已处理）
                details.append(
                    f"{asset_name}: 权重 {actual_weight:.1%} 低于目标 {midpoint:.1%} "
                    f"(偏差 {deviation:.1%}) → 依赖新钱补仓，不触发卖出"
                )

    if trades:
        return {
            "rebalance_needed": True,
            "trades": trades,
            "detail": "\n".join(details),
        }

    return {"rebalance_needed": False, "trades": {}, "detail": "未触发"}
