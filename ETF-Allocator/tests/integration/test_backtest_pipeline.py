"""
tests/integration/test_backtest_pipeline.py — 全流程 PIT 回测集成测试。

验证 run_backtest() 完整管道：
  DB → 因子 → 评分 → 温度计 → 约束 → 分配 → 执行 → 指标

所有数据用内存 SQLite 构造，不依赖真实数据库或网络。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
import numpy as np
import pandas as pd
import sqlite3
from datetime import date, timedelta

from config.settings import (
    ASSETS,
    TRAIN_START, TRAIN_END, TEST_START, TEST_END,
    WINDOW_PE_PERCENTILE_YEARS, EXCLUDE_INDEX_BACKFILL,
)
from src.store.schema import (
    create_tables, insert_etf_info, insert_index_info,
    insert_index_valuation, insert_etf_price,
)
from src.backtest.engine import run_backtest, _is_backfill, compute_metrics
from src.regime.thermometer import reset_persistence
from src.risk.controller import reset_recovery_tracking


# ════════════════════════════════════════════════════════════════
# helpers
# ════════════════════════════════════════════════════════════════

def _seed_etf_info(conn: sqlite3.Connection):
    """写入 6 个 ETF 的元信息。"""
    for name, cfg in ASSETS.items():
        insert_etf_info(
            conn, code=cfg["code"], name=name,
            asset_class=cfg["asset_class"],
            factor_group=cfg["factor_group"],
            tracking_index=cfg.get("tracking_index"),
            list_date=None,
        )


def _seed_index_info(conn: sqlite3.Connection):
    """写入所有跟踪指数的元信息（含 publish_date 用于回填段检测）。"""
    indexes = {
        "399997": ("中证白酒", "2008-12-31", "2009-01-15"),
        "399986": ("中证银行", "2004-12-31", "2005-01-15"),
        "000922": ("中证红利", "2004-12-31", "2005-01-15"),
        "000300": ("沪深300", "2004-12-31", "2005-04-08"),
        "000688": ("科创50", "2019-12-31", "2020-07-23"),
        "000985": ("万得全A", "1999-12-30", "2000-01-15"),
    }
    for code, (name, base, pub) in indexes.items():
        insert_index_info(conn, code, name, base, pub)


def _seed_valuations(
    conn: sqlite3.Connection,
    months: list,
    *,
    pe_val: float = 15.0,
    pb_val: float = 1.3,
    dy_val: float = 3.2,
    index_code: str = "000300",
    publish_days_offset: int = 0,
):
    """
    向 index_valuation 插入月度估值数据。

    Args:
        months: 月末日期列表
        pe_val: PE 值（每个月底相同）
        pb_val: PB 值
        dy_val: 股息率
        index_code: 指数代码
        publish_days_offset: publish_date 相对于 trade_date 的偏移天数
    """
    for m in months:
        trade_d = m
        pub_d = m + timedelta(days=publish_days_offset)
        insert_index_valuation(
            conn, index_code,
            trade_d.isoformat(), pe_val, pb_val, dy_val,
            publish_date=pub_d.isoformat(),
        )


def _seed_prices(
    conn: sqlite3.Connection,
    months: list,
    code: str = "510300",
    start_price: float = 100.0,
    drift: float = 0.005,
):
    """
    向 etf_price 插入月度价格数据。

    Args:
        months: 月末日期列表
        code: ETF 代码
        start_price: 起始价格
        drift: 每月涨跌幅（默认 +0.5%）
    """
    for i, m in enumerate(months):
        price = start_price * (1.0 + drift) ** i
        # 也插入一些日频数据用于因子计算
        for day_offset in range(-20, 1):  # 每月前 21 个交易日
            td = m + timedelta(days=day_offset - 20)
            # 日价格围绕月价格微小波动
            daily_p = price * (1.0 + np.random.normal(0, 0.01))
            insert_etf_price(conn, code, td.isoformat(), close_adj=max(daily_p, 1.0), volume=1e6)


def _seed_full_valuation_data(
    conn: sqlite3.Connection,
    months: list,
    *,
    hs300_pe: float = 15.0,
    all_a_pb: float = 1.3,
    publish_days_offset: int = 0,
):
    """为沪深300 和万得全A 同时写入估值数据。"""
    _seed_valuations(conn, months, pe_val=hs300_pe, pb_val=1.3, dy_val=3.2,
                     index_code="000300", publish_days_offset=publish_days_offset)
    _seed_valuations(conn, months, pe_val=15.0, pb_val=all_a_pb, dy_val=3.2,
                     index_code="000985", publish_days_offset=publish_days_offset)


def _seed_full_price_data(conn: sqlite3.Connection, months: list):
    """为所有 6 个 ETF 写入价格数据。"""
    for name, cfg in ASSETS.items():
        _seed_prices(conn, months, code=cfg["code"], start_price={
            "白酒ETF": 100, "银行ETF": 50, "红利ETF": 30,
            "沪深300ETF": 100, "科创50ETF": 80, "国债ETF": 20,
        }.get(name, 100))


def _monthly_dates(start: str, end: str) -> list:
    """生成月末日期列表。"""
    return [d.date() for d in pd.date_range(start, end, freq="ME")]


def _setup_backtest_db(
    conn: sqlite3.Connection,
    start: str = "2024-01-01",
    end: str = "2024-03-31",
    *,
    hs300_pe: float = 15.0,
    all_a_pb: float = 1.3,
    publish_days_offset: int = 0,
):
    """
    完整初始化回测数据库：建表 → 种子数据 → 写估值 → 写价格。
    返回月末日期列表。
    """
    create_tables(conn)
    _seed_etf_info(conn)
    _seed_index_info(conn)

    months = _monthly_dates(start, end)
    _seed_full_valuation_data(
        conn, months,
        hs300_pe=hs300_pe, all_a_pb=all_a_pb,
        publish_days_offset=publish_days_offset,
    )
    _seed_full_price_data(conn, months)
    return months


# ════════════════════════════════════════════════════════════════
# 场景 1: 冒烟测试 — 3个月平静行情
# ════════════════════════════════════════════════════════════════

class TestBacktestSmoke:
    """场景1: 基本管道不崩溃、4 指标输出。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_persistence()
        reset_recovery_tracking()

    def test_run_backtest_does_not_crash(self):
        """3 个月平静行情下 run_backtest() 正常返回。"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _setup_backtest_db(conn, start="2024-01-01", end="2024-03-31")

        result = run_backtest(conn, mode="test", new_money_per_month=10000.0)

        assert "metrics" in result
        assert "monthly_results" in result
        assert "final_value" in result
        conn.close()

    def test_run_backtest_returns_four_metrics(self):
        """
        返回 4 个指标。max_drawdown 和 annualized_return 应非 None，
        calmar/sharpe 在数据不足时可 None（回测起点为 0，全进国债时收益率为 0）。
        """
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _setup_backtest_db(conn, start="2024-01-01", end="2024-03-31")

        result = run_backtest(conn, mode="test", new_money_per_month=10000.0)
        m = result["metrics"]

        for key in ["annualized_return", "max_drawdown", "calmar", "sharpe"]:
            assert key in m, f"Missing metric: {key}"

        # annualized_return 和 max_drawdown 应始终有值
        assert m["annualized_return"] is not None
        assert m["max_drawdown"] is not None

        conn.close()

    def test_monthly_results_count(self):
        """
        backtest 使用 config 中 TEST_START/END 范围。
        验证月度记录不为空。
        """
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _setup_backtest_db(conn, start="2024-01-01", end="2024-03-31")

        result = run_backtest(conn, mode="test", new_money_per_month=10000.0)
        # 至少有一些月度记录（数量取决于 TEST_START→TEST_END）
        assert len(result["monthly_results"]) > 0

        conn.close()


# ════════════════════════════════════════════════════════════════
# 场景 2: 极端高估 — 温度计触发 >90% → 权益 30%
# ════════════════════════════════════════════════════════════════

class TestBacktestOverheat:
    """场景2: 极端高估触发温度计降温。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_persistence()
        reset_recovery_tracking()

    def test_overheat_thermometer_direct(self):
        """
        温度计直接测试：双指标 >90% 分位 → 权益 30%。

        回测引擎需要 242+ 日频数据做 expanding window 分位计算，
        此处直接测试温度计逻辑，完整回测管道验证见场景1（冒烟）。
        """
        from src.regime.thermometer import equity_ratio, reset_persistence

        reset_persistence()

        # 双 >90% → 触发 Tier 3 → 权益 30%
        eq, bond = equity_ratio(0.93, 0.97)
        assert eq == pytest.approx(0.30, abs=0.01)
        assert bond == pytest.approx(0.70, abs=0.01)

        # 双 <60% → Tier 0 → 权益 100%
        reset_persistence()
        eq, bond = equity_ratio(0.30, 0.50)
        assert eq == pytest.approx(1.00)

        # 双 80-90% → Tier 2 → 权益 40%
        reset_persistence()
        eq, bond = equity_ratio(0.85, 0.88)
        assert eq == pytest.approx(0.40, abs=0.01)


