# ci-cd-pipeline

GitHub Actions CI 配置，push/PR 触发自动运行测试 + 覆盖率报告。

## ADDED Requirements

### Requirement: Push 和 PR 触发测试
系统 SHALL 在每次 push 和 pull_request 事件时自动运行 pytest 测试套件。

#### Scenario: Push 触发 CI 运行
- **WHEN** 任何分支有新的 push
- **THEN** GitHub Actions SHALL 触发 `test` workflow，运行 pytest 并输出结果

### Requirement: 单元测试跳过网络依赖
系统 SHALL 在 CI 中运行 pytest 时跳过标记为 `integration` 的测试和需要后端运行的 `test_api.py`。

#### Scenario: CI 跳过 integration 标记测试
- **WHEN** CI 执行 `pytest tests/ -v -m "not integration" --ignore=tests/integration/test_api.py`
- **THEN** `test_datasource.py` 中的测试 SHALL 被跳过，`test_api.py` SHALL 不被执行

### Requirement: test_formulas.py 独立运行
系统 SHALL 在 CI 中单独运行 `tests/integration/test_formulas.py`，因为该文件不依赖网络但标记为集成测试。

#### Scenario: test_formulas 在 CI 中通过
- **WHEN** CI 执行 `pytest tests/integration/test_formulas.py -v`
- **THEN** 所有 40+ 个公式验证测试 SHALL 全部通过

### Requirement: 代码覆盖率报告
系统 SHALL 在 CI 中生成 `src/` 目录的代码覆盖率报告，以终端文本格式输出。

#### Scenario: 覆盖率报告输出
- **WHEN** CI 执行 `pytest ... --cov=src --cov-report=term`
- **THEN** 终端输出 SHALL 包含覆盖率摘要（模块名、语句覆盖率百分比）

### Requirement: Python 3.10 运行环境
系统 SHALL 使用 Python 3.10 作为 CI 运行环境，与项目 `requires-python = ">=3.10"` 一致。

#### Scenario: CI 使用 Python 3.10
- **WHEN** CI workflow 启动
- **THEN** `setup-python` action SHALL 配置 `python-version: "3.10"`
