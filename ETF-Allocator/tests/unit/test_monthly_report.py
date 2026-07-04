"""
tests/unit/test_monthly_report.py — 月报文本格式验证。

验证 src/reports/monthly.py::generate_report() 的输出符合
ds.v1.2.winner.md §十三 的 4 条报告设计原则。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from datetime import date

from src.reports.monthly import generate_report
from config.settings import TARGET_BANDS, GROUP_CAPS


# ── helpers ──

def _make_temp_result(
    equity_ratio: float = 0.70,
    hs300_pe: float | None = 0.72,
    all_a_pb: float | None = 0.68,
    label: str = "中等偏高（60-80%）",
    detail: str = "双指标均在 60-80% 档，一致触发降温",
):
    return {
        "temperature": (hs300_pe or 0.5) if hs300_pe is not None else 0.5,
        "equity_ratio": equity_ratio,
        "bond_ratio": round(1.0 - equity_ratio, 10),
        "hs300_pe_pct": hs300_pe,
        "all_a_pb_pct": all_a_pb,
        "label": label,
        "detail": detail,
    }


def _make_factors():
    return {
        "白酒ETF": {"pe_percentile": 0.15},
        "银行ETF": {"pb_percentile": 0.22, "dividend_percentile": 0.30},
        "红利ETF": {"dividend_percentile": 0.70},
        "沪深300ETF": {"pe_percentile": 0.55},
        "科创50ETF": {"momentum_percentile": 0.68, "trend_multiplier": 1.0},
        "国债ETF": {},
    }


def _make_scores():
    return {
        "白酒ETF": 0.85,
        "银行ETF": 0.88,
        "红利ETF": 0.80,
        "沪深300ETF": 0.78,
        "科创50ETF": 0.92,
        "国债ETF": None,
    }


def _make_allocation():
    return {
        "白酒ETF": 2500,
        "银行ETF": 1500,
        "红利ETF": 1200,
        "沪深300ETF": 1100,
        "科创50ETF": 700,
        "国债ETF": 3000,
    }


def _make_weights():
    return {
        "白酒ETF": 0.12,
        "银行ETF": 0.18,
        "红利ETF": 0.08,
        "沪深300ETF": 0.22,
        "科创50ETF": 0.13,
        "国债ETF": 0.27,
    }


def _make_upper_limits():
    return {
        "白酒ETF": 0.25,
        "银行ETF": 0.30,
        "红利ETF": 0.25,
        "沪深300ETF": 0.30,
        "科创50ETF": 0.15,
        "国债ETF": 0.20,
    }


def _make_constraints_result():
    return {
        "group_weights": {"VALUE": 0.52, "GROWTH": 0.13},
        "group_caps": {"VALUE": 0.60, "GROWTH": 0.15},
        "buy_coefficients": {},
        "max_buy": {},
    }


def _generate_standard_report(**overrides):
    """生成标准月报，可选择性覆盖参数。"""
    params = dict(
        invest_date=date(2026, 6, 1),
        new_money=10000.0,
        temp_result=_make_temp_result(),
        factors=_make_factors(),
        scores=_make_scores(),
        allocation=_make_allocation(),
        weights=_make_weights(),
        upper_limits=_make_upper_limits(),
        constraints_result=_make_constraints_result(),
    )
    params.update(overrides)
    return generate_report(**params)


# ════════════════════════════════════════════════════════════════
# 场景 1: 四段落必须存在
# ════════════════════════════════════════════════════════════════

class TestReportSections:
    """场景1: 月报输出必须包含四个标准段落。"""

    def test_market_temperature_section(self):
        report = _generate_standard_report()
        assert "【市场温度】" in report

    def test_new_money_section(self):
        report = _generate_standard_report()
        assert "【本月新增资金】" in report

    def test_equity_allocation_section(self):
        report = _generate_standard_report()
        assert "【权益分配】" in report

    def test_portfolio_risk_section(self):
        report = _generate_standard_report()
        assert "【组合风险】" in report


# ════════════════════════════════════════════════════════════════
# 场景 2: 每个分配条目含触发原因
# ════════════════════════════════════════════════════════════════

class TestTriggerReasons:
    """场景2: 每行分配附带非空触发原因。"""

    def test_baijiu_has_trigger_reason(self):
        report = _generate_standard_report()
        # 白酒机会分 0.85，PE 分位 15% → 触发原因含"PE分位 15%"
        assert "PE分位 15%" in report

    def test_bank_has_trigger_reason(self):
        report = _generate_standard_report()
        # 银行 PB 分位 22%, 股息率 30%
        assert "PB分位 22%" in report or "股息率分位 30%" in report

    def test_dividend_has_trigger_reason(self):
        report = _generate_standard_report()
        assert "股息率分位 70%" in report

    def test_kechuang_has_trigger_reason(self):
        report = _generate_standard_report()
        # 科创50 动量 68%, 趋势 ON
        assert "动量分位 68%" in report or "趋势ON" in report

    def test_guozhai_has_defense_reason(self):
        report = _generate_standard_report()
        assert "国债避险配置" in report


# ════════════════════════════════════════════════════════════════
# 场景 3: 因子组权重显性化
# ════════════════════════════════════════════════════════════════

class TestFactorGroupDisplay:
    """场景3: VALUE 组和 GROWTH 组的权重+上限均展示。"""

    def test_value_group_weight_and_cap_displayed(self):
        report = _generate_standard_report()
        assert "52.0%" in report   # VALUE 组权重
        assert "60%" in report     # VALUE 组上限

    def test_growth_group_weight_and_cap_displayed(self):
        report = _generate_standard_report()
        assert "13.0%" in report   # GROWTH 组权重
        assert "15%" in report     # GROWTH 组上限


# ════════════════════════════════════════════════════════════════
# 场景 4: 无虚假精度
# ════════════════════════════════════════════════════════════════

class TestNoFakePrecision:
    """场景4: 不含"预计年化"点估计（除非带"仅供参考"标注）。"""

    def test_no_predicted_annualized_return(self):
        report = _generate_standard_report()
        assert "预计年化" not in report

    def test_disclaimer_present(self):
        """底注应包含免责声明。"""
        report = _generate_standard_report()
        assert "不构成投资建议" in report


# ════════════════════════════════════════════════════════════════
# 边界情况
# ════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界情况：缺失数据、零分配等。"""

    def test_report_with_none_factors(self):
        """全部因子为 None 时不崩溃。"""
        report = _generate_standard_report(
            factors={"白酒ETF": {}, "银行ETF": {}, "红利ETF": {},
                     "沪深300ETF": {}, "科创50ETF": {}, "国债ETF": {}},
        )
        assert "ETF配置月报" in report
        assert "【市场温度】" in report

    def test_report_with_zero_new_money(self):
        """新钱为 0 时不崩溃。"""
        report = _generate_standard_report(new_money=0.0)
        assert "0 元" in report or "权益投资: 0" in report

    def test_report_with_full_equity(self):
        """温度计权益 100% 时格式正确。"""
        report = _generate_standard_report(
            temp_result=_make_temp_result(equity_ratio=1.00, detail="双指标均<60%"),
        )
        assert "100%" in report
        assert "0 元" in report  # 国债 = 0


