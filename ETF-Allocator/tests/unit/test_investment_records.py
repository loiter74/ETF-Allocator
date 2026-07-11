import sqlite3
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from src.api import server


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    database_path = tmp_path / "investments.db"
    monkeypatch.setattr(server, "DB_PATH", database_path)
    yield database_path


def make_params(day: date, amount: str, note: str = ""):
    return server.InvestmentRecordParams(
        investment_date=day,
        amount=amount,
        note=note,
    )


def make_detailed_params(day: date, note: str = "", **overrides):
    allocations = {
        "白酒ETF": "0",
        "银行ETF": "0",
        "红利ETF": "0",
        "沪深300ETF": "0",
        "科创50ETF": "0",
        "国债ETF": "0",
    }
    allocations.update(overrides)
    return server.InvestmentRecordParams(
        investment_date=day,
        allocations=allocations,
        note=note,
    )


def test_empty_investment_summary():
    payload = server.get_investments()

    assert payload["records"] == []
    assert payload["summary"] == {
        "count": 0,
        "total_amount": 0.0,
        "last_date": None,
        "last_amount": None,
    }


def test_create_list_and_summarize_investments():
    older = date.today() - timedelta(days=31)
    newer = date.today() - timedelta(days=1)

    first = server.create_investment(make_params(older, "8000.50", " 六月投入 "))
    second = server.create_investment(make_params(newer, "12000", "七月投入"))
    payload = server.get_investments()

    assert first["amount"] == 8000.5
    assert first["allocations"] == {}
    assert first["note"] == "六月投入"
    assert payload["records"] == [second, first]
    assert payload["summary"] == {
        "count": 2,
        "total_amount": 20000.5,
        "last_date": newer.isoformat(),
        "last_amount": 12000.0,
    }


def test_detailed_investment_derives_total_and_persists_all_assets():
    params = make_detailed_params(
        date.today(),
        "分项投入",
        白酒ETF="1000.25",
        银行ETF="2000",
        国债ETF="3000.75",
    )

    created = server.create_investment(params)
    persisted = server.get_investments()["records"][0]

    assert created["amount"] == 6001.0
    assert persisted == created
    assert persisted["allocations"] == {
        "白酒ETF": 1000.25,
        "银行ETF": 2000.0,
        "红利ETF": 0.0,
        "沪深300ETF": 0.0,
        "科创50ETF": 0.0,
        "国债ETF": 3000.75,
    }


@pytest.mark.parametrize(
    ("allocations", "detail"),
    [
        ({"未知基金": "100"}, "不支持的资产"),
        ({"白酒ETF": "-1"}, "不能为负数"),
        ({"白酒ETF": "0"}, "必须大于 0"),
    ],
)
def test_invalid_investment_details_are_rejected(allocations, detail):
    params = server.InvestmentRecordParams(
        investment_date=date.today(),
        allocations=allocations,
    )

    with pytest.raises(HTTPException) as exc_info:
        server.create_investment(params)

    assert exc_info.value.status_code == 422
    assert detail in exc_info.value.detail


def test_duplicate_investment_returns_conflict():
    params = make_params(date.today(), "8000", "本月投入")
    server.create_investment(params)

    with pytest.raises(HTTPException) as exc_info:
        server.create_investment(params)

    assert exc_info.value.status_code == 409
    assert server.get_investments()["summary"]["count"] == 1


def test_future_date_is_rejected():
    with pytest.raises(HTTPException) as exc_info:
        server.create_investment(
            make_params(date.today() + timedelta(days=1), "8000")
        )

    assert exc_info.value.status_code == 422


def test_delete_investment_updates_summary_and_cascades_details(isolated_database):
    created = server.create_investment(
        make_detailed_params(date.today(), 白酒ETF="5000", 国债ETF="3000")
    )

    response = server.delete_investment(created["id"])

    assert response.status_code == 204
    assert server.get_investments()["summary"]["count"] == 0
    with sqlite3.connect(isolated_database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM investment_record_item").fetchone()[0] == 0
    with pytest.raises(HTTPException) as exc_info:
        server.delete_investment(created["id"])
    assert exc_info.value.status_code == 404
