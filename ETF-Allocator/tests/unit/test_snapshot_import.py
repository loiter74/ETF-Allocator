import json
import sqlite3

import httpx
import pytest

from src.snapshot_import.deepseek import DeepSeekSettings, DeepSeekStructurer
from src.snapshot_import.parser import parse_local
from src.snapshot_import.service import ImportLimits, ocr_config, structure_ocr_texts
from src.store.schema import create_tables, insert_etf_price


OCR_TABLE = """2026-08-02
可用资金：2,272.50
证券名称 证券代码 持仓份额 当前价 成本价 持仓市值
科创50ETF 588000 600 1.040 0.800 624.00
银行ETF 512800 1000 1.086 1.020 1086.00
"""


def test_local_parser_uses_labels_and_headers_without_guessing():
    draft, warnings = parse_local([OCR_TABLE], "2026-08-02")
    payload = draft.to_dict()

    assert payload["snapshot_date"]["value"] == "2026-08-02"
    assert payload["account_cash"]["value"] == 2272.50
    k50 = next(item for item in payload["positions"] if item["asset"]["value"] == "科创50ETF")
    assert k50["shares"]["value"] == 600
    assert k50["price"]["value"] == 1.04
    assert k50["average_cost"]["value"] == 0.8
    assert k50["market_value"]["value"] == 624
    assert not warnings


def test_local_parser_leaves_ambiguous_numbers_empty():
    draft, warnings = parse_local(["科创50ETF 588000 盈亏 240.5 涨幅 3.2%"], "2026-08-02")
    position = draft.positions[0]

    assert position.shares.value is None
    assert position.price.value is None
    assert position.average_cost.value is None
    assert any("未可靠识别份额" in warning for warning in warnings)


def test_local_parser_tolerates_real_tesseract_chinese_spacing():
    text = """2026-08-02
可 用 资金 : 4567.89
证 券 名 称 证 券 代 码 持仓 份额 当前 价 成 本 价 持仓 市 值
科 创 50ETF 588000 900 1.200 0.950 1080.00
银行 ETF 512800 1300 1.100 1.020 1430.00
"""
    draft, warnings = parse_local([text], "2026-08-02")
    positions = {position.asset.value: position for position in draft.positions}

    assert draft.account_cash.value == 4567.89
    assert positions["科创50ETF"].shares.value == 900
    assert positions["科创50ETF"].price.value == 1.2
    assert positions["科创50ETF"].average_cost.value == 0.95
    assert positions["银行ETF"].market_value.value == 1430
    assert not warnings


def test_local_parser_handles_real_two_line_broker_rows_and_flags_ocr_mismatch():
    text = """买 入 卖 出 撤 单 持仓 查询
25,109.20 2,272.38 271.84
持仓 股
市 值 盈亏 人 持仓 /可 用 *? 成 本 /现价
国债 ETF 国 泰 20.42 100 140.700
14,097.00 0.1889%p 100 140.970
中 证 红利 ETF 招 商 232.70 3000 1.499
4731.00 5.203% 3000 1.577
科 创 50ETF 广 发 -42.20 0600 1.110
624.00 -0.306% 600 1.040
银行 ETF 华 宝 69.10 1300 0.783
1,086.80 0.7069% 1300 0.830
白酒 基金 LOF 313.20 6200 0.532
3,614.60 9.586% 0200 0.583
航 民 股份 -5.01 100 0.740
6069.00 -0.742% 100 0.690
机 器 人 ETF 华 夏 12.70 300 0.914
286.80 4.5959p 300 0.950
"""
    draft, warnings = parse_local([text], "2026-08-02")
    positions = {position.asset.value: position for position in draft.positions}

    assert draft.account_cash.value == 2272.38
    assert draft.account_cash.confidence < 0.75
    assert positions["国债ETF"].shares.value == 100
    assert positions["国债ETF"].price.value == 140.97
    assert positions["红利ETF"].market_value.value == 4731
    assert positions["科创50ETF"].average_cost.value == 1.11
    assert positions["科创50ETF"].price.value == 1.04
    assert positions["银行ETF"].shares.value == 1300
    assert positions["白酒ETF"].shares.value == 6200
    assert positions["机器人ETF"].market_value.value == 286.8
    assert positions["航民股份"].market_value.confidence < 0.75
    assert any("航民股份识别市值与份额×现价" in warning for warning in warnings)


