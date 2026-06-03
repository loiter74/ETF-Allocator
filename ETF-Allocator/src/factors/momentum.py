"""
factors/momentum.py — 120日动量 + 200日均线趋势开关。

ds.v1.2 规则：
- 趋势 ON (Price ≥ MA200) → 不减半
- 趋势 OFF (Price < MA200) → 机会分 × 0.50
"""
import pandas as pd
import numpy as np
from typing import Optional

from config.settings import (
    WINDOW_MOMENTUM_DAYS,
    WINDOW_MA_TREND_DAYS,
    KECHUANG_TREND_OFF_MULTIPLIER,
)
from src.factors.value import expanding_percentile


def momentum_120d(price_series: pd.Series) -> Optional[float]:
    """
    120 日动量 = (今日收盘 - 120日前收盘) / 120日前收盘。

    Returns:
        收益率（小数），数据不足返回 None
    """
    clean = price_series.dropna()
    if len(clean) < WINDOW_MOMENTUM_DAYS + 1:
        return None
    current = clean.iloc[-1]
    past = clean.iloc[-(WINDOW_MOMENTUM_DAYS + 1)]
    if past == 0:
        return None
    return float((current - past) / past)


def ma_trend_200d(price_series: pd.Series) -> bool:
    """
    200 日均线趋势开关。
    Price ≥ MA200 → ON (True)
    Price < MA200 → OFF (False)
    数据不足 → OFF (保守)
    """
    clean = price_series.dropna()
    if len(clean) < WINDOW_MA_TREND_DAYS:
        return False
    ma200 = clean.iloc[-WINDOW_MA_TREND_DAYS:].mean()
    current = clean.iloc[-1]
    return bool(current >= ma200)


def kechuang_opportunity(
    price_series: pd.Series,
    max_window_years: int = 5,
) -> Optional[float]:
    """
    科创50 机会分 = 动量分位 × 趋势开关系数。

    步1：计算 120 日动量
    步2：计算动量在历史 expanding window 中的分位
    步3：趋势 ON → multiplier = 1.0；趋势 OFF → multiplier = 0.50

    Returns:
        机会分 ∈ [0, 1]，数据不足返回 None
    """
    mom = momentum_120d(price_series)
    if mom is None:
        return None

    # 动量分位：需要历史动量序列
    # 构造滚动动量序列
    clean = price_series.dropna()
    min_len = WINDOW_MOMENTUM_DAYS + 1
    if len(clean) < min_len:
        return None

    momentum_history = []
    for i in range(min_len, len(clean) + 1):
        window = clean.iloc[:i]
        m = momentum_120d(window)
        if m is not None:
            momentum_history.append(m)

    if len(momentum_history) < 20:  # 至少需要一些历史
        return None

    # 动量分位：越高越好
    mom_series = pd.Series(momentum_history)
    mom_percentile = expanding_percentile(mom_series, mom)

    # 趋势开关
    trend_on = ma_trend_200d(price_series)
    multiplier = 1.00 if trend_on else KECHUANG_TREND_OFF_MULTIPLIER

    return float(mom_percentile * multiplier)
