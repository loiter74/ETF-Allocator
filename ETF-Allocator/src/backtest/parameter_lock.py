"""Training/test parameter snapshot and integrity verification."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from config import settings


PARAMETER_NAMES = (
    "WINDOW_PE_PERCENTILE_YEARS",
    "WINDOW_MOMENTUM_DAYS",
    "WINDOW_MA_TREND_DAYS",
    "TEMP_THRESHOLDS",
    "TEMP_EQUITY_RATIOS",
    "THERMOMETER_DEFAULT_EQUITY",
    "RISK_CONTROL",
    "TARGET_BANDS",
    "GROUP_CAPS",
    "PENALTY_BUFFER",
    "FACTOR_WEIGHTS",
    "KECHUANG_TREND_OFF_MULTIPLIER",
    "ALLOCATION_GAP_WEIGHT",
    "ALLOCATION_OPPORTUNITY_WEIGHT",
    "MIN_OPPORTUNITY_SCORE",
    "EXCLUDE_INDEX_BACKFILL",
)


def current_parameters() -> Dict[str, Any]:
    return {name: getattr(settings, name) for name in PARAMETER_NAMES}


def parameter_hash(parameters: Dict[str, Any] | None = None) -> str:
    payload = parameters if parameters is not None else current_parameters()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def write_snapshot(path: Path) -> Dict[str, Any]:
    parameters = current_parameters()
    snapshot = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "train_range": {"start": settings.TRAIN_START, "end": settings.TRAIN_END},
        "test_range": {"start": settings.TEST_START, "end": settings.TEST_END},
        "parameter_hash": parameter_hash(parameters),
        "parameters": parameters,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return snapshot


def verify_snapshot(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, f"参数锁定快照不存在: {path}。请先运行 python validate.py train"
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"参数锁定快照无法读取: {exc}"
    expected = snapshot.get("parameter_hash")
    actual = parameter_hash()
    if expected != actual:
        return False, f"参数已改变: locked={expected}, current={actual}"
    return True, actual