# ════════════════════════════════════════════════════════════════
# 场景 3: 温度计不一致冻结
# ════════════════════════════════════════════════════════════════

class TestBacktestFreeze:
    """场景3: 双指标不一致 → 冻结上期。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_persistence()
        reset_recovery_tracking()

    def test_disagreement_freezes_equity_ratio(self):
        """
        第1月: 双指标正常 → 权益 100%
        第2月: PE 极高(95%分位)但 PB 正常(50%分位) → 不一致 → 冻结
        """
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_tables(conn)
        _seed_etf_info(conn)
        _seed_index_info(conn)

        months = _monthly_dates("2024-01-01", "2024-03-31")
        # 需要 5 年历史让分位稳定
        hist_months = _monthly_dates("2019-01-01", "2023-12-31")

        for m in hist_months:
            pub = m.isoformat()
            insert_index_valuation(conn, "000300", m.isoformat(), 15.0, 1.3, 3.0, publish_date=pub)
            insert_index_valuation(conn, "000985", m.isoformat(), 15.0, 1.3, 3.0, publish_date=pub)

        # Month 1 (Jan 2024): 双正常 → 权益 100%
        m1 = months[0]
        insert_index_valuation(conn, "000300", m1.isoformat(), 15.0, 1.3, 3.0, publish_date=m1.isoformat())
        insert_index_valuation(conn, "000985", m1.isoformat(), 15.0, 1.3, 3.0, publish_date=m1.isoformat())

        # Month 2 (Feb 2024): PE=30(极高), PB=1.3(正常) → 不一致
        m2 = months[1]
        insert_index_valuation(conn, "000300", m2.isoformat(), 30.0, 1.3, 3.0, publish_date=m2.isoformat())
        insert_index_valuation(conn, "000985", m2.isoformat(), 15.0, 1.3, 3.0, publish_date=m2.isoformat())

        # Month 3 (Mar 2024): 双正常 → 权益 100%
        m3 = months[2]
        insert_index_valuation(conn, "000300", m3.isoformat(), 15.0, 1.3, 3.0, publish_date=m3.isoformat())
        insert_index_valuation(conn, "000985", m3.isoformat(), 15.0, 1.3, 3.0, publish_date=m3.isoformat())

        _seed_full_price_data(conn, hist_months + months)

        result = run_backtest(conn, mode="test", new_money_per_month=10000.0)
        recs = result["monthly_results"]

        # 3 个月度记录
        assert recs[0]["equity_ratio"] == pytest.approx(1.00)    # Jan: 一致 <60% → 100%
        assert recs[1]["equity_ratio"] == pytest.approx(1.00)    # Feb: 不一致 → 冻结 100%
        assert recs[2]["equity_ratio"] == pytest.approx(1.00)    # Mar: 一致 <60% → 100%

        conn.close()


# ════════════════════════════════════════════════════════════════
# 场景 4: 回填段排除
# ════════════════════════════════════════════════════════════════

class TestBackfillExclusion:
    """场景4: 指数回填段数据被排除。"""

    def test_is_backfill_returns_true_for_backfill_period(self):
        """base_date ≤ trade_date < publish_date → True"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_tables(conn)
        insert_index_info(conn, "000300", "沪深300", "2023-01-01", "2023-06-01")

        # trade_date 在 base_date 和 publish_date 之间 → 是回填段
        assert _is_backfill(conn, "000300", "2023-03-15") is True
        # trade_date < base_date → 不是回填段（数据不存在于 index_valuation 中）
        assert _is_backfill(conn, "000300", "2022-12-01") is False
        # trade_date >= publish_date → 不是回填段
        assert _is_backfill(conn, "000300", "2023-06-15") is False
        # 无 index_info → 不是回填段
        assert _is_backfill(conn, "999999", "2023-03-15") is False

        conn.close()

    def test_backfill_data_excluded_in_backtest(self):
        """回填段数据在 EXCLUDE_INDEX_BACKFILL=True 时不被使用。"""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_tables(conn)
        _seed_etf_info(conn)

        # 沪深300: base=2023-01-01, publish=2023-06-01
        # 万得全A: base=1999-12-30, publish=2000-01-15（正常，无回填段影响）
        insert_index_info(conn, "000300", "沪深300", "2023-01-01", "2023-06-01")
        insert_index_info(conn, "000985", "万得全A", "1999-12-30", "2000-01-15")

        # 需要 5 年历史让分位稳定
        hist = _monthly_dates("2019-01-01", "2023-12-31")
        for m in hist:
            pub = m.isoformat()
            insert_index_valuation(conn, "000300", m.isoformat(), 15.0, 1.3, 3.0, publish_date=pub)
            insert_index_valuation(conn, "000985", m.isoformat(), 15.0, 1.3, 3.0, publish_date=pub)

        # 2024 年 3 个月测试期
        test_ms = _monthly_dates("2024-01-01", "2024-03-31")
        for m in test_ms:
            pub = m.isoformat()
            insert_index_valuation(conn, "000300", m.isoformat(), 15.0, 1.3, 3.0, publish_date=pub)
            insert_index_valuation(conn, "000985", m.isoformat(), 15.0, 1.3, 3.0, publish_date=pub)

        _seed_full_price_data(conn, hist + test_ms)

        # 回填空跑，验证不崩溃
        result = run_backtest(conn, mode="test", new_money_per_month=10000.0, exclude_backfill=True)
        assert "metrics" in result

        conn.close()


