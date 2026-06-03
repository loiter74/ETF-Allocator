"""
pytest 全局配置。
"""
import sys
import os

# 确保 src/ 和 config/ 在 Python path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)

# 注册共享测试 fixtures
pytest_plugins = ["tests.fixtures.data"]


def pytest_configure(config):
    """注册自定义 markers。"""
    config.addinivalue_line(
        "markers", "integration: tests that require network/akshare access"
    )
    config.addinivalue_line(
        "markers", "slow: tests that take > 1 second"
    )


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _auto_reset_stateful_modules():
    """
    每个测试后自动重置全局状态模块，防止测试间交叉污染。

    温度计持久化 (_last_equity_ratio) 和波动率恢复计数 (_low_vol_days)
    是模块级变量，跨测试共享。此 fixture 确保每次测试后重置。
    """
    yield
    from src.regime.thermometer import reset_persistence
    from src.risk.controller import reset_recovery_tracking
    reset_persistence()
    reset_recovery_tracking()
