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

        # 顶层字段（v1.3 退役：assets 替代 allocations）
        for key in ["date", "market_temp", "portfolio_risk", "assets"]:
            assert key in d, f"missing top-level key: {key}"
        for removed in ["allocations", "bond_status", "allocation_summary"]:
            assert removed not in d, f"GET report should not return decision field {removed}"

        # 温度计字段
        mt = d["market_temp"]
        for key in ["hs300_pe_percentile", "all_a_pb_percentile", "equity_ratio", "bond_ratio", "status"]:
            assert key in mt, f"missing market_temp key: {key}"

        # 组合风险字段
        pr = d["portfolio_risk"]
        for key in ["value_group_weight", "value_group_cap", "growth_group_weight", "growth_group_cap", "next_rebalance_date"]:
            assert key in pr, f"missing portfolio_risk key: {key}"

        # 资产列表（含因子详情，不再有 amount）
        assert len(d["assets"]) == 6, f"expected 6 assets, got {len(d['assets'])}"
        a0 = d["assets"][0]
        for key in ["name", "code", "score", "weight_current", "weight_upper", "trigger_reason"]:
            assert key in a0, f"assets[0] missing: {key}"

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
        # v1.3 退役：POST report 委托 GET，不再返回 before/after_weights
        # 改为验证 POST 返回与 GET 相同的市场状态结构
        payload = {
            "date": "2026-06-01", "new_money": 10000, "total_assets": 200000,
            "current_weights": {
                "白酒ETF": 0.12, "银行ETF": 0.22, "红利ETF": 0.15,
                "沪深300ETF": 0.18, "科创50ETF": 0.10, "国债ETF": 0.23,
            },
        }
        r = requests.post(f"{BASE_URL}/api/report", json=payload, timeout=10)
        d = r.json()
        assert "market_temp" in d
        assert "assets" in d
        # 不应返回决策字段
        assert "before_weights" not in d
        assert "allocations" not in d

    def test_post_report_total_changes(self):
        """v1.3 退役：POST 委托 GET，不再返回 new_total。验证市场状态可用即可。"""
        payload = {
            "date": "2026-06-01", "new_money": 10000, "total_assets": 200000,
            "current_weights": {
                "白酒ETF": 0.12, "银行ETF": 0.22, "红利ETF": 0.15,
                "沪深300ETF": 0.18, "科创50ETF": 0.10, "国债ETF": 0.23,
            },
        }
        r = requests.post(f"{BASE_URL}/api/report", json=payload, timeout=10)
        d = r.json()
        assert "new_total" not in d  # v1.3 退役后不再有此字段
        assert d["market_temp"]["equity_ratio"] >= 0  # 市场状态可用

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
            cwd=str(dashboard_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            shell=True,
        )
        assert result.returncode == 0, f"tsc errors:\n{result.stdout[-500:]}\n{result.stderr[-500:]}"

    def test_vite_build_succeeds(self):
        dashboard_dir = ROOT / "dashboard"
        if not (dashboard_dir / "node_modules").exists():
            pytest.skip("node_modules not installed")
        result = subprocess.run(
            ["npx", "vite", "build"],
            cwd=str(dashboard_dir), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
            shell=True,
        )
        assert result.returncode == 0, f"vite build failed:\n{result.stderr[-500:]}"
