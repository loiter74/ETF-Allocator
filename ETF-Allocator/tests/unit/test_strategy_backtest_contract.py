import sqlite3

from src.api import server
from src.backtest import engine
from src.strategy import planner


def test_cli_api_and_backtest_import_the_same_decision_function():
    import run

    assert server.build_trade_plan is planner.build_trade_plan
    assert engine.build_trade_plan is planner.build_trade_plan
    assert run.build_trade_plan is planner.build_trade_plan


def test_sensitivity_grid_is_report_only_and_never_selects_winner(monkeypatch):
    fake = {
        "metrics": {
            "annualized_return": 0.05,
            "max_drawdown": -0.10,
            "calmar": 0.5,
            "sharpe": 0.4,
        },
        "execution": {
            "total_costs": 10,
            "sell_count": 1,
            "kechuang_independent_triggers": 1,
        },
    }
    monkeypatch.setattr(engine, "run_trade_backtest", lambda *args, **kwargs: fake)
    conn = sqlite3.connect(":memory:")
    report = engine.run_sensitivity_analysis(conn)
    assert len(report["results"]) == 81
    assert report["selection_performed"] is False
    assert report["locked_choice"] == {
        "activation": 0.25,
        "drawdown": 0.12,
        "off_months": 2,
        "sell_fraction": 1.0 / 3.0,
    }
    conn.close()
