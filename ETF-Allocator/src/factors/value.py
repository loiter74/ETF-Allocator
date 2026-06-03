"""
factors/value.py — PE/PB 滚动历史分位计算 (expanding window)。

核心规则：
- 只用 expanding window（从数据起始到当前日，不超过 max_window_years）
- 分位输出 ∈ [0, 1]
- 数据不足 1 年 → 返回 None
"""
import pandas as pd
import numpy as np
from typing import Optional

from config.settings import TRADING_DAYS_PER_YEAR


def expanding_percentile(values: pd.Series, current_value: float) -> float:
    """
    计算 current_value 在 values 序列中的百分位 ∈ [0, 1]。

    使用(基于0的排名) / (n-1) 公式确保：
    - 最小值 → 0.0
    - 最大值 → 1.0
    - 中位数 → ≈0.5

    Args:
        values: 历史值序列（已经截断到 expanding window）
        current_value: 当前最新值

    Returns:
        分位值 [0, 1]
    """
    clean = values.dropna().sort_values().reset_index(drop=True)
    n = len(clean)
    if n == 0:
        return 0.0
    if n == 1:
        return 0.0

    # 找到 current_value 在排序序列中的位置
    # strict less than 的数量
    rank = int((clean < current_value).sum())
    # percentile = rank / (n-1)，夹到 [0,1]
    result = rank / (n - 1)
    return float(np.clip(result, 0.0, 1.0))


def _expand_truncate(
    series: pd.Series,
    max_window_years: int,
    min_days: int = TRADING_DAYS_PER_YEAR,
) -> pd.Series:
    """
    截断到最多 max_window_years，但如果总数据量不足 min_days，返回空。
    """
    if len(series.dropna()) < min_days:
        return pd.Series(dtype=float)

    max_days = max_window_years * TRADING_DAYS_PER_YEAR
    if len(series) > max_days:
        return series.iloc[-max_days:]
    return series


def pe_percentile(
    pe_series: pd.Series, max_window_years: int = 5
) -> Optional[float]:
    """
    计算当前 PE 在历史 expanding window 中的分位。
    分位越低 → PE 越便宜 → 机会越好。

    Returns:
        分位 ∈ [0, 1]，数据不足返回 None
    """
    truncated = _expand_truncate(pe_series, max_window_years)
    if len(truncated) == 0:
        return None
    # 过滤异常值：PE < 0 或 PE > 500 为数据错误
    truncated = truncated[(truncated > 0) & (truncated < 500)]
    if len(truncated) == 0:
        return None
    current = truncated.iloc[-1]
    return expanding_percentile(truncated, current)


def pb_percentile(
    pb_series: pd.Series, max_window_years: int = 5
) -> Optional[float]:
    """
    同 pe_percentile，用于 PB。
    对银行等金融股，PB 解释力 > PE。
    """
    truncated = _expand_truncate(pb_series, max_window_years)
    if len(truncated) == 0:
        return None
    # 过滤异常值：PB < 0 或 PB > 50 为数据错误
    truncated = truncated[(truncated > 0) & (truncated < 50)]
    if len(truncated) == 0:
        return None
    current = truncated.iloc[-1]
    return expanding_percentile(truncated, current)


def compute_zscore(
    series: pd.Series, max_window_years: int = 5
) -> Optional[float]:
    """
    ds.v1.2 §五·银行：真实 z-score 计算。

    z = (当前值 - 历史均值) / 历史标准差

    历史序列排除最后一个值（当前值），防止当前值"污染"分布参数。
    例如：银行 PB 高 → z > 0 → sigmoid 后机会分高。

    Returns:
        z-score（小数），数据不足返回 None
    """
    truncated = _expand_truncate(series, max_window_years)
    clean = truncated.dropna()
    if len(clean) < 2:
        return None

    current = clean.iloc[-1]
    hist = clean.iloc[:-1]  # 排除当前值

    mean = float(hist.mean())
    std = float(hist.std(ddof=1))

    if std < 1e-12:
        return 0.0

    return float((current - mean) / std)
