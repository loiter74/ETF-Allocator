"""Public snapshot and trade-plan domain models.

The models intentionally use the standard library so the same contracts work in
the CLI, FastAPI adapters and the backtest without framework-specific behavior.
Money is rounded only for presentation; planner arithmetic keeps float precision
and enforces the final cash identity to cents.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from config.settings import ASSETS


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _non_negative(label: str, value: float) -> float:
    number = float(value)
    if number < -1e-9:
        raise ValueError(f"{label}不能为负数")
    return max(0.0, number)


@dataclass(frozen=True)
class PositionSnapshot:
    asset: str
    code: str
    shares: float
    price: float
    market_value: Optional[float] = None
    average_cost: Optional[float] = None
    is_equity: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "shares", _non_negative(f"{self.asset}份额", self.shares))
        object.__setattr__(self, "price", _non_negative(f"{self.asset}价格", self.price))
        if self.average_cost is not None:
            object.__setattr__(
                self,
                "average_cost",
                _non_negative(f"{self.asset}平均成本", self.average_cost),
            )
        computed = self.shares * self.price
        if self.market_value is not None:
            supplied = _non_negative(f"{self.asset}市值", self.market_value)
            tolerance = max(0.01, computed * 0.001)
            if abs(supplied - computed) > tolerance:
                raise ValueError(
                    f"{self.asset}市值与份额×价格不一致: "
                    f"supplied={supplied:.2f}, computed={computed:.2f}"
                )

    @property
    def value(self) -> float:
        return self.shares * self.price

    @property
    def managed(self) -> bool:
        return self.asset in ASSETS

    @property
    def equity_exposure(self) -> bool:
        return self.asset != "国债ETF" and bool(self.is_equity)

    def with_shares(self, shares: float, *, price: Optional[float] = None) -> "PositionSnapshot":
        new_price = self.price if price is None else float(price)
        return replace(
            self,
            shares=max(0.0, float(shares)),
            price=new_price,
            market_value=max(0.0, float(shares)) * new_price,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset": self.asset,
            "code": self.code,
            "shares": self.shares,
            "price": self.price,
            "market_value": self.value,
            "average_cost": self.average_cost,
            "is_equity": self.is_equity,
            "managed": self.managed,
        }


@dataclass(frozen=True)
class PortfolioSnapshot:
    snapshot_date: date | str
    price_date: date | str
    new_money: float
    account_cash: float
    bond_pool_cash: float
    positions: Tuple[PositionSnapshot, ...] | Iterable[PositionSnapshot]
    reverse_repo_cash: float = 0.0
    equity_pending_cash: float = 0.0
    confirmed_sell_proceeds: float = 0.0
    legacy_allocation_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_date", _as_date(self.snapshot_date))
        object.__setattr__(self, "price_date", _as_date(self.price_date))
        object.__setattr__(self, "new_money", _non_negative("新增资金", self.new_money))
        object.__setattr__(self, "account_cash", _non_negative("账户现金", self.account_cash))
        object.__setattr__(self, "bond_pool_cash", _non_negative("国债累积池", self.bond_pool_cash))
        object.__setattr__(self, "reverse_repo_cash", _non_negative("逆回购", self.reverse_repo_cash))
        object.__setattr__(
            self,
            "equity_pending_cash",
            _non_negative("权益待投现金", self.equity_pending_cash),
        )
        object.__setattr__(
            self,
            "confirmed_sell_proceeds",
            _non_negative("已确认卖出净收入", self.confirmed_sell_proceeds),
        )
        positions = tuple(self.positions)
        object.__setattr__(self, "positions", positions)

        if self.price_date > self.snapshot_date:
            raise ValueError("价格日期不能晚于快照日期")
        marked_cash = self.bond_pool_cash + self.equity_pending_cash
        if marked_cash > self.account_cash + 0.01:
            raise ValueError("国债累积池与权益待投现金合计不能超过账户现金")
        if marked_cash + self.confirmed_sell_proceeds > self.account_cash + 0.01:
            raise ValueError("现金标记与已确认卖出净收入合计不能超过账户现金")

        seen_managed: set[str] = set()
        for position in positions:
            if position.managed:
                if position.asset in seen_managed:
                    raise ValueError(f"受管资产重复: {position.asset}")
                seen_managed.add(position.asset)

    @property
    def total_assets(self) -> float:
        """Whole-account assets before this month's external contribution."""
        return sum(p.value for p in self.positions) + self.account_cash + self.reverse_repo_cash

    @property
    def unknown_value(self) -> float:
        return sum(p.value for p in self.positions if not p.managed)

    @property
    def managed_total(self) -> float:
        # Free and tagged cash remain in the managed sleeve; unknown holdings do not.
        return max(0.0, self.total_assets - self.unknown_value)

    @property
    def account_equity_value(self) -> float:
        return sum(p.value for p in self.positions if p.equity_exposure)

    @property
    def account_equity_ratio(self) -> float:
        return self.account_equity_value / self.total_assets if self.total_assets > 0 else 0.0

    @property
    def defense_value(self) -> float:
        bond_value = sum(p.value for p in self.positions if p.asset == "国债ETF")
        return bond_value + self.bond_pool_cash + self.reverse_repo_cash

    @property
    def defense_ratio(self) -> float:
        return self.defense_value / self.total_assets if self.total_assets > 0 else 0.0

    def position(self, asset: str) -> Optional[PositionSnapshot]:
        return next((p for p in self.positions if p.asset == asset), None)

    def managed_values(self) -> Dict[str, float]:
        values = {name: 0.0 for name in ASSETS}
        for position in self.positions:
            if position.managed:
                values[position.asset] += position.value
        # A pool/reverse repo is economically part of the managed bond sleeve.
        values["国债ETF"] += self.bond_pool_cash + self.reverse_repo_cash
        return values

    def managed_weights(self, denominator: Optional[float] = None) -> Dict[str, float]:
        total = self.managed_total if denominator is None else float(denominator)
        if total <= 0:
            return {name: 0.0 for name in ASSETS}
        return {name: value / total for name, value in self.managed_values().items()}

    @property
    def warnings(self) -> Tuple[str, ...]:
        unknown = [p.asset for p in self.positions if not p.managed]
        if not unknown:
            return ()
        return (f"非白名单持仓仅计入账户风险，不自动交易: {', '.join(sorted(unknown))}",)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.isoformat(),
            "price_date": self.price_date.isoformat(),
            "new_money": self.new_money,
            "account_cash": self.account_cash,
            "bond_pool_cash": self.bond_pool_cash,
            "reverse_repo_cash": self.reverse_repo_cash,
            "equity_pending_cash": self.equity_pending_cash,
            "confirmed_sell_proceeds": self.confirmed_sell_proceeds,
            "legacy_allocation_only": self.legacy_allocation_only,
            "positions": [p.to_dict() for p in self.positions],
            "total_assets": self.total_assets,
        }


