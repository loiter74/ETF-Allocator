"""
allocation/allocator.py — 资金分配算法。

设计 (ds.v1.2.winner.md)：
  综合优先级 = GAP_WEIGHT × 缺口分 + OPPORTUNITY_WEIGHT × 机会分

- 缺口分衡量"当前权重低于目标下限"的程度
- 机会分衡量"当前估值是否有吸引力"
- 如果所有权益资产的缺口分 ≤ 0，跳过缺口调整，直接用机会分
- 分配上限 = 最终仓位上限对应金额 - 当前持仓金额
"""
from typing import Dict, Optional
import numpy as np
import os

from config.settings import (
    TARGET_BANDS,
    GROUP_CAPS,
    ASSETS,
    ALLOCATION_GAP_WEIGHT,
    ALLOCATION_OPPORTUNITY_WEIGHT,
    MIN_OPPORTUNITY_SCORE,
)


def compute_gap_scores(
    current_weights: Dict[str, float],
) -> Dict[str, float]:
    """
    计算每个权益资产的缺口分。

    缺口分 = max(0, 目标下限 - 当前权重)
    结果归一化到 [0, 1]（除以所有缺口之和，和为0则全返回0）。
    """
    gaps = {}
    for name, (lower, _upper) in TARGET_BANDS.items():
        if name == "国债ETF":
            continue
        cw = current_weights.get(name, 0.0)
        gap = max(0.0, lower - cw)
        gaps[name] = gap

    total_gap = sum(gaps.values())
    if total_gap <= 0:
        return {k: 0.0 for k in gaps}

    return {k: v / total_gap for k, v in gaps.items()}


def compute_priority(
    gap_scores: Dict[str, float],
    opportunity_scores: Dict[str, Optional[float]],
) -> Dict[str, float]:
    """
    计算综合优先级。

    如果所有缺口分 ≤ 0 → 跳过缺口，直接用机会分。
    否则 → GAP_WEIGHT × 缺口分 + OPPORTUNITY_WEIGHT × 机会分。
    """
    all_gaps_zero = all(v <= 0 for v in gap_scores.values())

    priorities = {}
    for name in gap_scores:
        opp = opportunity_scores.get(name)
        if opp is None:
            priorities[name] = 0.0
            continue

        if all_gaps_zero:
            priorities[name] = opp
        else:
            priorities[name] = (
                ALLOCATION_GAP_WEIGHT * gap_scores[name]
                + ALLOCATION_OPPORTUNITY_WEIGHT * opp
            )

    return priorities


