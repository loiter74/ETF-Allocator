"""
execution/bond_liquidity.py — 国债ETF虚拟累积池。

解决511010场内最低买入门槛（约14,000元）问题：
  - 每月固收应配金额累加到虚拟池
  - 池中余额按年化1.8%计息（逆回购近似）
  - 攒够14,000元才触发买入
  - 流A通过JSON持久化跨月保存状态
"""
import json
import os
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

from config.settings import BOND_MIN_PURCHASE, BOND_CASH_YIELD


@dataclass
class BondAction:
    """execute() 的返回值，描述本月是否触发买入。"""
    buy: bool
    lots: int
    amount: float


class BondAccumulator:
    """
    国债ETF虚拟累积池。

    生命周期：
      1. deposit(amount)     — 每月固收应配金额入池
      2. accrue_interest()   — 按月计息
      3. execute()           — 判断是否触发买入
      4. get_status()        — 报告层用的状态快照
      5. save(path)/load(path) — 流A跨月持久化
    """

    def __init__(self, min_purchase: float = BOND_MIN_PURCHASE):
        self._balance: float = 0.0
        self._min_purchase: float = min_purchase
        self._total_interest: float = 0.0

    def deposit(self, amount: float) -> None:
        """每月固收应配金额入池。"""
        self._balance += amount

    def accrue_interest(self, annual_rate: float = BOND_CASH_YIELD) -> float:
        """
        按月累积逆回购收益。

        月化利率 = annual_rate / 12，应用于当前余额。
        返回本次利息金额。
        """
        if self._balance <= 0:
            return 0.0
        monthly_rate = annual_rate / 12
        interest = self._balance * monthly_rate
        self._balance += interest
        self._total_interest += interest
        return interest

    def execute(self) -> BondAction:
        """
        判断是否触发买入。

        余额 >= 最低买入金额 → 买入 floor(balance / min_purchase) 手
        余额不足 → 不操作，余额继续累积
        """
        if self._balance >= self._min_purchase:
            lots = int(self._balance // self._min_purchase)
            buy_amount = lots * self._min_purchase
            self._balance -= buy_amount
            return BondAction(buy=True, lots=lots, amount=buy_amount)
        return BondAction(buy=False, lots=0, amount=0.0)

    def get_status(self) -> dict:
        """
        返回状态快照，供报告层使用。

        Returns:
            {
                "balance": 当前余额,
                "min_purchase": 最低买入金额,
                "total_interest": 累计逆回购收益,
                "can_buy": 是否可触发买入,
                "lots_available": 可买手数,
            }
        """
        return {
            "balance": self._balance,
            "min_purchase": self._min_purchase,
            "total_interest": self._total_interest,
            "can_buy": self._balance >= self._min_purchase,
            "lots_available": int(self._balance // self._min_purchase),
        }

    def save(self, path: str) -> None:
        """将状态持久化为JSON文件（流A跨月保存）。"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "balance": self._balance,
            "total_interest": self._total_interest,
            "min_purchase": self._min_purchase,
            "last_update": date.today().isoformat(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str, min_purchase: float = BOND_MIN_PURCHASE) -> "BondAccumulator":
        """
        从JSON文件恢复状态。

        文件不存在时返回余额=0的新实例（首次运行）。
        """
        acc = cls(min_purchase=min_purchase)
        if not os.path.exists(path):
            return acc
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            acc._balance = data.get("balance", 0.0)
            acc._total_interest = data.get("total_interest", 0.0)
        except (json.JSONDecodeError, KeyError):
            pass  # 文件损坏时返回空实例
        return acc
