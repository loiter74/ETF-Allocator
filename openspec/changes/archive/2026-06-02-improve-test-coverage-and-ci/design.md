## Context

ETF-Allocator v1.2 当前有 16 个测试文件（14 单元 + 2 集成），覆盖了核心计算函数但存在三个结构性缺口：

1. **回测管道无端到端测试**：`src/backtest/engine.py::run_backtest()` 是流B的核心函数，实现逐月 PIT 回放（数据→因子→评分→温度计→约束→分配→执行→指标），但只有 `compute_metrics()` 被单独测试，完整管道无覆盖。
2. **月报生成无自动化验证**：`src/reports/monthly.py` 的输出只能通过 `run.py --demo` 手动查看，无法验证是否满足 `ds.v1.2.winner.md §十三` 的 4 条报告设计原则。
3. **无 CI/CD**：没有 GitHub Actions 配置，pytest-cov 在 optional-deps 但从未运行。

此外，14 个单元测试各自重复构造测试数据（价格序列、估值序列、内存 DB），`tests/fixtures/` 目录为空，复用率为零。

约束：所有新增测试必须用内存 SQLite + 构造数据，不依赖真实数据库或网络，确保 CI 中稳定运行。

## Goals / Non-Goals

**Goals:**
- 新增 `test_backtest_pipeline.py`：5 个场景覆盖完整 PIT 回放管道（冒烟/上涨/高估/温度计冻结/再平衡）
- 新增 `test_monthly_report.py`：4 个测试验证月报格式符合设计规范 §十三
- 新增 `tests/fixtures/data.py`：提供 `memory_db`, `sample_prices`, `sample_valuations`, `standard_weights`, `standard_scores` 五个共享 fixture
- 新增 `.github/workflows/test.yml`：push/PR 触发 pytest（跳过 integration 标记）+ 覆盖率 HTML 报告
- 更新 `conftest.py`：注册 fixtures，自动 reset_persistence/reset_recovery_tracking 清理

**Non-Goals:**
- 不修改任何 `src/` 业务代码
- 不新增外部依赖（pytest-cov 已在 optional-deps）
- 不追求 100% 覆盖率
- 不添加 API 集成测试的新场景（test_api.py 已有 10 个测试）
- 不修改现有测试文件

## Decisions

### D1: 内存 SQLite 而非真实 DB

**选择**：所有回测管道测试使用 `sqlite3.connect(":memory:")` + `create_tables()`。

**理由**：
- 不依赖 `data/db/etf_data.db` 的真实数据
- CI 中零配置运行
- 每个测试独立隔离（pytest fixture scope=function）
- 构造数据比 mock 更接近真实行为

**替代方案考虑**：Mock `get_available_valuations/get_available_prices` → 拒绝了，因为 mock 会绕过数据库层的 SQL 查询逻辑，测试不到 schema 和 SQL 的正确性。

### D2: 构造 300 天数据而非真实拉取

**选择**：用 numpy 生成价格序列（含涨/跌/趋势/波动）和估值序列（PE/PB/股息率），直接 INSERT 到内存 DB。

**理由**：
- 精确控制场景（上涨行情、极端高估、温度计不一致）
- 测试确定性（不依赖 AkShare/Tushare 网络）
- 速度快（毫秒级 vs 网络级）

**构造策略**：
- 价格序列：起点 100，用 `np.cumprod(1 + r)` 生成，r 从正态分布采样
- 估值序列：PE 从指定分位范围均匀分布生成，PB 随 PE 正相关
- publish_date 设为 trade_date 同一天（避免 PIT 过滤器误杀测试数据）

### D3: 5 个回测场景选择

**选择**：覆盖回测管道的 5 个关键行为路径。

| # | 场景 | 验证点 | 数据构造 |
|---|------|--------|----------|
| 1 | 3 个月平静行情 | 基本管道不崩溃、4 指标输出、配置读取 | PE 分位~50%，全A PB~45%，价格平稳 |
| 2 | 3 个月极端高估 | 温度计触发 >90%→权益 30%，70% 进国债 | PE 分位 95%，全A PB 92% |
| 3 | 温度计不一致冻结 | 第1月一致→第2月不一致→权益冻结 | 第1月双<60%，第2月 PE=95%/PB=50% |
| 4 | 指数回填段排除 | `EXCLUDE_INDEX_BACKFILL=True` 时回填段被排除 | 构造 index_info 中 base_date < trade_date < publish_date |
| 5 | 再平衡触发 | 权重偏离中点超 10pp → 标记卖出 | 白酒权重 28%（偏离中点 17.5% 超 10pp） |

### D4: fixtures/ 目录设计

**选择**：单一 `tests/fixtures/data.py`，通过 `conftest.py` 全局注册。

**替代方案考虑**：每个 fixture 独立文件 → 拒绝了，5 个 fixture 都是数据构造函数，关联紧密，拆散增加查找成本。

**Fixture 定义**：

```python
# conftest.py 注册
pytest_plugins = ["tests.fixtures.data"]

# fixtures/data.py
@pytest.fixture(scope="function")
def memory_db():          # sqlite3 :memory: + create_tables()

@pytest.fixture(scope="function")
def sample_prices():      # 300 天上升价格 pd.Series

@pytest.fixture(scope="function")
def sample_valuations():  # (pe_s, pb_s, dy_s) 三元组

@pytest.fixture(scope="function")
def standard_weights():   # {6资产: 权重} dict

@pytest.fixture(scope="function")
def standard_scores():    # {6资产: 机会分} dict
```

### D5: CI 配置设计

**选择**：单一 job，两个 step——先跑单元测试（跳过 integration 标记），再单独跑 test_formulas.py（这是集成测试但不依赖网络）。

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - checkout
      - setup-python 3.10
      - pip install -e ".[dev]"
      - pytest tests/ -v -m "not integration" --ignore=tests/integration/test_api.py --cov=src --cov-report=term
      - pytest tests/integration/test_formulas.py -v
```

**排除项**：`test_api.py`（需要后端运行）、`test_datasource.py`（需要 AkShare 网络）。

## Risks / Trade-offs

- **[Risk] 构造数据可能与真实数据分布不符** → **Mitigation**: 回测管道测试的目标是验证"管道连通性"而非"策略收益"，构造数据只需覆盖边界条件（极端高估、温度计不一致），不需要统计真实性。
- **[Risk] CI 首次运行可能因 pytest-cov 配置报错** → **Mitigation**: 在 `pyproject.toml` 中预配置 `[tool.coverage.*]` 段，指定 source=src。
- **[Trade-off] 不回测真实历史数据** → 这是有意的设计选择。真实历史回测是 `validate.py` 的职责，测试的是"管道逻辑正确性"而非"策略在历史上表现如何"。两者互补。

## Migration Plan

1. P3（fixtures + conftest）→ 零风险，不影响现有测试
2. P2（CI 配置）→ 推送后生效，可先跳过 test_api.py
3. P0（回测管道测试）→ 依赖 P3 的 fixtures
4. P1（月报测试）→ 独立，可与 P0 并行

回滚：删除新增的 4 个文件，还原 conftest.py 和 pyproject.toml 修改即可。

## Open Questions

无。所有技术决策在上方 D1-D5 中已确定。
