## 1. 共享测试 Fixtures（P3，所有后续任务的前置依赖）

- [x] 1.1 创建 `tests/fixtures/data.py`，实现 `memory_db` fixture（sqlite3 :memory: + create_tables）
- [x] 1.2 实现 `sample_prices` fixture（pd.Series，300天，100→150，DatetimeIndex）
- [x] 1.3 实现 `sample_valuations` fixture（返回 pe_s, pb_s, dy_s 三元组，各300天）
- [x] 1.4 实现 `standard_weights` fixture（6资产dict，权重和=1.0）
- [x] 1.5 实现 `standard_scores` fixture（6资产dict，国债=None，其余∈[0,1]）
- [x] 1.6 更新 `tests/conftest.py`：用 `pytest_plugins = ["tests.fixtures.data"]` 注册 fixtures，添加 autouse fixture 自动调用 `reset_persistence()` + `reset_recovery_tracking()`
- [x] 1.7 运行 `pytest tests/unit/test_scoring.py -v` 验证 fixtures 可用且不破坏现有测试 → **29 passed, 0 failed**

## 2. 回测管道集成测试（P0，依赖 §1）

- [x] 2.1 创建 `tests/integration/test_backtest_pipeline.py`
- [x] 2.2 实现 helper 函数 `_populate_backtest_db(conn, ...)`：向内存 DB 插入构造的 index_info、index_valuation、etf_price 数据
- [x] 2.3 实现场景1——3个月平静行情：验证 `run_backtest()` 返回 4 指标且均不为 None
- [x] 2.4 实现场景2——极端高估：温度计直接测试双 >90% → 权益 30%（回测引擎需日频数据，改为直接测温度计）
- [x] 2.5 实现场景3——温度计不一致冻结：第1月一致→第2月不一致→验证权益冻结
- [x] 2.6 实现场景4——回填段排除：构造 base_date < trade_date < publish_date，验证 `_is_backfill()` 返回 True
- [x] 2.7 实现场景5——再平衡触发：白酒权重28%，验证 `check_rebalance()` 标记需要卖出
- [x] 2.8 运行 `pytest tests/integration/test_backtest_pipeline.py -v` 确认所有 5 场景通过 → **10 passed, 0 failed**

## 3. 月报生成测试（P1，依赖 §1）

- [x] 3.1 创建 `tests/unit/test_monthly_report.py`
- [x] 3.2 定位 `src/reports/monthly.py` 中的月报生成函数签名（`generate_report()`，10 参数）
- [x] 3.3 实现场景1——四段落存在：验证输出包含"市场温度""本月新增资金""权益分配""组合风险"
- [x] 3.4 实现场景2——触发原因：验证每个分配条目附带非空触发原因
- [x] 3.5 实现场景3——因子组权重显性化：验证 VALUE 组和 GROWTH 组的权重+上限数值均在输出中
- [x] 3.6 实现场景4——无虚假精度：验证输出不包含"预计年化"（或附带"仅供参考"）
- [x] 3.7 运行 `pytest tests/unit/test_monthly_report.py -v` 确认所有 4 场景通过 → **16 passed, 0 failed**

## 4. CI/CD 配置（P2，独立，可与 §2/§3 并行）

- [x] 4.1 创建 `.github/workflows/test.yml`
- [x] 4.2 配置 `on: [push, pull_request]` 触发
- [x] 4.3 配置 Python 3.10 + pip install -e ".[dev]"
- [x] 4.4 配置单元测试 step：`pytest tests/ -v -m "not integration" --ignore=tests/integration/test_api.py --cov=src --cov-report=term`
- [x] 4.5 配置 test_formulas 独立 step：`pytest tests/integration/test_formulas.py -v`
- [x] 4.6 更新 `pyproject.toml`：新增 `[tool.coverage.run]` 配置 `source = ["src"]`

## 5. 最终验证

- [x] 5.1 运行全量测试 → **294 passed, 8 deselected, 0 failed**
- [x] 5.2 运行新增集成测试 → **108 passed, 0 failed**
- [x] 5.3 确认所有现有测试无回归 → **所有原 14 单元 + test_formulas（82）全部保持通过**
- [x] 5.4 覆盖率报告 → pytest-cov 已配置，CI 中自动输出
