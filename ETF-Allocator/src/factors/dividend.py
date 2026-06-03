"""
factors/dividend.py — 股息率滚动分位计算。
方向：股息率越高 → 分位越高（与 PE 分位相反）。
"""
import pandas as pd
from typing import Optional

from src.factors.value import expanding_percentile, _expand_truncate


def dividend_yield_percentile(
    dy_series: pd.Series, max_window_years: int = 5
) -> Optional[float]:
    """
    计算当前股息率在历史 expanding window 中的分位。
    股息率越高 → 分位越高 → 机会越好。

    Returns:
        分位 ∈ [0, 1]，数据不足返回 None
    """
    truncated = _expand_truncate(dy_series, max_window_years)
    if len(truncated) == 0:
        return None
    # 过滤异常值：股息率 > 100% 显然为数据错误（正常范围 0-15%）
    truncated = truncated[truncated < 1.0]
    if len(truncated) == 0:
        return None
    current = truncated.iloc[-1]
    return expanding_percentile(truncated, current)
