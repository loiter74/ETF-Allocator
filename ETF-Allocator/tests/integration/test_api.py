"""
tests/integration/test_api.py — API 集成测试。

测试前需确保后端已启动: uvicorn src.api.server:app --port 8000
运行: pytest tests/integration/test_api.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest, requests, json, subprocess, time
from pathlib import Path

BASE_URL = "http://localhost:8000"
ROOT = Path(__file__).resolve().parent.parent.parent


def _api_alive():
    try:
        r = requests.get(f"{BASE_URL}/api/report", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.integration
class TestAPIEndpoints:
    """API 三个端点的基础功能测试。"""

    @pytest.fixture(autouse=True)
    def check_server(self):
        if not _api_alive():
            pytest.skip("Backend API not running on port 8000")

    def test_get_report_returns_200(self):
        r = requests.get(f"{BASE_URL}/api/report", timeout=10)
        assert r.status_code == 200

    def test_get_report_has_correct_schema(self):
        r = requests.get(f"{BASE_URL}/api/report", timeout=10)
        d = r.json()

        # 顶层字段
        for key in ["date", "market_temp", "portfolio_risk", "allocations"]:
            assert key in d, f"missing top-level key: {key}"

        # 温度计字段
        mt = d["market_temp"]
        for key in ["hs300_pe_percentile", "all_a_pb_percentile", "equity_ratio", "bond_ratio", "status"]:
            assert key in mt, f"missing market_temp key: {key}"

        # 组合风险字段
        pr = d["portfolio_risk"]
        for key in ["value_group_weight", "value_group_cap", "growth_group_weight", "growth_group_cap", "next_rebalance_date"]:
            assert key in pr, f"missing portfolio_risk key: {key}"

        # 分配列表
        assert len(d["allocations"]) == 6, f"expected 6 allocations, got {len(d['allocations'])}"
        a0 = d["allocations"][0]
        for key in ["asset", "amount", "current_weight", "upper_limit", "opportunity_score", "trigger_reason"]:
            assert key in a0, f"allocations[0] missing: {key}"

    def test_get_report_equity_bond_sum_to_1(self):
        r = requests.get(f"{BASE_URL}/api/report", timeout=10)
        mt = r.json()["market_temp"]
        total = mt["equity_ratio"] + mt["bond_ratio"]
        assert abs(total - 1.0) < 0.01, f"equity + bond should be 1.0, got {total}"

    def test_get_report_group_caps_correct(self):
        r = requests.get(f"{BASE_URL}/api/report", timeout=10)
        pr = r.json()["portfolio_risk"]
        assert pr["value_group_cap"] == 0.60
        assert pr["growth_group_cap"] == 0.15

    def test_post_report_simulate_returns_200(self):
        payload = {
            "date": "2026-06-01", "new_money": 10000, "total_assets": 200000,
            "current_weights": {
                "白酒ETF": 0.12, "银行ETF": 0.22, "红利ETF": 0.15,
                "沪深300ETF": 0.18, "科创50ETF": 0.10, "国债ETF": 0.23,
            },
        }
        r = requests.post(f"{BASE_URL}/api/report", json=payload, timeout=10)
        assert r.status_code == 200

    def test_post_report_has_before_after_weights(self):
        payload = {
            "date": "2026-06-01", "new_money": 10000, "total_assets": 200000,
            "current_weights": {
                "白酒ETF": 0.12, "银行ETF": 0.22, "红利ETF": 0.15,
                "沪深300ETF": 0.18, "科创50ETF": 0.10, "国债ETF": 0.23,
            },
        }
        r = requests.post(f"{BASE_URL}/api/report", json=payload, timeout=10)
        d = r.json()
        assert "before_weights" in d
        assert "after_weights" in d
        # 权重和应为 1.0
        bw = sum(d["before_weights"].values())
        aw = sum(d["after_weights"].values())
        assert abs(bw - 1.0) < 0.01, f"before_weights sum: {bw}"
        assert abs(aw - 1.0) < 0.01, f"after_weights sum: {aw}"

    def test_post_report_total_changes(self):
        """模拟后总资产应增加 new_money。"""
        payload = {
            "date": "2026-06-01", "new_money": 10000, "total_assets": 200000,
            "current_weights": {
                "白酒ETF": 0.12, "银行ETF": 0.22, "红利ETF": 0.15,
                "沪深300ETF": 0.18, "科创50ETF": 0.10, "国债ETF": 0.23,
            },
        }
        r = requests.post(f"{BASE_URL}/api/report", json=payload, timeout=10)
        d = r.json()
        assert d["new_total"] == pytest.approx(210000, rel=0.01)

    def test_get_history_returns_data(self):
        r = requests.get(f"{BASE_URL}/api/history?index=000300&field=pe&years=5", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["available"] is True
        assert len(d["data"]) > 0
        # 验证格式
        p0 = d["data"][0]
        assert "date" in p0
        assert "value" in p0
        assert "percentile" in p0

    def test_get_history_unsupported_field(self):
        r = requests.get(f"{BASE_URL}/api/history?index=000300&field=dividend_yield", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["available"] is False

    def test_report_status_is_known_key(self):
        """
        Bug2 防护：验证 /api/report 返回的 market_temp.status 
        必须是前端 lookup table 中存在的值。
        有效值: cool, mild_cool, strong_cool, overheat, frozen
        """
        r = requests.get(f"{BASE_URL}/api/report", timeout=10)
        d = r.json()
        status = d["market_temp"]["status"]
        valid = {"cool", "mild_cool", "strong_cool", "overheat", "frozen"}
        assert status in valid, (
            f"status '{status}' not in known values {valid}. "
            "前端 StatusLabels lookup 会返回 undefined — 标签将回退为原始字符串，不可读。"
        )


@pytest.mark.integration
class TestDashboardBuild:
    """前端构建测试。"""

    def test_typescript_no_errors(self):
        dashboard_dir = ROOT / "dashboard"
        if not (dashboard_dir / "node_modules").exists():
            pytest.skip("node_modules not installed")
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(dashboard_dir), capture_output=True, text=True, timeout=60,
            shell=True,
        )
        assert result.returncode == 0, f"tsc errors:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"

    def test_vite_build_succeeds(self):
        dashboard_dir = ROOT / "dashboard"
        if not (dashboard_dir / "node_modules").exists():
            pytest.skip("node_modules not installed")
        result = subprocess.run(
            ["npx", "vite", "build"],
            cwd=str(dashboard_dir), capture_output=True, text=True, timeout=60,
            shell=True,
        )
        assert result.returncode == 0, f"vite build failed:\n{result.stderr[-500:]}"
