"""
regime/thermometer.py — 市场温度计（MarketRegime）。

ds.v1.2 §七 设计（4档分级 + 不一致冻结）：
- 双指标(p1=沪深300 PE分位, p2=全A PB分位) 各自判定档位
- 档位一致 → 返回对应权益比，并记住本次比例
- 档位不一致 → 返回上次记住的比例（冻结）
- 首调用无历史 → 默认权益 100%

档位表：
  双 <60%  → 权益 100%
  双 60-80% → 权益 70%
  双 80-90% → 权益 40%
  双 >90%  → 权益 30%
"""
import json
from pathlib import Path
from typing import Optional, Tuple, Union

from config.settings import TEMP_THRESHOLDS, TEMP_EQUITY_RATIOS, THERMOMETER_DEFAULT_EQUITY

# ── 模块级状态：用于"不一致时冻结上期比例" ──
_last_equity_ratio: Optional[float] = None
_last_bond_ratio: Optional[float] = None


def _tier(percentile: float) -> int:
    """
    将分位值映射到档位 0-3。
    thresholds = [0.60, 0.80, 0.90]
    0: < 0.60
    1: [0.60, 0.80)
    2: [0.80, 0.90)
    3: >= 0.90
    """
    for i, t in enumerate(TEMP_THRESHOLDS):
        if percentile < t:
            return i
    return len(TEMP_THRESHOLDS)  # 3（>= 0.90）


def equity_ratio(
    p1: Optional[float], p2: Optional[float],
) -> Tuple[float, float]:
    """
    4档分级温度计 + 不一致冻结。

    Args:
        p1: 沪深300 PE 分位 [0,1] 或 None
        p2: 全A PB 分位 [0,1] 或 None

    Returns:
        (equity_ratio, bond_ratio)，永不为 None
    """
    global _last_equity_ratio, _last_bond_ratio

    # 数据缺失 → 冻结（或默认配置值）
    if p1 is None or p2 is None:
        if _last_equity_ratio is not None:
            return (_last_equity_ratio, _last_bond_ratio)  # type: ignore[return-value]
        default = THERMOMETER_DEFAULT_EQUITY
        return (default, round(1.0 - default, 10))

    t1 = _tier(p1)
    t2 = _tier(p2)

    if t1 == t2:
        # 一致 → 应用对应档位
        eq = TEMP_EQUITY_RATIOS[t1]
        bond = round(1.0 - eq, 10)
        _last_equity_ratio = eq
        _last_bond_ratio = bond
        return (eq, bond)

    # 不一致 → 冻结上期比例
    if _last_equity_ratio is not None:
        return (_last_equity_ratio, _last_bond_ratio)  # type: ignore[return-value]
    # 首调用且不一致 → 使用配置的默认权益比
    return (THERMOMETER_DEFAULT_EQUITY, round(1.0 - THERMOMETER_DEFAULT_EQUITY, 10))


def resolve_equity_ratio(
    p1: Optional[float],
    p2: Optional[float],
    previous_equity_ratio: Optional[float] = None,
) -> Tuple[float, float]:
    """Pure thermometer calculation for read-only APIs."""
    if p1 is None or p2 is None or _tier(p1) != _tier(p2):
        equity = (
            previous_equity_ratio
            if previous_equity_ratio is not None
            else THERMOMETER_DEFAULT_EQUITY
        )
    else:
        equity = TEMP_EQUITY_RATIOS[_tier(p1)]
    return (float(equity), round(1.0 - float(equity), 10))


def reset_persistence() -> None:
    """重置持久化状态（用于测试和回测初始化）。"""
    global _last_equity_ratio, _last_bond_ratio
    _last_equity_ratio = None
    _last_bond_ratio = None


def load_persistence(path: Union[str, Path]) -> None:
    """Load the last valid ratio for a real cross-process monthly run."""
    global _last_equity_ratio, _last_bond_ratio
    state_path = Path(path)
    if not state_path.exists():
        return
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        equity = float(payload["equity_ratio"])
        if not 0.0 <= equity <= 1.0:
            raise ValueError("equity ratio out of range")
        _last_equity_ratio = equity
        _last_bond_ratio = round(1.0 - equity, 10)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        reset_persistence()


def read_persistence(path: Union[str, Path]) -> Optional[float]:
    """Read the persisted ratio without mutating module state."""
    state_path = Path(path)
    if not state_path.exists():
        return None
    try:
        equity = float(json.loads(state_path.read_text(encoding="utf-8"))["equity_ratio"])
        return equity if 0.0 <= equity <= 1.0 else None
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def save_persistence(path: Union[str, Path]) -> None:
    """Atomically persist the last valid ratio, if one exists."""
    if _last_equity_ratio is None:
        return
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = state_path.with_suffix(state_path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps({"equity_ratio": _last_equity_ratio}, ensure_ascii=False),
        encoding="utf-8",
    )
    temp_path.replace(state_path)
