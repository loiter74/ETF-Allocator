"""确定性 OCR 文字解析器。

只在标签或可识别表头提供数字语义时提取，避免把券商页面上的涨跌额、盈亏等
无关数字按位置猜成份额或成本。
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Iterable

from config.settings import ASSETS
from .models import FieldCandidate, PositionDraft, SnapshotDraft, empty_field


ASSET_ALIASES: dict[str, tuple[str, ...]] = {
    "白酒ETF": ("白酒ETF", "白酒LOF", "白酒基金LOF", "中证白酒", "招商中证白酒", "161725"),
    "银行ETF": ("银行ETF", "中证银行", "华宝中证银行", "512800"),
    "红利ETF": ("红利ETF", "中证红利", "招商中证红利", "515080"),
    "沪深300ETF": ("沪深300ETF", "300ETF", "华泰柏瑞沪深300", "510300"),
    "科创50ETF": ("科创50ETF", "科创ETF", "华夏上证科创板50", "588000"),
    "国债ETF": ("国债ETF", "上证5年期国债", "511010"),
}
NON_MANAGED_ALIASES: dict[str, tuple[str, ...]] = {
    "航民股份": ("航民股份",),
    "机器人ETF": ("机器人ETF", "机器人ETF华夏"),
}
ALL_ASSET_ALIASES = {**ASSET_ALIASES, **NON_MANAGED_ALIASES}

NUMBER = r"([-+]?\d[\d,]*(?:\.\d+)?)"
FIELD_PATTERNS: dict[str, tuple[str, ...]] = {
    "shares": (r"(?:持仓|可用)?份额\s*[:：]?\s*" + NUMBER, r"持仓数量\s*[:：]?\s*" + NUMBER),
    "price": (r"(?:现价|当前价|最新价|市价)\s*[:：]?\s*" + NUMBER,),
    "average_cost": (r"(?:平均成本|持仓成本|成本价|成本)\s*[:：]?\s*" + NUMBER,),
    "market_value": (r"(?:持仓市值|参考市值|市值)\s*[:：]?\s*" + NUMBER,),
}
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "shares": ("持仓", "份额", "数量"),
    "price": ("现价", "当前价", "最新价", "市价"),
    "average_cost": ("成本价", "平均成本", "成本"),
    "market_value": ("持仓市值", "参考市值", "市值"),
}


def _clean_number(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _line_candidate(value: float | None, evidence: str, confidence: float = 0.86) -> FieldCandidate:
    if value is None:
        return empty_field()
    return FieldCandidate(value, confidence, "local_parser", evidence.strip()[:240])


def _find_tagged(block: str, field_name: str) -> FieldCandidate:
    for pattern in FIELD_PATTERNS[field_name]:
        match = re.search(pattern, block, flags=re.IGNORECASE)
        if match:
            value = _clean_number(match.group(1))
            if value is not None:
                evidence = match.group(0)
                return _line_candidate(value, evidence)
    return empty_field()


def _header_mapping(header: str) -> list[str]:
    located: list[tuple[int, str]] = []
    for field_name, aliases in HEADER_ALIASES.items():
        positions = [header.find(alias) for alias in aliases if alias in header]
        if positions:
            located.append((min(positions), field_name))
    return [field_name for _, field_name in sorted(located)]


def _strip_asset_identity(line: str, asset: str, code: str | None) -> str:
    if code and code in line:
        # 常见券商表格的数值列均位于证券代码之后；直接截断可避免“科创50”中的 50 被误认成份额。
        return line.split(code, 1)[1]
    scrubbed = line
    for alias in sorted(ALL_ASSET_ALIASES[asset], key=len, reverse=True):
        spaced_pattern = r"\s*".join(re.escape(char) for char in alias)
        scrubbed, count = re.subn(spaced_pattern, " ", scrubbed, count=1, flags=re.IGNORECASE)
        if count:
            break
    return scrubbed


def _signed_numbers(line: str) -> list[float]:
    values: list[float] = []
    for raw in re.findall(NUMBER, line):
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def _numbers_without_code(line: str, code: str | None, asset: str) -> list[float]:
    return [value for value in _signed_numbers(_strip_asset_identity(line, asset, code)) if value >= 0]


def _asset_for_line(line: str) -> str | None:
    compact = re.sub(r"\s+", "", line).upper()
    for asset, aliases in ALL_ASSET_ALIASES.items():
        if any(re.sub(r"\s+", "", alias).upper() in compact for alias in aliases):
            return asset
    return None


def _paired_broker_fields(
    block_lines: list[str],
    header: str,
    asset: str,
    code: str | None,
) -> tuple[dict[str, FieldCandidate], list[str]] | None:
    """解析中信建投等“字段名A/B + 每个持仓两行数值”的持仓表。"""
    compact_header = re.sub(r"\s+", "", header)
    if not all(token in compact_header for token in ("市值", "盈亏", "持仓/可用", "成本/现价")):
        return None
    if len(block_lines) < 2:
        return None
    first = _signed_numbers(_strip_asset_identity(block_lines[0], asset, code))
    second = _signed_numbers(block_lines[1])
    if len(first) < 3 or len(second) < 3:
        return None

    shares_value = abs(first[-2])
    cost_value = abs(first[-1])
    market_value = abs(second[0])
    price_value = abs(second[-1])
    evidence = f"{block_lines[0]} | {block_lines[1]}"
    confidence = 0.83
    mismatch_warning: list[str] = []
    expected_value = shares_value * price_value
    relative_error = abs(market_value - expected_value) / max(market_value, expected_value, 1.0)
    price_confidence = confidence
    market_confidence = confidence
    if relative_error > 0.08:
        price_confidence = 0.45
        market_confidence = 0.45
        mismatch_warning.append(
            f"{asset}识别市值与份额×现价相差{relative_error:.0%}，疑似 OCR 漏位，必须人工核对"
        )
    return {
        "shares": _line_candidate(shares_value, evidence, confidence),
        "price": _line_candidate(price_value, evidence, price_confidence),
        "average_cost": _line_candidate(cost_value, evidence, confidence),
        "market_value": _line_candidate(market_value, evidence, market_confidence),
    }, mismatch_warning


def _normalize_ocr_line(line: str) -> str:
    """合并中文字符间的 OCR 假空格，同时保留列之间的数字边界。"""
    normalized = line.strip()
    while True:
        compacted = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", normalized)
        if compacted == normalized:
            break
        normalized = compacted
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_date(text: str, fallback: str | None) -> FieldCandidate:
    for pattern in (
        r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?",
        r"(?:日期|时间)\s*[:：]?\s*(20\d{2})(\d{2})(\d{2})",
    ):
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            parsed = date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
        except ValueError:
            continue
        return FieldCandidate(parsed, 0.88, "local_parser", match.group(0))
    if fallback:
        return FieldCandidate(fallback, 1.0, "user", "页面快照日期")
    return empty_field()


def _extract_cash(text: str, lines: list[str]) -> FieldCandidate:
    patterns = (
        r"(?:可用资金|可用金额|可取金额|资金余额|账户现金|现金余额)\s*[:：]?\s*" + NUMBER,
        r"(?:可用|余额)\s*[:：]\s*[¥￥]?\s*" + NUMBER,
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _clean_number(match.group(1))
            if value is not None:
                return _line_candidate(value, match.group(0), 0.9)
    for index, line in enumerate(lines):
        compact = re.sub(r"\s+", "", line)
        if not all(token in compact for token in ("买入", "卖出", "持仓", "查询")):
            continue
        for summary_line in lines[index + 1:min(len(lines), index + 4)]:
            values = [value for value in _signed_numbers(summary_line) if value >= 0]
            if len(values) == 3:
                return _line_candidate(
                    values[1], summary_line, 0.55,
                )
    return empty_field()


def parse_local(texts: Iterable[str], snapshot_date: str | None = None) -> tuple[SnapshotDraft, list[str]]:
    text = "\n".join(part.strip() for part in texts if part.strip())
    lines = [_normalize_ocr_line(line) for line in text.splitlines() if line.strip()]
    normalized_text = "\n".join(lines)
    warnings: list[str] = []
    positions: list[PositionDraft] = []
    seen: set[str] = set()

    for index, line in enumerate(lines):
        asset = _asset_for_line(line)
        if not asset or asset in seen:
            continue
        seen.add(asset)
        code = str(ASSETS[asset]["code"]) if asset in ASSETS else None
        block_lines = [line]
        for following in lines[index + 1:min(len(lines), index + 7)]:
            if _asset_for_line(following):
                break
            block_lines.append(following)
        block = "\n".join(block_lines)
        fields = {name: _find_tagged(block, name) for name in FIELD_PATTERNS}
        position_warnings: list[str] = []

        header = " ".join(lines[:index])
        paired = _paired_broker_fields(block_lines, header, asset, code)
        if paired is not None:
            fields, paired_warnings = paired
            position_warnings.extend(paired_warnings)

        if all(candidate.value is None for candidate in fields.values()):
            header = " ".join(lines[max(0, index - 3):index])
            mapping = _header_mapping(header)
            values = _numbers_without_code(line, code, asset)
            if mapping and len(values) >= len(mapping):
                fields.update({
                    field_name: _line_candidate(value, f"{header} | {line}", 0.82)
                    for field_name, value in zip(mapping, values)
                })

        shares = fields["shares"]
        price = fields["price"]
        market_value = fields["market_value"]
        if market_value.value is None and shares.value is not None and price.value is not None:
            derived = float(shares.value) * float(price.value)
            market_value = FieldCandidate(
                derived, min(shares.confidence, price.confidence) - 0.05,
                "local_parser", "由份额 × 当前价格推导",
            )
        if price.value is None and market_value.value is not None and shares.value not in (None, 0):
            derived = float(market_value.value) / float(shares.value)
            price = FieldCandidate(
                derived, min(market_value.confidence, shares.confidence) - 0.12,
                "local_parser", "由市值 ÷ 份额推导，请核对",
            )
        for field_name, label in (
            ("shares", "份额"), ("price", "当前价格"), ("average_cost", "平均成本"),
        ):
            candidate = {"shares": shares, "price": price, "average_cost": fields["average_cost"]}[field_name]
            if candidate.value is None:
                position_warnings.append(f"{asset}未可靠识别{label}")

        positions.append(PositionDraft(
            asset=FieldCandidate(asset, 0.98, "local_parser", line),
            code=FieldCandidate(code, 0.98, "local_parser", line) if code else empty_field(),
            shares=shares,
            price=price,
            average_cost=fields["average_cost"],
            market_value=market_value,
            is_equity=asset != "国债ETF",
            warnings=tuple(position_warnings),
        ))

    if not positions:
        warnings.append("没有识别出受管资产，请检查截图清晰度或直接粘贴 OCR 文字。")
    warnings.extend(warning for position in positions for warning in position.warnings)
    return SnapshotDraft(
        snapshot_date=_extract_date(normalized_text, snapshot_date),
        account_cash=_extract_cash(normalized_text, lines),
        positions=tuple(positions),
    ), warnings