class _Response:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.responses.pop(0))


def test_deepseek_retries_empty_json_response_and_never_sends_an_image():
    client = _Client([
        "",
        json.dumps({
            "snapshot_date": "2026-08-02",
            "account_cash": 100,
            "positions": [],
        }),
    ])
    settings = DeepSeekSettings("secret", "https://api.deepseek.com", "deepseek-v4-flash", 5)
    result = DeepSeekStructurer(settings, client).structure(["OCR文字"], "2026-08-02")

    assert result["account_cash"] == 100
    assert len(client.calls) == 2
    body = client.calls[0][1]["json"]
    assert body["response_format"] == {"type": "json_object"}
    assert "data:image" not in json.dumps(body)


class _BrokenStructurer:
    enabled = True
    settings = DeepSeekSettings("secret", "https://api.deepseek.com", "test-model", 5)

    def structure(self, texts, snapshot_date):
        return {"positions": "not-an-array"}


def test_invalid_model_payload_falls_back_to_local_parser():
    result = structure_ocr_texts(
        [OCR_TABLE],
        "2026-08-02",
        structurer=_BrokenStructurer(),
    )

    assert result.provider == "local_parser"
    assert any("安全回退" in warning for warning in result.warnings)
    assert any(position.asset.value == "科创50ETF" for position in result.draft.positions)


class _NoKeyStructurer:
    enabled = False
    settings = DeepSeekSettings("", "https://api.deepseek.com", "deepseek-v4-flash", 5)


def test_market_data_only_fills_missing_price_and_is_low_confidence(tmp_path):
    db_path = tmp_path / "prices.db"
    conn = sqlite3.connect(db_path)
    create_tables(conn)
    insert_etf_price(conn, "588000", "2026-08-01", 1.234, 1000)
    conn.commit()
    conn.close()

    result = structure_ocr_texts(
        ["科创50ETF 588000\n持仓份额：600\n平均成本：0.8"],
        "2026-08-02",
        db_path=db_path,
        structurer=_NoKeyStructurer(),
    )
    position = result.draft.positions[0]

    assert position.price.value == 1.234
    assert position.price.source == "market_data"
    assert position.price.confidence < 0.75
    assert position.average_cost.value == 0.8
    assert any("必须核对券商现价" in warning for warning in result.warnings)


@pytest.mark.parametrize("texts", [[], [""], ["a" * 11]])
def test_input_limits_are_enforced_before_provider_call(texts):
    limits = ImportLimits(max_segment_characters=10, max_total_characters=10)
    with pytest.raises(ValueError):
        structure_ocr_texts(texts, None, structurer=_NoKeyStructurer(), limits=limits)


def test_config_does_not_expose_api_key():
    config = ocr_config(DeepSeekSettings("super-secret", "https://api.deepseek.com", "model-x", 5))

    assert config["deepseek_enabled"] is True
    assert config["image_upload"] is False
    assert "api_key" not in config
    assert "super-secret" not in json.dumps(config)


def test_browser_ocr_confidence_caps_structured_field_confidence():
    result = structure_ocr_texts(
        [OCR_TABLE],
        "2026-08-02",
        structurer=_NoKeyStructurer(),
        ocr_confidences=[73],
    )
    k50 = next(position for position in result.draft.positions if position.asset.value == "科创50ETF")

    assert k50.shares.confidence == 0.73
    assert k50.price.confidence == 0.73
