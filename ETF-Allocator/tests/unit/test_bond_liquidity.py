"""
tests/unit/test_bond_liquidity.py — BondAccumulator 单元测试。

覆盖：deposit、execute触发/不触发、多手、逆回购计息、状态快照、持久化。
"""
import json
import os
import tempfile

import pytest

from src.execution.bond_liquidity import BondAccumulator, BondAction


class TestBondAction:
    """BondAction dataclass 基本属性。"""

    def test_buy_action_fields(self):
        action = BondAction(buy=True, lots=2, amount=28000.0)
        assert action.buy is True
        assert action.lots == 2
        assert action.amount == 28000.0

    def test_no_buy_action_fields(self):
        action = BondAction(buy=False, lots=0, amount=0.0)
        assert action.buy is False
        assert action.lots == 0
        assert action.amount == 0.0


class TestDeposit:
    """deposit() 累加行为。"""

    def test_deposit_single(self):
        acc = BondAccumulator()
        acc.deposit(3000)
        assert acc.get_status()["balance"] == 3000.0

    def test_deposit_accumulates(self):
        acc = BondAccumulator()
        acc.deposit(3000)
        acc.deposit(5000)
        acc.deposit(2000)
        assert acc.get_status()["balance"] == 10000.0

    def test_deposit_zero(self):
        acc = BondAccumulator()
        acc.deposit(0)
        assert acc.get_status()["balance"] == 0.0


class TestExecute:
    """execute() 触发/不触发行为。"""

    def test_no_trigger_below_threshold(self):
        acc = BondAccumulator(min_purchase=14000)
        acc.deposit(8000)
        action = acc.execute()
        assert action.buy is False
        assert action.lots == 0
        assert action.amount == 0.0
        # 余额不变
        assert acc.get_status()["balance"] == 8000.0

    def test_trigger_at_exact_threshold(self):
        acc = BondAccumulator(min_purchase=14000)
        acc.deposit(14000)
        action = acc.execute()
        assert action.buy is True
        assert action.lots == 1
        assert action.amount == 14000.0
        assert acc.get_status()["balance"] == 0.0

    def test_trigger_above_threshold(self):
        acc = BondAccumulator(min_purchase=14000)
        acc.deposit(17000)
        action = acc.execute()
        assert action.buy is True
        assert action.lots == 1
        assert action.amount == 14000.0
        assert acc.get_status()["balance"] == 3000.0

    def test_trigger_multiple_lots(self):
        acc = BondAccumulator(min_purchase=14000)
        acc.deposit(31000)
        action = acc.execute()
        assert action.buy is True
        assert action.lots == 2
        assert action.amount == 28000.0
        assert acc.get_status()["balance"] == 3000.0

    def test_execute_empty_pool(self):
        acc = BondAccumulator()
        action = acc.execute()
        assert action.buy is False


class TestAccrueInterest:
    """accrue_interest() 逆回购计息。"""

    def test_interest_on_balance(self):
        acc = BondAccumulator()
        acc.deposit(11000)
        interest = acc.accrue_interest(annual_rate=0.018)
        # 11000 * 0.018 / 12 = 16.5
        assert abs(interest - 16.5) < 0.01
        assert abs(acc.get_status()["balance"] - 11016.5) < 0.01
        assert abs(acc.get_status()["total_interest"] - 16.5) < 0.01

    def test_interest_on_zero(self):
        acc = BondAccumulator()
        interest = acc.accrue_interest()
        assert interest == 0.0
        assert acc.get_status()["total_interest"] == 0.0

    def test_interest_accumulates_across_months(self):
        acc = BondAccumulator()
        acc.deposit(10000)
        total_interest = 0.0
        for _ in range(6):
            i = acc.accrue_interest(annual_rate=0.018)
            total_interest += i
        # 简单月化：10000 * 0.0015 * 6 = 90（近似，忽略复利）
        assert total_interest > 85
        assert abs(acc.get_status()["total_interest"] - total_interest) < 0.01


class TestMultiMonthSimulation:
    """模拟多月累积+触发的完整流程。"""

    def test_five_month_accumulation(self):
        """前4月累积不足，第5月触发买入。"""
        acc = BondAccumulator(min_purchase=14000)
        results = []
        for month in range(6):
            acc.deposit(3000)
            action = acc.execute()
            results.append(action)

        # 月0: 3000, no buy
        assert results[0].buy is False
        # 月1: 6000, no buy
        assert results[1].buy is False
        # 月2: 9000, no buy
        assert results[2].buy is False
        # 月3: 12000, no buy
        assert results[3].buy is False
        # 月4: 15000, buy 1 lot, remainder 1000
        assert results[4].buy is True
        assert results[4].lots == 1
        assert results[4].amount == 14000
        # 月5: 1000 + 3000 = 4000, no buy
        assert results[5].buy is False
        assert acc.get_status()["balance"] == 4000.0

    def test_with_interest(self):
        """带逆回购收益的累积。"""
        acc = BondAccumulator(min_purchase=14000)
        acc.deposit(12000)
        acc.accrue_interest(0.018)  # +18
        acc.deposit(1000)
        action = acc.execute()
        # 12000 + 18 + 1000 = 13018 < 14000
        assert action.buy is False

        acc.accrue_interest(0.018)
        acc.deposit(1000)
        action = acc.execute()
        # 13018 + interest + 1000 > 14000
        assert action.buy is True
        assert action.lots == 1


class TestGetStatus:
    """get_status() 状态快照。"""

    def test_status_fields(self):
        acc = BondAccumulator(min_purchase=14000)
        acc.deposit(5000)
        status = acc.get_status()
        assert status["balance"] == 5000.0
        assert status["min_purchase"] == 14000
        assert status["total_interest"] == 0.0
        assert status["can_buy"] is False
        assert status["lots_available"] == 0

    def test_status_can_buy(self):
        acc = BondAccumulator(min_purchase=14000)
        acc.deposit(30000)
        status = acc.get_status()
        assert status["can_buy"] is True
        assert status["lots_available"] == 2


class TestPersistence:
    """save()/load() JSON 持久化。"""

    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            acc = BondAccumulator(min_purchase=14000)
            acc.deposit(3000)
            acc.accrue_interest(0.018)
            acc.save(path)

            loaded = BondAccumulator.load(path, min_purchase=14000)
            assert abs(loaded.get_status()["balance"] - 3004.5) < 0.01
            assert abs(loaded.get_status()["total_interest"] - 4.5) < 0.01
        finally:
            os.unlink(path)

    def test_load_missing_file(self):
        loaded = BondAccumulator.load("/nonexistent/path.json")
        assert loaded.get_status()["balance"] == 0.0
        assert loaded.get_status()["total_interest"] == 0.0

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "accumulator.json")
            acc = BondAccumulator()
            acc.deposit(1000)
            acc.save(path)
            assert os.path.exists(path)

            loaded = BondAccumulator.load(path)
            assert loaded.get_status()["balance"] == 1000.0