@dataclass(frozen=True)
class TradeOrder:
    side: str
    asset: str
    code: str
    reason_codes: Tuple[str, ...]
    shares: int
    reference_price: float
    estimated_price: float
    gross_amount: float
    commission: float
    slippage_cost: float
    cash_effect: float
    mandatory: bool
    shadow: bool = False
    allocation_stages: Tuple[str, ...] = ()
    # 各分配阶段给本资产分到的金额明细 {stage: amount}，用于可追溯审计
    stage_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "side": self.side,
            "asset": self.asset,
            "code": self.code,
            "reason_codes": list(self.reason_codes),
            "shares": self.shares,
            "reference_price": round(self.reference_price, 6),
            "estimated_price": round(self.estimated_price, 6),
            "gross_amount": round(self.gross_amount, 2),
            "commission": round(self.commission, 2),
            "slippage_cost": round(self.slippage_cost, 2),
            "cash_effect": round(self.cash_effect, 2),
            "mandatory": self.mandatory,
            "shadow": self.shadow,
            "allocation_stages": list(self.allocation_stages),
            "stage_breakdown": {k: round(v, 2) for k, v in self.stage_breakdown.items()},
        }


@dataclass(frozen=True)
class CashLedger:
    opening_cash: float
    new_money: float
    sell_net_proceeds: float
    buy_cash_outflow: float
    closing_cash: float
    bond_pool_before: float
    bond_pool_deposit: float
    bond_pool_released: float
    bond_pool_after: float
    equity_pending_before: float
    equity_pending_after: float
    free_cash_after: float
    total_commission: float
    total_slippage: float

    @property
    def cash_identity_error(self) -> float:
        expected = self.opening_cash + self.new_money + self.sell_net_proceeds - self.buy_cash_outflow
        return self.closing_cash - expected

    def to_dict(self) -> Dict[str, float]:
        data = {name: round(float(value), 2) for name, value in self.__dict__.items()}
        data["cash_identity_error"] = round(self.cash_identity_error, 2)
        return data


@dataclass(frozen=True)
class TradePlan:
    plan_id: str
    snapshot_date: date
    phase: str
    formal_sells: Tuple[TradeOrder, ...] = ()
    shadow_sells: Tuple[TradeOrder, ...] = ()
    buys: Tuple[TradeOrder, ...] = ()
    warnings: Tuple[str, ...] = ()
    before: Mapping[str, Any] = field(default_factory=dict)
    after: Mapping[str, Any] = field(default_factory=dict)
    cash_ledger: Optional[CashLedger] = None
    state_patch: Mapping[str, Any] = field(default_factory=dict)
    pending_buy_recalculation: bool = False
    legacy_allocation_only: bool = False

    def to_dict(self, *, include_state_patch: bool = False) -> Dict[str, Any]:
        result = {
            "plan_id": self.plan_id,
            "snapshot_date": self.snapshot_date.isoformat(),
            "phase": self.phase,
            "formal_sells": [order.to_dict() for order in self.formal_sells],
            "shadow_sells": [order.to_dict() for order in self.shadow_sells],
            "buys": [order.to_dict() for order in self.buys],
            "warnings": list(self.warnings),
            "before": dict(self.before),
            "after": dict(self.after),
            "cash_ledger": self.cash_ledger.to_dict() if self.cash_ledger else None,
            "pending_buy_recalculation": self.pending_buy_recalculation,
            "legacy_allocation_only": self.legacy_allocation_only,
        }
        if include_state_patch:
            result["state_patch"] = dict(self.state_patch)
        return result


def positions_from_mapping(items: Iterable[Mapping[str, Any]]) -> Tuple[PositionSnapshot, ...]:
    return tuple(PositionSnapshot(**dict(item)) for item in items)