# ════════════════════════════════════════════════════════════════
# 场景 5: 国债执行状态（v1.3 新增）
# ════════════════════════════════════════════════════════════════

class TestBondExecutionStatus:
    """v1.3: 国债执行状态区块渲染。"""

    def _make_bond_status(self, **overrides):
        status = {
            "balance": 11000.0,
            "min_purchase": 14000,
            "total_interest": 126.0,
            "can_buy": False,
            "lots_available": 0,
        }
        status.update(overrides)
        return status

    def test_bond_status_section_present(self):
        """传入 bond_status 时应显示国债执行状态区块。"""
        report = _generate_standard_report(bond_status=self._make_bond_status())
        assert "【国债执行状态】" in report
        assert "累积制" in report

    def test_bond_status_shows_deposit_amount(self):
        """显示本月固收应配金额。"""
        report = _generate_standard_report(bond_status=self._make_bond_status())
        assert "本月固收应配" in report

    def test_bond_status_shows_interest(self):
        """有逆回购收益时显示。"""
        report = _generate_standard_report(bond_status=self._make_bond_status(total_interest=126.0))
        assert "逆回购收益" in report

    def test_bond_status_no_buy(self):
        """未触发买入时显示等待信息。"""
        report = _generate_standard_report(
            bond_status=self._make_bond_status(can_buy=False, balance=5000)
        )
        assert "暂不买入" in report
        assert "距下一手门槛" in report

    def test_bond_status_buy_triggered(self):
        """触发买入时显示买入信息。"""
        report = _generate_standard_report(
            bond_status=self._make_bond_status(can_buy=True, lots_available=1, balance=17000)
        )
        assert "买入 1 手" in report
        assert "511010" in report

    def test_bond_status_shows_remaining_after_buy(self):
        """买入后有余留时显示余留金额。"""
        report = _generate_standard_report(
            bond_status=self._make_bond_status(can_buy=True, lots_available=1, balance=17000)
        )
        assert "买入后余留" in report

    def test_bond_status_backward_compatible(self):
        """不传 bond_status 时报告正常生成（向后兼容）。"""
        report = _generate_standard_report()
        assert "ETF配置月报" in report
        assert "【国债执行状态】" not in report
