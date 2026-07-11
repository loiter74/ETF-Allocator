"""Canonical data-boundary normalization helpers."""
from __future__ import annotations

from datetime import date, datetime
from numbers import Integral, Real
from typing import Any, Optional


def normalize_iso_date(value: Any, *, allow_none: bool = False) -> Optional[str]:
    """Return *value* as ``YYYY-MM-DD`` or raise ``ValueError``.

    SQLite DATE columns have numeric affinity, so an eight-digit string such as
    ``"20260703"`` may be stored as an integer. Always inserting the dashed ISO
    representation prevents type-dependent date comparisons.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if allow_none:
            return None
        raise ValueError("date value is required")

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Integral):
        raw = f"{int(value):08d}"
    else:
        raw = str(value).strip()
        if raw.endswith(".0") and raw[:-2].isdigit():
            raw = raw[:-2]

    try:
        if len(raw) == 8 and raw.isdigit():
            return datetime.strptime(raw, "%Y%m%d").date().isoformat()
        # Supports ISO datetimes while deliberately ignoring their time part.
        return date.fromisoformat(raw[:10]).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid date value: {value!r}") from exc


def normalize_dividend_yield(value: Any) -> Optional[float]:
    """Normalize dividend yield to a decimal fraction.

    Providers commonly return either ``0.042`` or ``4.2`` for 4.2%. Values in
    ``(1, 100]`` are interpreted as percentages. Negative and >100% values are
    rejected as invalid source data.
    """
    if value is None or value == "":
        return None
    if not isinstance(value, Real):
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid dividend yield: {value!r}") from exc
    result = float(value)
    if result < 0 or result > 100:
        raise ValueError(f"dividend yield out of range: {result}")
    if result > 1:
        result /= 100.0
    return result
