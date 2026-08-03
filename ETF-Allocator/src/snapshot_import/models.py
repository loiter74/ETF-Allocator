"""截图导入的只读领域模型。识别值永远是草稿，不是交易事实。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FieldCandidate:
    value: str | float | None
    confidence: float
    source: str
    evidence: str = ""
    value_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": round(max(0.0, min(1.0, self.confidence)), 4),
            "source": self.source,
            "evidence": self.evidence[:240],
            "value_date": self.value_date,
        }


def empty_field() -> FieldCandidate:
    return FieldCandidate(None, 0.0, "missing")


@dataclass(frozen=True)
class PositionDraft:
    asset: FieldCandidate
    code: FieldCandidate
    shares: FieldCandidate = field(default_factory=empty_field)
    price: FieldCandidate = field(default_factory=empty_field)
    average_cost: FieldCandidate = field(default_factory=empty_field)
    market_value: FieldCandidate = field(default_factory=empty_field)
    is_equity: bool = True
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset.to_dict(),
            "code": self.code.to_dict(),
            "shares": self.shares.to_dict(),
            "price": self.price.to_dict(),
            "average_cost": self.average_cost.to_dict(),
            "market_value": self.market_value.to_dict(),
            "is_equity": self.is_equity,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SnapshotDraft:
    snapshot_date: FieldCandidate
    account_cash: FieldCandidate
    positions: tuple[PositionDraft, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_date": self.snapshot_date.to_dict(),
            "account_cash": self.account_cash.to_dict(),
            "positions": [position.to_dict() for position in self.positions],
        }


@dataclass(frozen=True)
class StructureResult:
    draft: SnapshotDraft
    provider: str
    model: str | None
    warnings: tuple[str, ...]
    input_characters: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft": self.draft.to_dict(),
            "provider": self.provider,
            "model": self.model,
            "warnings": list(self.warnings),
            "input_characters": self.input_characters,
            "read_only": True,
            "image_uploaded": False,
        }

