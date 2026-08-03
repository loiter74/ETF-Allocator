"""Shared low-frequency portfolio decision engine.

All entry points (CLI, API and backtest) adapt their inputs to these models and
call :func:`build_trade_plan`; rule implementations must not be copied outside
this package.
"""

from .models import (
    CashLedger,
    PortfolioSnapshot,
    PositionSnapshot,
    TradeOrder,
    TradePlan,
)
from .kechuang import KechuangProtectionState
from .planner import apply_confirmed_sells, build_trade_plan, strategic_equity_ratio

__all__ = [
    "CashLedger",
    "PortfolioSnapshot",
    "PositionSnapshot",
    "TradeOrder",
    "TradePlan",
    "KechuangProtectionState",
    "apply_confirmed_sells",
    "build_trade_plan",
    "strategic_equity_ratio",
]
