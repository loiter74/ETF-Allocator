"""
tests/fixtures/data.py — 共享测试数据构造 fixtures。

集中管理 16 个测试文件共同使用的数据构造函数，消除重复。
所有 fixtures 不依赖外部网络或真实数据库。
"""
import pytest
import numpy as np
import pandas as pd
import sqlite3
from datetime import date


# ── DB fixture ──

@pytest.fixture(scope="function")
def memory_db():
    """内存 SQLite 数据库，已建表，每个测试独立隔离。"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from src.store.schema import create_tables
    create_tables(conn)
    yield conn
    conn.close()


# ── 价格序列 fixture ──

@pytest.fixture(scope="function")
def sample_prices() -> pd.Series:
    """
    300 天价格序列，从 100 单调上升至 ~150。
    索引为 DatetimeIndex (2023-01-01 起，B 频)。
    足够计算 120 日动量 + 200 日均线 + 60 日波动率。
    """
    np.random.seed(42)
    dates = pd.date_range(start="2023-01-01", periods=300, freq="B")
    # 每日收益率 ~0.05%，累积到 ~116 → 加趋势到 ~150
    daily_r = np.random.normal(0.0005, 0.015, 300)
    prices = 100.0 * np.cumprod(1.0 + daily_r)
    # 再加一个上升趋势确保大致单调向上
    trend = np.linspace(1.0, 1.3, 300)
    final = prices * trend
    return pd.Series(final, index=dates)


# ── 估值序列 fixture ──

@pytest.fixture(scope="function")
def sample_valuations():
    """
    返回 (pe_series, pb_series, dy_series) 三元组。
    各 300 天，数值范围贴近真实市场：
      PE ∈ [10, 30], PB ∈ [0.8, 2.0], 股息率 ∈ [2%, 5%]
    """
    np.random.seed(42)
    n = 300
    dates = pd.date_range(start="2023-01-01", periods=n, freq="B")

    # PE: 围绕 15 波动，加轻微趋势
    pe_vals = 15.0 + np.cumsum(np.random.normal(0, 0.3, n))
    pe_vals = np.clip(pe_vals, 10.0, 30.0)

    # PB: 与 PE 正相关（合理关联）
    pb_vals = 1.2 + (pe_vals - 15.0) * 0.05 + np.random.normal(0, 0.05, n)
    pb_vals = np.clip(pb_vals, 0.8, 2.0)

    # 股息率: 与 PE 负相关（高 PE = 贵 = 低股息率）
    dy_vals = 4.5 - (pe_vals - 15.0) * 0.15 + np.random.normal(0, 0.1, n)
    dy_vals = np.clip(dy_vals, 2.0, 5.0)

    pe_s = pd.Series(pe_vals, index=dates)
    pb_s = pd.Series(pb_vals, index=dates)
    dy_s = pd.Series(dy_vals, index=dates)

    return pe_s, pb_s, dy_s


# ── 标准权重 fixture ──

@pytest.fixture(scope="function")
def standard_weights() -> dict:
    """
    6 资产标准权重，总和 = 1.0。
    权重分布：白酒12%, 银行18%, 红利8%, 沪深30022%, 科创50 13%, 国债27%
    """
    return {
        "白酒ETF": 0.12,
        "银行ETF": 0.18,
        "红利ETF": 0.08,
        "沪深300ETF": 0.22,
        "科创50ETF": 0.13,
        "国债ETF": 0.27,
    }


# ── 标准机会分 fixture ──

@pytest.fixture(scope="function")
def standard_scores() -> dict:
    """
    6 资产机会分，国债为 None。
    白酒0.85, 银行0.88, 红利0.80, 沪深3000.78, 科创50 0.92, 国债 None
    """
    return {
        "白酒ETF": 0.85,
        "银行ETF": 0.88,
        "红利ETF": 0.80,
        "沪深300ETF": 0.78,
        "科创50ETF": 0.92,
        "国债ETF": None,
    }
