# 重构计划（Refactor Plan）

> 生成日期：2026-07-25  
> 分支：`chore/nightly-audit-refactor`  
> 配套：`docs/architecture-current.md`、`docs/audit-report.md`  
> 执行约束（用户第四阶段）：只自动实施 **P0** 全部 + **最多 5 个低风险 P1**，不改外部接口、不重命名大文件、不引入新框架、不删用途不明代码。

每项任务含：涉及文件 / 目标 / 风险 / 验证方法 / 预计影响范围。

---

## P0 — 明确安全风险（必须修）

### P0-1  Tushare Token 改环境变量
- **涉及文件**：
  - `ETF-Allocator/scripts/import_pb.py`
  - `ETF-Allocator/scripts/import_pb_all.py`
  - `ETF-Allocator/scripts/import_pb_one.py`
  - `ETF-Allocator/scripts/auto_import_pb.py`
  - `ETF-Allocator/scripts/tushare_import.py`
- **目标**：把硬编码 `TOKEN = '3d769e...'` 改为 `TOKEN = os.environ.get("TUSHARE_TOKEN")`，缺失时 `sys.exit("请设置 TUSHARE_TOKEN 环境变量")`。
- **风险**：低 — 脚本无单测覆盖；改动只影响脚本启动期。**不改 git 历史**（需人工 `git filter-repo` + **token 轮换**，本 agent 不执行）。
- **验证方法**：`python -c "import ast; ast.parse(open('scripts/import_pb.py').read())"` 全部通过；手动 `TUSHARE_TOKEN=test python scripts/import_pb.py` 不再爆 token；`grep -rn '3d769e' scripts/` 应为空。
- **影响范围**：仅 scripts/，不影响 src/ 运行时行为。
- **是否本次执行**：**是**（代码侧）。

---

## P1 — 低风险结构优化（本次最多选 5 个）

> 选择标准：行为不变 + 有测试守护 + 单文件改动 < 30 行。

### P1-1  `_RECOVERY_DAYS` 移入 settings（参数集中原则）
- **涉及文件**：`config/settings.py`、`src/risk/controller.py`
- **目标**：settings 新增 `RISK_RECOVERY_DAYS = 20`；controller 从 settings import，删除模块级 `_RECOVERY_DAYS = 16` 字面量。
- **风险**：极低 — 值不变，纯搬运。
- **验证方法**：`pytest tests/unit/test_risk.py tests/unit/test_config.py -v`。
- **影响范围**：risk 模块。
- **是否本次执行**：**是**。

### P1-2  `KECHUANG_TREND_OFF_MULTIPLIER` wiring（修虚假配置）
- **涉及文件**：`run.py`、`src/factors/momentum.py`
- **目标**：把 `run.py:277` 硬编码 `0.50 if not trend_on else 1.0` 改为读 `KECHUANG_TREND_OFF_MULTIPLIER`；`momentum.py:85` 同步。settings 中的 `0.50` 真正生效。
- **风险**：低 — 当前配置值正好 = 硬编码值，行为等价；变的是"以后改配置会生效"。
- **验证方法**：`pytest tests/unit/test_factors_momentum.py tests/unit/test_scoring.py -v`；并临时把 settings 值改成 0.30 跑一次确认 wiring 生效（验证后改回）。
- **影响范围**：科创50机会分计算。
- **是否本次执行**：**是**。

### P1-3  `NEW_MONEY` / `DEFAULT_TOTAL` 进 settings
- **涉及文件**：`config/settings.py`、`run.py`、`src/api/server.py`
- **目标**：settings 新增 `DEFAULT_NEW_MONEY = 8_000`、`DEFAULT_TOTAL_ASSETS = 500_000`；run.py / server.py 改 import。
- **风险**：低 — 值不变；唯一注意 `run_rebalance_check` 用的 `100_000` 是另一个语义（再平衡演示默认），**不**统一，仅记录到 audit。
- **验证方法**：`pytest tests/unit/ tests/integration/test_api_idempotency.py -v`；手动 `python run.py report --demo` 输出不变。
- **影响范围**：默认值来源；外部 CLI/API 接口签名不变。
- **是否本次执行**：**是**。

### P1-4  温度计档位去重（`run.py` 与 `reports/monthly.py` 改读 settings）
- **涉及文件**：`run.py`、`src/reports/monthly.py`（保留 `thermometer._tier` 不动）
- **目标**：
  - `run.py:458-469` 的 `_temp_tier` 和 `labels` 改为从 `settings.TEMP_THRESHOLDS` 派生（动态生成 tier 函数与 label 字典），不再硬编码 `0.60/0.80/0.90`。
  - `reports/monthly.py:18-24` 的倒序阈值常量改为同样从 settings 派生。
