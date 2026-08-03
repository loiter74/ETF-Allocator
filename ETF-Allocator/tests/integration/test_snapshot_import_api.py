import sqlite3

from src.api import server
from src.store.schema import create_tables


def _params(text: str):
    return server.OcrTextStructureParams(
        snapshot_date="2026-08-02",
        ocr_texts=[{"name": "broker.png", "text": text, "ocr_confidence": 88}],
    )


def test_parse_text_endpoint_is_read_only_and_returns_review_draft(tmp_path, monkeypatch):
    db_path = tmp_path / "readonly-import.db"
    conn = sqlite3.connect(db_path)
    create_tables(conn)
    conn.commit()
    conn.close()
    monkeypatch.setattr(server, "DB_PATH", db_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")

    result = server.parse_portfolio_snapshot_text(_params(
        "可用资金：2272\n科创50ETF 588000\n持仓份额：600\n现价：1.04\n平均成本：0.8"
    ))

    assert result["read_only"] is True
    assert result["image_uploaded"] is False
    assert result["provider"] == "local_parser"
    assert result["draft"]["account_cash"]["value"] == 2272
    assert result["draft"]["positions"][0]["shares"]["value"] == 600

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT count(*) FROM portfolio_snapshot").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM strategy_state").fetchone()[0] == 0
    conn.close()


def test_parse_text_endpoint_rejects_empty_text(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    params = server.OcrTextStructureParams(ocr_texts=[{"name": "empty", "text": ""}])

    try:
        server.parse_portfolio_snapshot_text(params)
        raise AssertionError("expected HTTPException")
    except server.HTTPException as exc:
        assert exc.status_code == 422
        assert "不能为空" in exc.detail


def test_ocr_config_endpoint_never_exposes_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-for-browser")
    config = server.get_portfolio_snapshot_ocr_config()

    assert config["deepseek_enabled"] is True
    assert config["ocr_location"] == "browser"
    assert "key" not in " ".join(config.keys()).lower()
    assert "not-for-browser" not in str(config)
