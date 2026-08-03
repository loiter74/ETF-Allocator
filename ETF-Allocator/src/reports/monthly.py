"""
reports/monthly.py — 月度配置报告生成器。

生成符合设计文档格式的可追溯报告，每个数字都可溯源到因子值和规则。
永不显示"预计年化"点估计。
"""
from datetime import date
from typing import Optional

from config.settings import TEMP_THRESHOLDS


def _fmt_amount(amount: float) -> str:
    """格式化金额，添加千分位逗号。"""
    return f"{amount:,.0f}"


# 温度计 4 档人类可读标签，阈值来自 settings.TEMP_THRESHOLDS（audit C1）。
# TEMP_THRESHOLDS 形如 [0.60, 0.80, 0.90]，对应 4 档：正常 / 中等偏高 / 高温 / 过热。
def _temperature_label(temp: float) -> str:
    """温度计分位 → 人类可读标签（4档分级）。"""
    if temp > TEMP_THRESHOLDS[2]:          # > 0.90
        return "过热（>90%）"
    elif temp >= TEMP_THRESHOLDS[1]:       # 80-90%
        return "高温（80-90%）"
    elif temp >= TEMP_THRESHOLDS[0]:       # 60-80%
        return "中等偏高（60-80%）"
    return "正常（<60%）"


def _asset_trigger_reason(
    asset_name: str,
    factors: dict,
    scores: dict,
) -> str:
    """
    生成每个资产分配的触发原因。
    
    根据资产类型返回对应的因子值，如"PE分位 15%"。
    """
    asset_factors = factors.get(asset_name, {}) if isinstance(factors, dict) else {}
    
    if asset_name == "白酒ETF":
        pe = asset_factors.get("pe_percentile")
        if pe is not None:
            return f"PE分位 {pe:.0%}"
        return "估值数据缺失"
    
    elif asset_name == "银行ETF":
        pb = asset_factors.get("pb_percentile")
        dy = asset_factors.get("dividend_percentile")
        pb_z = asset_factors.get("pb_zscore")
        dy_z = asset_factors.get("dividend_zscore")
        parts = []
        if pb is not None:
            parts.append(f"PB分位 {pb:.0%}")
        if dy is not None:
            parts.append(f"股息率分位 {dy:.0%}")
        if pb_z is not None and dy_z is not None:
            parts.append(f"z值 {pb_z:.2f}/{dy_z:.2f}")
        return ", ".join(parts) if parts else "估值数据缺失"
    
    elif asset_name == "红利ETF":
        dy = asset_factors.get("dividend_percentile")
        if dy is not None:
            return f"股息率分位 {dy:.0%}"
        return "股息率数据缺失"
    
    elif asset_name == "沪深300ETF":
        pe = asset_factors.get("pe_percentile")
        if pe is not None:
            return f"PE分位 {pe:.0%}"
        return "估值数据缺失"
    
    elif asset_name == "科创50ETF":
        mom = asset_factors.get("momentum_percentile")
        trend = asset_factors.get("trend_multiplier")
        parts = []
        if mom is not None:
            parts.append(f"动量分位 {mom:.0%}")
        if trend is not None:
            status = "ON" if trend >= 0.99 else "OFF"
            parts.append(f"趋势{status}")
        return ", ".join(parts) if parts else "动量数据缺失"
    
    return "国债避险配置"


def _format_weight_range(current: float, upper: float) -> str:
    """格式化仓位范围显示：当前→上限。"""
    return f"{current:.1%}→{upper:.1%}"


def _next_december(current_date: date) -> date:
    """计算下一个12月第一个交易日。"""
    year = current_date.year
    if current_date.month >= 12:
        year += 1
    return date(year, 12, 1)


