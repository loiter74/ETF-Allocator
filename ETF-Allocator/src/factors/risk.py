"""
factors/risk.py — 波动率与最大回撤计算。
风险因子不进评分，仅输出给 risk controller 使用。

使用窗口参数来自 config/settings.py。
"""
import pandas as pd
import numpy as np
from typing import Optional

from config.settings import (
    TRADING_DAYS_PER_YEAR,
    WINDOW_VOL_DAYS,
    WINDOW_MAX_DRAWDOWN_DAYS,
)


def annualized_volatility(
    price_series: pd.Series, window: int = WINDOW_VOL_DAYS
) -> Optional[float]:
    """
    年化波动率（基于日收益率标准差 × √242）。

    Args:
        price_series: 日频价格序列
        window: 滚动窗口（交易日）

    Returns:
        年化波动率（小数），数据不足返回 None
    """
    clean = price_series.dropna()
    if len(clean) < window + 1:
        return None

    recent = clean.iloc[-(window + 1):]
    daily_returns = recent.pct_change().dropna()
    daily_std = daily_returns.std()
    annualized = daily_std * np.sqrt(TRADING_DAYS_PER_YEAR)
    return float(annualized)


def max_drawdown(
    price_series: pd.Series, window: int = WINDOW_MAX_DRAWDOWN_DAYS
) -> Optional[float]:
    """
    滚动窗口内的最大回撤。

    公式：min(price / running_max - 1)，结果 ≤ 0。

    Returns:
        最大回撤（负小数，如 -0.30 表示 -30%），数据不足返回 None
    """
    clean = price_series.dropna()
    if len(clean) < 2:
        return None

    recent = clean.iloc[-window:] if len(clean) > window else clean
    running_max = recent.cummax()
    drawdowns = recent / running_max - 1
    return float(drawdowns.min())
