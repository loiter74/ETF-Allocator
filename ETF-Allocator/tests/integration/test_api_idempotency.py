from src.api import server


def test_get_report_does_not_create_or_change_bond_state(tmp_path, monkeypatch):
    state_path = tmp_path / "bond_accumulator.json"
    monkeypatch.setattr(server, "BOND_ACCUMULATOR_PATH", state_path)

    first = server.get_report(date_str="2026-06-01", total_assets=0)
    second = server.get_report(date_str="2026-06-01", total_assets=0)

    assert not state_path.exists()
    assert first["bond_status"] == second["bond_status"]
    assert first["allocations"] == second["allocations"]
