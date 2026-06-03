"""
src/backtest/splitter.py — Train/test date-split.

流B 验证流的前置步骤：把历史数据按日期切分为训练期和测试期。
训练期→调参(锁死)，测试期→只看不调。
"""
import pandas as pd
from typing import Tuple

from config.settings import TRAIN_START, TRAIN_END, TEST_START, TEST_END

__all__ = ["DEFAULT_SPLIT", "split_by_date"]

DEFAULT_SPLIT = {
    "train_start": TRAIN_START,
    "train_end": TRAIN_END,
    "test_start": TEST_START,
    "test_end": TEST_END,
}


def split_by_date(
    df: pd.DataFrame,
    date_col: str = "trade_date",
    train_start: str = TRAIN_START,
    train_end: str = TRAIN_END,
    test_start: str = TEST_START,
    test_end: str = TEST_END,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split a DataFrame into train and test sets by a date column.

    Returns:
        (train_df, test_df) — rows where date_col falls in the respective range.
        Each DataFrame may be empty if no rows match.
    """
    col = df[date_col]
    train = df[(col >= train_start) & (col <= train_end)].copy()
    test = df[(col >= test_start) & (col <= test_end)].copy()
    return train, test