- **风险**：中低 — 温度档是核心规则，需仔细对照现有输出。`thermometer._tier` 是权威实现，**不动它**，只让其他两处对齐它的语义。
- **验证方法**：`pytest tests/unit/test_regime.py tests/unit/test_monthly_report.py tests/unit/test_regression.py -v`；手动对比改前/改后 `python run.py report --demo` 的温度计输出文本逐字相同。
- **影响范围**：温度计文本与冻结判定。
- **是否本次执行**：**是**。

### P1-5  `compute_metrics` 调用 `_nav_from_returns` 去重
- **涉及文件**：`src/backtest/engine.py`
- **目标**：`compute_metrics` (line ~240) 内联的 NAV 构造改为调用已有的 `_nav_from_returns` (line 270-277)。
- **风险**：低 — `test_backtest_pipeline.py` 守护指标计算口径。
- **验证方法**：`pytest tests/integration/test_backtest_pipeline.py -v`，对比指标输出与改前完全一致。
- **影响范围**：回测指标计算路径。
- **是否本次执行**：**是**。

---

### 候选但本次不自动执行的 P1（记录）

| ID | 项目 | 不执行原因 |
|---|---|---|
| P1-X1 | A2 CORS 改环境变量 | 涉及部署假设，需确认默认值语义 |
| P1-X2 | B2 `update_data` 异常处理 | 改了可能让 cron 崩，需设计决策 |
| P1-X3 | B4/H akshare 加 logging | 需先建项目级 logging 配置（否则无效） |
| P1-X4 | J2 `/api/health` 端点 | 增量功能，属扩展非重构 |
| P1-X5 | C2 动量循环去重 | 涉及回测精度，需对比双输出 |

---

## P2 — 需设计决策（仅记录，不执行）

### P2-1  抽取共享 `pipeline.py`（消除 C3 三重重复）
- **涉及**：`run.py` / `validate.py` / `src/api/server.py` → 新增 `src/pipeline.py`
- **目标**：流A 9 步流水线提取为纯函数 `build_monthly_allocation(...)`，三个入口都调用。
- **风险**：高（流水线是产品核心）；需先有完整回归测试基线。
- **影响范围**：全项目。
- **前置条件**：补齐 `run.run_report` / `validate.run_test` 入口测试。

### P2-2  `_low_vol_days` 持久化（B1）
- **涉及**：`src/risk/controller.py`、`run.py`
- **决策点**：当前"每次 cron 重置"是否已是预期行为？需对照 ds.v1.3 §八 确认。

### P2-3  删除 `validate.simple_backtest` 死代码（D1）
- 需确认无外部 notebook / cron 调用。

### P2-4  统一 group 约束实现（D4）
- `constraints.check_factor_group_constraint` 与 `allocator._apply_group_constraint` 二选一。

### P2-5  前端 API 客户端统一（C4 + 重复 BASE）
- 抽 `dashboard/src/lib/api.ts`，AiriDashboard 内联 fetch 收敛到 hook。

### P2-6  demo 数据移出正式模块（J1）
- `_demo_factors` / `_demo_weights` 迁到 `tests/fixtures/`。

### P2-7  引入 logging 框架（H）
- 项目级 logger 配置（`utils/logging.py` + `LOG_LEVEL` env）。

### P2-8  过长函数拆分（E）
- `run_report` / `run_backtest` / `calculate_factors` 拆子函数。

### P2-9  `store/schema.py` CHECK 约束动态化（F）
- 资产名从 `settings.ASSETS` 派生，而非字面量。

---

## P3 — 暂不建议处理

| ID | 项目 | 原因 |
|---|---|---|
| P3-1 | `validator.validate_publish_date_not_future` 死函数 | 看起来是预留 API，无害 |
| P3-2 | 前端未用依赖清理 | 需逐个验证无引用，收益低 |
| P3-3 | `000985` 注释误标"上证50替代" | 仅注释错误，行为正确 |

---

## 执行顺序（本次）

```
1. P0-1  Tushare token 改 env         （scripts/，5 文件）
2. P1-1  RISK_RECOVERY_DAYS 进 config  （最小，先暖手）
3. P1-2  KECHUANG multiplier wiring
4. P1-3  DEFAULT_NEW_MONEY / TOTAL 进 config
5. P1-5  compute_metrics 去重          （有回测守护）
6. P1-4  温度计档位去重                （最复杂，最后做）
每步：改 → pytest 相关子集 → 单独 commit
```

每步提交信息格式：`refactor(<area>): <动作> (<原因，引 audit §X>)`
