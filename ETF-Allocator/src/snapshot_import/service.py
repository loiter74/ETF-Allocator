"""OCR 文字结构化编排、严格归一和只读行情补齐。"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from config.settings import ASSETS
from .deepseek import DeepSeekError, DeepSeekSettings, DeepSeekStructurer
from .models import FieldCandidate, PositionDraft, SnapshotDraft, StructureResult, empty_field
from .parser import ASSET_ALIASES, parse_local


@dataclass(frozen=True)
class ImportLimits:
    max_files: int = 3
    max_file_bytes: int = 8 * 1024 * 1024
    max_total_bytes: int = 20 * 1024 * 1024
    max_segment_characters: int = 30_000
    max_total_characters: int = 60_000
    accepted_image_types: tuple[str, ...] = ("image/png", "image/jpeg", "image/webp")


def ocr_config(settings: DeepSeekSettings | None = None, limits: ImportLimits | None = None) -> dict[str, Any]:
    settings = settings or DeepSeekSettings.from_environment()
    limits = limits or ImportLimits()
    return {
        "deepseek_enabled": bool(settings.api_key),
        "structuring_provider": "deepseek" if settings.api_key else "local_parser",
        "model": settings.model if settings.api_key else None,
        "image_upload": False,
        "ocr_location": "browser",
        "accepted_image_types": list(limits.accepted_image_types),
        "max_files": limits.max_files,
        "max_file_bytes": limits.max_file_bytes,
        "max_total_bytes": limits.max_total_bytes,
        "max_segment_characters": limits.max_segment_characters,
        "max_total_characters": limits.max_total_characters,
        "privacy_notice": "原图仅在浏览器本地 OCR；服务端只接收识别文字，不保存草稿。",
    }


def _finite_non_negative(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _confidence(value: Any, fallback: float = 0.72) -> float:
    number = _finite_non_negative(value)
    return fallback if number is None else max(0.0, min(1.0, number))


def _normalize_asset(raw_asset: Any, raw_code: Any) -> tuple[str | None, str | None, bool]:
    asset_text = str(raw_asset or "").strip()
    code_text = str(raw_code or "").strip()
    compact = "".join(asset_text.split()).upper()
    for asset, aliases in ASSET_ALIASES.items():
        if code_text == str(ASSETS[asset]["code"]) or any(
            "".join(alias.split()).upper() in compact for alias in aliases
        ):
            return asset, str(ASSETS[asset]["code"]), asset != "国债ETF"
    if asset_text and (code_text or len(asset_text) >= 2):
        return asset_text[:80], code_text[:20] or None, True
    return None, None, True


def _model_to_draft(payload: dict[str, Any], fallback_date: str | None) -> tuple[SnapshotDraft, list[str]]:
    warnings: list[str] = []
    positions: list[PositionDraft] = []
    seen: set[tuple[str, str | None]] = set()
    raw_positions = payload.get("positions")
    if not isinstance(raw_positions, list):
        raise ValueError("positions 必须是数组")

    for raw in raw_positions[:100]:
        if not isinstance(raw, dict):
            continue
        asset, code, is_equity = _normalize_asset(raw.get("asset"), raw.get("code"))
        if not asset:
            continue
        identity = (asset, code)
        if identity in seen:
            warnings.append(f"{asset}出现重复识别行，已保留第一行")
            continue
        seen.add(identity)
        confidence = _confidence(raw.get("confidence"))
        evidence = str(raw.get("evidence") or "DeepSeek 结构化结果")[:240]

        def numeric(name: str) -> FieldCandidate:
            value = _finite_non_negative(raw.get(name))
            return FieldCandidate(value, confidence if value is not None else 0.0, "deepseek", evidence) if value is not None else empty_field()

        position_warnings: list[str] = []
        for key, label in (("shares", "份额"), ("price", "当前价格"), ("average_cost", "平均成本")):
            if _finite_non_negative(raw.get(key)) is None:
                position_warnings.append(f"{asset}未可靠识别{label}")
        positions.append(PositionDraft(
            asset=FieldCandidate(asset, confidence, "deepseek", evidence),
            code=FieldCandidate(code, confidence if code else 0.0, "deepseek", evidence),
            shares=numeric("shares"),
            price=numeric("price"),
            average_cost=numeric("average_cost"),
            market_value=numeric("market_value"),
            is_equity=is_equity,
            warnings=tuple(position_warnings),
        ))
        warnings.extend(position_warnings)

    raw_date = str(payload.get("snapshot_date") or "").strip()
    try:
        normalized_date = date.fromisoformat(raw_date).isoformat() if raw_date else fallback_date
    except ValueError:
        normalized_date = fallback_date
        warnings.append("模型识别的快照日期无效，已使用页面日期")
    snapshot_field = (
        FieldCandidate(normalized_date, 0.8 if raw_date else 1.0, "deepseek" if raw_date else "user", raw_date or "页面快照日期")
        if normalized_date else empty_field()
    )
    cash = _finite_non_negative(payload.get("account_cash"))
    return SnapshotDraft(
        snapshot_date=snapshot_field,
        account_cash=FieldCandidate(cash, 0.78, "deepseek", "账户可用资金") if cash is not None else empty_field(),
        positions=tuple(positions),
    ), warnings


def _enrich_prices(draft: SnapshotDraft, db_path: Path | None) -> tuple[SnapshotDraft, list[str]]:
    if db_path is None or not db_path.exists():
        return draft, []
    snapshot_date = draft.snapshot_date.value if isinstance(draft.snapshot_date.value, str) else date.today().isoformat()
    warnings: list[str] = []
    enriched: list[PositionDraft] = []
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return draft, []
    try:
        for position in draft.positions:
            if position.price.value is not None or not position.code.value:
                enriched.append(position)
                continue
            try:
                row = conn.execute(
                    """SELECT trade_date, close_adj FROM etf_price
                       WHERE code = ? AND trade_date <= ?
                       ORDER BY trade_date DESC LIMIT 1""",
                    (str(position.code.value), snapshot_date),
                ).fetchone()
            except sqlite3.Error:
                row = None
            if not row:
                enriched.append(position)
                continue
            price_date = str(row["trade_date"])
            price = float(row["close_adj"])
            price_field = FieldCandidate(
                price, 0.55, "market_data", "本地后复权参考价，请与券商现价核对", price_date,
            )
            market_value = position.market_value
            if market_value.value is None and position.shares.value is not None:
                market_value = FieldCandidate(
                    float(position.shares.value) * price, 0.5, "market_data",
                    "由识别份额 × 本地后复权参考价推导", price_date,
                )
            enriched.append(replace(position, price=price_field, market_value=market_value))
            warnings.append(f"{position.asset.value}现价来自{price_date}本地后复权数据，应用前必须核对券商现价")
    finally:
        conn.close()
    return replace(draft, positions=tuple(enriched)), warnings


def _cap_with_ocr_confidence(
    draft: SnapshotDraft,
    ocr_confidences: Iterable[float | None] | None,
) -> SnapshotDraft:
    values = [
        max(0.0, min(1.0, float(value) / 100.0))
        for value in (ocr_confidences or [])
        if value is not None
    ]
    if not values:
        return draft
    confidence_cap = min(values)

    def capped(field: FieldCandidate) -> FieldCandidate:
        if field.value is None or field.source not in {"local_parser", "deepseek"}:
            return field
        return replace(field, confidence=min(field.confidence, confidence_cap))

    return replace(
        draft,
        snapshot_date=capped(draft.snapshot_date),
        account_cash=capped(draft.account_cash),
        positions=tuple(
            replace(
                position,
                asset=capped(position.asset),
                code=capped(position.code),
                shares=capped(position.shares),
                price=capped(position.price),
                average_cost=capped(position.average_cost),
                market_value=capped(position.market_value),
            )
            for position in draft.positions
        ),
    )


def _validated_texts(texts: Iterable[str], limits: ImportLimits) -> list[str]:
    normalized = [str(text).strip() for text in texts if str(text).strip()]
    if not normalized:
        raise ValueError("OCR 文字不能为空")
    if len(normalized) > limits.max_files:
        raise ValueError(f"OCR 文字段最多 {limits.max_files} 段")
    if any(len(text) > limits.max_segment_characters for text in normalized):
        raise ValueError(f"单段 OCR 文字不能超过 {limits.max_segment_characters} 字符")
    if sum(map(len, normalized)) > limits.max_total_characters:
        raise ValueError(f"OCR 文字合计不能超过 {limits.max_total_characters} 字符")
    return normalized


def structure_ocr_texts(
    texts: Iterable[str],
    snapshot_date: str | None,
    *,
    db_path: Path | None = None,
    structurer: DeepSeekStructurer | None = None,
    limits: ImportLimits | None = None,
    ocr_confidences: Iterable[float | None] | None = None,
) -> StructureResult:
    limits = limits or ImportLimits()
    normalized = _validated_texts(texts, limits)
    structurer = structurer or DeepSeekStructurer()
    warnings: list[str] = []
    provider = "local_parser"
    model: str | None = None

    if structurer.enabled:
        try:
            payload = structurer.structure(normalized, snapshot_date)
            draft, model_warnings = _model_to_draft(payload, snapshot_date)
            warnings.extend(model_warnings)
            provider = "deepseek"
            model = structurer.settings.model
        except (DeepSeekError, ValueError) as exc:
            draft, local_warnings = parse_local(normalized, snapshot_date)
            warnings.append(f"DeepSeek 增强解析不可用，已安全回退本地解析：{exc}")
            warnings.extend(local_warnings)
    else:
        draft, local_warnings = parse_local(normalized, snapshot_date)
        warnings.append("未配置 DeepSeek API Key，当前使用本地规则解析。")
        warnings.extend(local_warnings)

    draft = _cap_with_ocr_confidence(draft, ocr_confidences)
    draft, price_warnings = _enrich_prices(draft, db_path)
    warnings.extend(price_warnings)
    return StructureResult(
        draft=draft,
        provider=provider,
        model=model,
        warnings=tuple(dict.fromkeys(warnings)),
        input_characters=sum(map(len, normalized)),
    )
