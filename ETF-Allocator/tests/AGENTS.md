# tests/ — 测试

pytest | 14 个单元测试文件 | 1 个 integration 占位

## STRUCTURE

```
tests/
├── conftest.py              # sys.path 设置
├── unit/
│   ├── test_config.py       # 配置完整性
│   ├── test_store_*.py      # schema + validator
│   ├── test_datasource.py   # AkShare 适配器（需网络）
│   ├── test_factors_*.py    # value / dividend / momentum / risk
│   ├── test_scoring.py      # 机会分映射
│   ├── test_regime.py       # 温度计
│   ├── test_risk.py         # 风险控制
│   ├── test_constraints.py  # 组合约束（最大文件 214 行）
│   └── test_allocation.py   # 资金分配
└── integration/
    └── __init__.py
```

## CONVENTIONS

- **pytest markers**：`integration`（需网络/AkShare）、`slow`（>1秒）
- **conftest.py** 只做 `sys.path.insert(0, project_root)`，不做 fixture
- **中文资产名**：测试中也用 `"白酒ETF"` 等中文字符串

## ANTI-PATTERNS

- **不要**让测试依赖外部网络（标注 `@pytest.mark.integration`）
- **不要**假设全局状态已重置 — 涉及温度计/风险恢复的测试后调用 `reset_persistence()` / `reset_recovery_tracking()`