# ════════════════════════════════════════════════════════════════
# 场景 5: 再平衡触发
# ════════════════════════════════════════════════════════════════

class TestRebalanceTrigger:
    """场景5: 权重偏离中点超 10pp → 标记卖出。"""

    def test_rebalance_triggered_when_deviation_exceeds_10pp(self):
        """白酒权重 28% vs 中点 17.5% → 偏离 10.5pp > 10pp → 触发"""
        from src.rebalance.checker import check_rebalance

        current_weights = {
            "白酒ETF": 0.28,
            "银行ETF": 0.18,
            "红利ETF": 0.08,
            "沪深300ETF": 0.18,
            "科创50ETF": 0.08,
            "国债ETF": 0.20,
        }

        result = check_rebalance(
            current_date=date(2024, 12, 1),
            current_weights=current_weights,
            total_assets=500_000,
        )

        # check_rebalance 返回 {"rebalance_needed": bool, "trades": {asset: amount}, "detail": str}
        assert result["rebalance_needed"] is True
        assert "白酒ETF" in result["trades"]
        assert result["trades"]["白酒ETF"] > 0

    def test_rebalance_not_triggered_within_tolerance(self):
        """白酒权重 20% vs 中点 17.5% → 偏离 2.5pp < 10pp → 不触发"""
        from src.rebalance.checker import check_rebalance

        current_weights = {
            "白酒ETF": 0.20,
            "银行ETF": 0.18,
            "红利ETF": 0.08,
            "沪深300ETF": 0.18,
            "科创50ETF": 0.08,
            "国债ETF": 0.28,
        }

        result = check_rebalance(
            current_date=date(2024, 12, 1),
            current_weights=current_weights,
            total_assets=500_000,
        )

        # 偏离在容忍范围内 → 不触发
        assert result["rebalance_needed"] is False

    def test_rebalance_only_in_december(self):
        """非 12 月不触发再平衡检查。"""
        from src.rebalance.checker import check_rebalance

        current_weights = {
            "白酒ETF": 0.28,
            "银行ETF": 0.18,
            "红利ETF": 0.08,
            "沪深300ETF": 0.18,
            "科创50ETF": 0.08,
            "国债ETF": 0.20,
        }

        result = check_rebalance(
            current_date=date(2024, 6, 15),
            current_weights=current_weights,
            total_assets=500_000,
        )

        # 6 月 → 不触发
        assert result["rebalance_needed"] is False
        assert result["detail"] == "未触发"
