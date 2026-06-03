## Why

ETF-Allocator v1.2 的实现代码与 `ds.v1.2.winner.md` 设计文档高度一致（15 章 + 4 条补充建议 100% 匹配），但测试覆盖存在结构性缺口：缺少全流程 PIT 回测集成测试、月报生成测试，且无 CI/CD 自动化。当前 16 个测试文件覆盖了核心计算函数（因子、评分、约束、温度计），但"管道层"和"报告层"的断裂点不可见——回测引擎 `run_backtest()` 和月报 `monthly.py` 完全没有自动化测试，只能靠手动 `--demo` 验证。此外 fixtures/ 目录为空、无覆盖率测量、无 GitHub Actions，每次改动只能本地手动跑 pytest。

## What Changes

- **新增** `tests/integration/test_backtest_pipeline.py`：3-6 个月完整 PIT 回放集成测试（上涨/高估/温度计冻结/再平衡触发 5 个场景）
- **新增** `tests/unit/test_monthly_report.py`：月报文本格式验证（4 个段落、触发原因、因子组风险展示、无虚假精度）
- **新增** `tests/fixtures/data.py`：共享测试数据构造（内存 DB、价格序列、估值序列、标准权重/评分）
- **新增** `.github/workflows/test.yml`：CI 自动化（push/PR 触发，单元测试 + 覆盖率报告）
- **修改** `tests/conftest.py`：注册共享 fixtures
- **修改** `pyproject.toml`：添加 pytest-cov 配置

## Capabilities

### New Capabilities
- `backtest-pipeline-test`: 全流程 PIT 回测集成测试，覆盖从数据库读取→因子计算→评分→温度计→约束→分配→执行→指标的完整管道
- `monthly-report-test`: 月报文本生成自动化测试，验证输出格式符合 `ds.v1.2.winner.md §十三` 规范
- `shared-test-fixtures`: 共享测试数据构造 fixtures，消除 14 个测试文件的重复构造代码
- `ci-cd-pipeline`: GitHub Actions CI 配置，push/PR 触发自动运行单元测试 + 覆盖率报告

### Modified Capabilities
<!-- No existing specs to modify -->

## Impact

- **新增文件**: 4 个（2 测试文件 + 1 fixtures + 1 CI 配置）
- **修改文件**: 2 个（conftest.py + pyproject.toml）
- **依赖**: pytest-cov（已在 optional-deps，无需新安装）
- **CI**: GitHub Actions（免费，公开仓库无限额度）
- **风险**: 零——所有新增测试不依赖真实数据库，用内存 SQLite + 构造数据，可在 CI 中稳定运行
- **不涉及**: 不修改任何 src/ 业务代码，纯测试基础建设