def generate_report(
    invest_date: date,
    new_money: float,
    temp_result: dict,
    factors: dict,
    scores: dict,
    allocation: dict,
    weights: dict,
    upper_limits: dict,
    constraints_result: dict,
    bond_status: Optional[dict] = None,
) -> str:
    """
    生成月度配置报告，完全匹配设计文档格式。

    Args:
        invest_date: 投资决策日期
        new_money: 本月新增资金总额
        temp_result: 市场温度计输出
            {
                "temperature": float,           # 加权温度
                "equity_ratio": float,          # 权益比例
                "bond_ratio": float,            # 国债比例
                "hs300_pe_pct": Optional[float], # 沪深300 PE分位
                "all_a_pb_pct": Optional[float], # 全A PB分位
                "detail": str,                   # 触发说明
            }
        factors: {asset_name: {factor_name: value, ...}}
        scores: {asset_name: opportunity_score or None}
        allocation: {asset_name: allocation_amount}（含国债）
        weights: {asset_name: current_weight}
        upper_limits: {asset_name: effective_upper_limit}
        constraints_result: constraints.apply_constraints 输出
        bond_status: BondAccumulator.get_status() 输出（可选，向后兼容）

    Returns:
        格式化的报告字符串
    """
    lines = []
    sep = "=" * 60

    # ── 头部 ──
    lines.append(sep)
    lines.append(f"  ETF配置月报 {invest_date.isoformat()}")
    lines.append(sep)
    lines.append("")

    # ── 【市场温度】 ──
    lines.append("【市场温度】")
    temp_val = temp_result.get("temperature", 0.50)
    hs300_pe = temp_result.get("hs300_pe_pct")
    all_a_pb = temp_result.get("all_a_pb_pct")
    equity_ratio = temp_result.get("equity_ratio", 1.0)
    temp_detail = temp_result.get("detail", "")

    pe_str = f"{hs300_pe:.0%}" if hs300_pe is not None else "N/A"
    pb_str = f"{all_a_pb:.0%}" if all_a_pb is not None else "N/A"
    lines.append(
        f"沪深300 PE分位: {pe_str} (5年窗口)  |  全A PB分位: {pb_str}"
    )
    label = temp_result.get("label") or _temperature_label(temp_val)
    lines.append(f"→ 温度计: {label}  |  本月权益投资比例: {equity_ratio:.0%}")
    if temp_detail:
        lines.append(f"  决策逻辑: {temp_detail}")
    lines.append("")

    # ── 【本月新增资金】 ──
    equity_amount = new_money * equity_ratio
    bond_amount = new_money - equity_amount
    lines.append(f"【本月新增资金】 {_fmt_amount(new_money)} 元")
    lines.append(f"├─ 权益投资: {_fmt_amount(equity_amount)} 元")
    lines.append(f"└─ 固收应配: {_fmt_amount(bond_amount)} 元")
    lines.append("")

    # ── 【国债执行状态】 ──
    if bond_status is not None:
        lines.append("【国债执行状态】（模式：累积制）")
        balance = bond_status.get("balance", 0)
        total_interest = bond_status.get("total_interest", 0)
        min_purchase = bond_status.get("min_purchase", 14000)
        can_buy = bond_status.get("can_buy", False)
        lots = bond_status.get("lots_available", 0)

        pool_total = balance  # accumulator 状态已包含本月存入与执行结果
        lines.append(f"本月固收应配： {_fmt_amount(bond_amount)}")
        interest_str = f"（含逆回购收益 {_fmt_amount(total_interest)}）" if total_interest > 0 else ""
        lines.append(f"累积池存量：   {_fmt_amount(balance)}{interest_str}")
        lines.append(f"累积池总额：   {_fmt_amount(pool_total)}")

        if can_buy:
            buy_amount = lots * min_purchase
            remaining = pool_total - buy_amount
            lines.append(f"-> 本月操作：   [BUY] 买入 {lots} 手 511010（{_fmt_amount(buy_amount)}）")
            if remaining > 0:
                lines.append(f"买入后余留：   {_fmt_amount(remaining)}（自动滚入下月）")
        else:
            gap = min_purchase - pool_total
            lines.append(f"距下一手门槛： {_fmt_amount(max(0, gap))}（需 {_fmt_amount(min_purchase)} 触发）")
            lines.append("-> 本月操作：   [WAIT] 暂不买入，继续累积")
        lines.append("")

    # ── 【权益分配】 ──
    lines.append("【权益分配】")
    
    # 表头
    header = f"{'资产':　<10s}　{'金额':>10s}　{'触发原因':　<20s}　{'机会分':>6s}　{'仓位(当前→上限)':　<16s}"
    lines.append(header)
    lines.append("-" * 75)

    for asset_name in ["白酒ETF", "银行ETF", "红利ETF", "沪深300ETF", "科创50ETF", "国债ETF"]:
        amount = allocation.get(asset_name, 0)
        if amount <= 0 and asset_name != "国债ETF":
            # 已到上限或未分配
            if asset_name in allocation:
                continue
        if amount <= 0:
            continue

        score = scores.get(asset_name)
        score_str = f"{score:.2f}" if score is not None else "N/A"
        trigger = _asset_trigger_reason(asset_name, factors, scores)
        current_w = weights.get(asset_name, 0)
        upper_w = upper_limits.get(asset_name, 1.0)
        w_range = _format_weight_range(current_w, upper_w)

        # 截断原因以对齐
        if len(trigger) > 20:
            trigger = trigger[:17] + "..."

        lines.append(
            f"{asset_name:<8s}　{_fmt_amount(amount):>10s}　"
            f"{trigger:<20s}　{score_str:>6s}　{w_range:<16s}"
        )
    
    lines.append("")

    # ── 【组合风险】 ──
    lines.append("【组合风险】")
    
    # 因子组权重
    group_weights = constraints_result.get("group_weights", {})
    group_caps = constraints_result.get("group_caps", {})
    
    value_weight = group_weights.get("VALUE", 0)
    value_cap = group_caps.get("VALUE", 0.60)
    growth_weight = group_weights.get("GROWTH", 0)
    growth_cap = group_caps.get("GROWTH", 0.15)
    
    lines.append(f"当前价值+红利组权重: {value_weight:.1%} (上限{value_cap:.0%})")
    lines.append(f"当前成长组权重: {growth_weight:.1%} (上限{growth_cap:.0%})")
    lines.append("")

    # ── 【下次再平衡检查】 ──
    next_check = _next_december(invest_date)
    lines.append(f"【下次再平衡检查】 {next_check.isoformat()}")
    lines.append("")

    # ── 底注 ──
    _disclaimer = (
        "注: 本报告仅提供新增资金配置建议，不构成投资建议。\n"
        "    所有数据截至报告日期，使用 expanding window 分位计算。\n"
        "    每个数字可追溯到对应因子值和规则。"
    )
    lines.append(_disclaimer)
    lines.append(sep)

    return "\n".join(lines)