def allocate(
    opportunity_scores: Dict[str, Optional[float]],
    current_weights: Dict[str, float],
    upper_limits: Dict[str, float],
    total_assets: float,
    equity_budget: float,
    buy_coefficients: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    资金分配主函数。

    Args:
        opportunity_scores: {asset: score ∈ [0,1] or None}
        current_weights: {asset: weight ∈ [0,1]}
        upper_limits: {asset: effective_upper}  — 风险层已调整的上限
        total_assets: 当前总资产金额
        equity_budget: 本月可投权益金额（温度计计算后）
        buy_coefficients: {asset: 可买入系数} — 约束层输出，0=禁止买入

    Returns:
        {asset: allocation_amount}，每个值 ≥ 0
    """
    # ── 0. 初始建仓模式：total_assets 过小时按机会分比例分配 ──
    if total_assets <= 0:
        return _initial_build_allocation(opportunity_scores, upper_limits, equity_budget, buy_coefficients)

    # ── 1. 计算缺口分 ──
    gap_scores = compute_gap_scores(current_weights)

    # ── 2. 计算综合优先级 ──
    priorities = compute_priority(gap_scores, opportunity_scores)

    # ── 3. 选出有可买空间且有机会分的资产 ──
    candidates = []
    for name, pri in sorted(priorities.items(), key=lambda x: -x[1]):
        if pri <= 0:
            continue

        ul = upper_limits.get(name, 0.0)
        if ul <= 0:
            continue

        current_value = current_weights.get(name, 0.0) * total_assets
        target_value = ul * total_assets
        max_buy = max(0.0, target_value - current_value)
        # 约束层可买入系数：0 = 禁止
        coeff = (buy_coefficients or {}).get(name, 1.0)
        max_buy *= coeff
        # 机会分过低 → 跳过（防御性：缺口再大也不买极度高估资产）
        opp = opportunity_scores.get(name)
        if opp is not None and opp < MIN_OPPORTUNITY_SCORE:
            continue
        if max_buy <= 0:
            continue

        candidates.append((name, pri, max_buy))

    # ── 4. 按优先级依次分配 ──
    allocation: Dict[str, float] = {}
    remaining = equity_budget

    for name, _pri, max_b in candidates:
        if remaining <= 0:
            break
        alloc = min(max_b, remaining)
        allocation[name] = alloc
        remaining -= alloc

    # ── 5. 因子组约束（等比缩减超限组） ──
    allocation = _apply_group_constraint(allocation, current_weights, total_assets)

    # ── 6. 剩余资金进国债 ──
    overflow = remaining
    if overflow > 0:
        allocation["国债ETF"] = allocation.get("国债ETF", 0) + overflow

    # 确保所有值 ≥ 0
    for k in allocation:
        allocation[k] = max(0.0, allocation[k])

    # ── 调试日志（设置 DEBUG_ALLOC=1 时输出） ──
    if os.environ.get("DEBUG_ALLOC"):
        # 缺口中转数值的打印
        print("\n=== ALLOCATION DEBUG ===")
        for name in gap_scores:
            opp = opportunity_scores.get(name)
            skipped = opp is not None and opp < MIN_OPPORTUNITY_SCORE
            coeff = (buy_coefficients or {}).get(name, 1.0)
            print(f"  {name:12s} | gap={gap_scores.get(name,0):.4f} opp={opp or 0:.3f} "
                  f"pri={priorities.get(name,0):.4f} coeff={coeff:.2f} "
                  f"alloc={allocation.get(name,0):>8.0f}{' SKIPPED' if skipped else ''}")
        print(f"  equity_budget={equity_budget:.0f} allocated={sum(v for v in allocation.values() if v>0):.0f}")
        print("===========================\n")

    return allocation


def _initial_build_allocation(
    opportunity_scores: Dict[str, Optional[float]],
    upper_limits: Dict[str, float],
    equity_budget: float,
    buy_coefficients: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    初始建仓模式：无历史持仓时，按机会分分配。

    单轮按机会分降序分配并遵守上限，剩余资金进入国债。
    """
    allocation: Dict[str, float] = {}
    candidates = []

    for name, score in opportunity_scores.items():
        if score is None or score <= 0:
            continue
        # 机会分过低 → 跳过（防止买入极度高估资产）
        if score < MIN_OPPORTUNITY_SCORE:
            continue
        ul = upper_limits.get(name, 0.0)
        if ul <= 0:
            continue
        coeff = (buy_coefficients or {}).get(name, 1.0)
        if coeff <= 0:
            continue  # 约束层禁止买入
        cap_amount = ul * equity_budget * coeff
        candidates.append((name, score, cap_amount))

    if not candidates:
        allocation["国债ETF"] = equity_budget
        return allocation

    candidates.sort(key=lambda x: -x[1])
    remaining = equity_budget

    # 首轮：上限封顶
    for name, _score, cap in candidates:
        if remaining <= 0:
            break
        alloc = min(cap, remaining)
        allocation[name] = alloc
        remaining -= alloc

    # ── 应用因子组约束后进国债 ──
    # 初始建仓时 total_assets=0，约束函数内 new_total = sum(allocation)
    zero_weights = {name: 0.0 for name in allocation}
    allocation = _apply_group_constraint(allocation, zero_weights, 0.0)

    # 最后的最后才进国债
    if remaining > 0:
        allocation["国债ETF"] = allocation.get("国债ETF", 0) + remaining

    # ── 调试日志 ──
    if os.environ.get("DEBUG_ALLOC"):
        print("\n=== INITIAL BUILD DEBUG ===")
        for name, score, _cap in candidates:
            skipped = score < MIN_OPPORTUNITY_SCORE
            print(f"  {name:12s} | score={score:.3f} cap={_cap:.0f} "
                  f"alloc={allocation.get(name,0):>8.0f}{' SKIPPED' if skipped else ''}")
        print(f"  equity_budget={equity_budget:.0f} allocated={sum(v for v in allocation.values() if v>0):.0f}")
        print("============================\n")

    return allocation


def _apply_group_constraint(
    allocation: Dict[str, float],
    current_weights: Dict[str, float],
    total_assets: float,
) -> Dict[str, float]:
    """
    因子组约束检查。

    如果某因子组的 当前权重 + 本次分配 > 组上限，
    则在组内等比缩减分配金额，溢出部分进国债。
    """
    # 模拟分配后的总资产
    new_total = total_assets + sum(allocation.values())
    if new_total <= 0:
        return allocation

    # 计算分配后的各资产权重
    new_weights = dict(current_weights)
    for name, amt in allocation.items():
        new_weights[name] = (current_weights.get(name, 0.0) * total_assets + amt) / new_total

    result = dict(allocation)
    for grp, cap in GROUP_CAPS.items():
        # 计算组当前权重（分配后）
        gw = sum(
            new_weights.get(name, 0.0)
            for name, cfg in ASSETS.items()
            if cfg["factor_group"] == grp
        )
        if gw <= cap:
            continue

        # 组内收到分配资金的资产
        group_allocated = [
            name for name, cfg in ASSETS.items()
            if cfg["factor_group"] == grp and result.get(name, 0) > 0
        ]
        if not group_allocated:
            continue

        # 计算可新增金额的上限
        current_group_value = sum(
            current_weights.get(a, 0.0) * total_assets
            for a, cfg in ASSETS.items() if cfg["factor_group"] == grp
        )
        allowed_group_value = cap * new_total
        allowed_new = max(0.0, allowed_group_value - current_group_value)
        current_new = sum(result[a] for a in group_allocated)

        if current_new <= allowed_new:
            continue

        # 等比缩减
        scale = allowed_new / current_new if current_new > 0 else 0
        for a in group_allocated:
            result[a] = result[a] * scale

        # 溢出部分进国债
        overflow = current_new - sum(result[a] for a in group_allocated)
        result["国债ETF"] = result.get("国债ETF", 0) + overflow

    return result
