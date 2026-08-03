"""Annual relative-band rebalance checker.

This compatibility checker works with weights only, so it can calculate annual
core-asset sell amounts and funding gaps but never emits K50 profit protection or
bond whole-lot orders.  Full executable plans use ``src.strategy.planner``.
"""
from datetime import date
from typing import Dict, Optional

from config.settings import (
    ANNUAL_REBALANCE_ENABLED,
    REBALANCE_INNER_LOWER,
    REBALANCE_INNER_UPPER,
    REBALANCE_OUTER_LOWER,
    REBALANCE_OUTER_UPPER,
    TARGET_WEIGHTS,
)


def _is_first_trading_day_of_december(current_date: date) -> bool:
    return current_date.month == 12 and current_date.day <= 3


def _target_midpoint(asset_name: str) -> float:
    """Compatibility name retained for callers; returns the explicit target."""
    return TARGET_WEIGHTS.get(asset_name, 0.0)


def check_rebalance(
    current_date: date,
    current_weights: Dict[str, float],
    total_assets: Optional[float] = None,
) -> Dict:
    if not ANNUAL_REBALANCE_ENABLED:
        return {
            "rebalance_needed": False,
            "trades": {},
            "buy_targets": {},
            "detail": "再平衡已关闭",
        }
    if not _is_first_trading_day_of_december(current_date):
        return {
            "rebalance_needed": False,
            "trades": {},
            "buy_targets": {},
            "detail": "未触发",
        }

    sells: Dict[str, float] = {}
    buys: Dict[str, float] = {}
    details: list[str] = []
    for asset, target in TARGET_WEIGHTS.items():
        if asset == "国债ETF":
            continue
        actual = current_weights.get(asset, 0.0)
        outer_low = target * REBALANCE_OUTER_LOWER
        outer_high = target * REBALANCE_OUTER_UPPER
        if actual > outer_high:
            post_weight = target * REBALANCE_INNER_UPPER
            amount = max(0.0, actual - post_weight) * (total_assets or 0.0)
            if amount > 0:
                sells[asset] = round(amount, 2)
            details.append(
                f"{asset}: {actual:.1%} > 年度外带上界 {outer_high:.1%}，"
                f"卖至内部带 {post_weight:.1%}"
            )
        elif actual < outer_low:
            post_weight = target * REBALANCE_INNER_LOWER
            amount = max(0.0, post_weight - actual) * (total_assets or 0.0)
            if amount > 0:
                buys[asset] = round(amount, 2)
            details.append(
                f"{asset}: {actual:.1%} < 年度外带下界 {outer_low:.1%}，"
                f"优先用新增资金补至 {post_weight:.1%}"
            )

    return {
        "rebalance_needed": bool(sells or buys),
        "trades": sells,
        "buy_targets": buys,
        "detail": "\n".join(details) if details else "未触发",
    }