def generate_trade_plan_report(plan) -> str:
    """Render a human-readable V2 TradePlan without changing its calculations."""
    reason_labels = {
        "STRATEGIC_HARD_CAP": "突破战略硬上限",
        "ANNUAL_SOFT_BAND": "12月越过年度外部软带",
        "BOND_ANNUAL_SOFT_BAND": "国债多手年度软再平衡",
        "K50_HWM_DRAWDOWN_PARTIAL": "科创高水位回撤且趋势OFF",
        "K50_TWO_MONTH_OFF_EXIT": "科创连续两月趋势OFF",
        "LOWER_BAND_REPAIR": "下限修复",
        "TARGET_FILL": "目标补齐",
        "HIGH_OPPORTUNITY_EXTENSION": "高机会扩展",
        "BOND_POOL_EXECUTION": "国债累积池达到交易门槛",
    }

    def describe(order) -> str:
        reasons = "、".join(reason_labels.get(code, code) for code in order.reason_codes)
        return (
            f"{order.asset} {order.shares}份 @ 预计¥{order.estimated_price:.4f}，"
            f"佣金¥{order.commission:.2f}；{reasons}"
        )

    before = plan.before
    lines = [
        f"🔴 月度交易计划（{plan.snapshot_date.isoformat()}，阶段：{plan.phase}）",
        "━" * 36,
        "【0. 战略仓位扫描】",
        f"全账户权益：{before.get('account_equity_ratio', 0):.1%}",
        f"防御桶：{before.get('defense_ratio', 0):.1%}",
        f"受管组合：¥{before.get('managed_total', 0):,.2f}",
        "",
        "【1. 正式卖单】",
    ]
    lines.extend([f"① {describe(order)}" for order in plan.formal_sells] or ["无"])
    lines.extend(["", "【2. 科创50影子卖单】"])
    lines.extend([f"① {describe(order)}（不执行、不计入现金）" for order in plan.shadow_sells] or ["无"])
    lines.extend(["", "【3. 买单】"])
    lines.extend([f"① {describe(order)}" for order in plan.buys] or [
        "等待真实卖出成交后重算" if plan.pending_buy_recalculation else "无"
    ])
    lines.extend(["", "【4. 现金轧差】"])
    if plan.cash_ledger:
        ledger = plan.cash_ledger
        lines.extend([
            f"期初现金 ¥{ledger.opening_cash:,.2f}",
            f"+ 新增资金 ¥{ledger.new_money:,.2f}",
            f"+ 卖出净收入 ¥{ledger.sell_net_proceeds:,.2f}",
            f"- 买入支出 ¥{ledger.buy_cash_outflow:,.2f}",
            f"= 期末现金 ¥{ledger.closing_cash:,.2f}",
            f"其中：国债池 ¥{ledger.bond_pool_after:,.2f}；权益待投 ¥{ledger.equity_pending_after:,.2f}",
        ])
    if plan.warnings:
        lines.extend(["", "【5. 提示】", *[f"- {warning}" for warning in plan.warnings]])
    lines.extend([
        "",
        "注：科创影子卖单不执行。正式卖单出现时必须先回填真实成交，再执行重算买单。",
    ])
    return "\n".join(lines)
