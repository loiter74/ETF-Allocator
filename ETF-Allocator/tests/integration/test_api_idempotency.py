from src.api import server


def test_get_report_does_not_create_or_change_bond_state(tmp_path, monkeypatch):
    state_path = tmp_path / "bond_accumulator.json"
    monkeypatch.setattr(server, "BOND_ACCUMULATOR_PATH", state_path)

    first = server.get_report(date_str="2026-06-01", total_assets=0)
    second = server.get_report(date_str="2026-06-01", total_assets=0)

    # v1.3 退役：GET report 不再触碰 BondAccumulator，也不返回 bond_status
    assert not state_path.exists()
    assert "bond_status" not in first
    assert "allocations" not in first
    # 市场状态应幂等
    assert first["market_temp"] == second["market_temp"]
    assert first["assets"] == second["assets"]
