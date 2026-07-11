"""
scoring/engine.py — 因子 → 统一 [0,1] 机会分。

规则：
- 风险不进评分
- 国债不参与评分（永远 None）
- 每个资产用自己的赚钱逻辑
- ds.v1.2 §六：银行用真实 z-score + sigmoid（非分位线性映射）
"""
import numpy as np
from typing import Dict, Optional

from config.settings import (
    FACTOR_WEIGHTS,
    KECHUANG_TREND_OFF_MULTIPLIER,
)


def sigmoid(x: float, k: float = 1.0) -> float:
    """sigmoid 映射到 (0,1)，k 控制陡峭度"""
    return float(1.0 / (1.0 + np.exp(-k * x)))


def score_baijiu(pe_percentile: Optional[float]) -> Optional[float]:
    """白酒：1 - PE分位"""
    if pe_percentile is None:
        return None
    return float(1.0 - pe_percentile)


def score_bank(
    pb_zscore: Optional[float],
    dividend_zscore: Optional[float],
) -> Optional[float]:
    """
    银行：sigmoid(0.5 * PB_zscore + 0.5 * 股息_zscore)

    ds.v1.2 §五·银行：
      复合 z-score = 配置权重加权的两个标准分。
    """
    if pb_zscore is None or dividend_zscore is None:
        return None

    weights = FACTOR_WEIGHTS["银行ETF"]
    composite = (
        weights["pb_percentile"] * pb_zscore
        + weights["dividend_percentile"] * dividend_zscore
    )

    return sigmoid(composite)


def score_dividend(dy_percentile: Optional[float]) -> Optional[float]:
    """红利：股息率分位 = 机会分"""
    if dy_percentile is None:
        return None
    return float(dy_percentile)


def score_hs300(pe_percentile: Optional[float]) -> Optional[float]:
    """沪深300：1 - PE分位"""
    if pe_percentile is None:
        return None
    return float(1.0 - pe_percentile)


def score_kechuang(
    momentum_percentile: Optional[float],
    trend_multiplier: Optional[float],
) -> Optional[float]:
    """科创50：动量分位 × 趋势开关（OFF → ×0.5）"""
    if momentum_percentile is None or trend_multiplier is None:
        return None
    return float(momentum_percentile * trend_multiplier)


def score_all(factors: Dict[str, Dict[str, Optional[float]]]) -> Dict[str, Optional[float]]:
    """
    批量评分。输入各资产的因子值字典，输出机会分字典。

    不读取也不使用波动率/回撤等风险数据。

    Args:
        factors: {asset_name: {factor_name: value, ...}}
                 银行ETF 需要 pb_zscore 和 dividend_zscore（真实 z-score）

    Returns:
        {asset_name: opportunity_score or None}
    """
    scores = {}

    for asset_name, asset_factors in factors.items():
        if asset_name == "国债ETF":
            scores[asset_name] = None
            continue

        if asset_name == "白酒ETF":
            scores[asset_name] = score_baijiu(asset_factors.get("pe_percentile"))

        elif asset_name == "银行ETF":
            scores[asset_name] = score_bank(
                asset_factors.get("pb_zscore"),
                asset_factors.get("dividend_zscore"),
            )

        elif asset_name == "红利ETF":
            scores[asset_name] = score_dividend(
                asset_factors.get("dividend_percentile")
            )

        elif asset_name == "沪深300ETF":
            scores[asset_name] = score_hs300(asset_factors.get("pe_percentile"))

        elif asset_name == "科创50ETF":
            scores[asset_name] = score_kechuang(
                asset_factors.get("momentum_percentile"),
                asset_factors.get("trend_multiplier"),
            )

        else:
            scores[asset_name] = None

    return scores
