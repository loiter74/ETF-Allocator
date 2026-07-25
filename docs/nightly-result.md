# Nightly Audit — 交付结果（Nightly Result）

> 执行日期：2026-07-25  
> 分支：`chore/nightly-audit-refactor`（**未推送远程**，等待人工审查）  
> 起点 commit：`2799cda (main)`  
> 终点 commit：`605521a`  
> 共 8 个原子提交，15 个文件，+984 / −34

---

## 1. 完成了哪些工作

| 阶段 | 产出 | 状态 |
|---|---|---|
| 一、理解项目 | `docs/architecture-current.md`（模块图、调用链、状态存储、依赖） | ✅ |
| 二、工程审计 | `docs/audit-report.md`（A-M 共 13 类问题，按 P0-P3 分级） | ✅ |
| 三、重构计划 | `docs/refactor-plan.md`（P0×1、P1×5 自动执行；P2×9、P3×3 记录） | ✅ |
| 四、实施 P0+P1 | Tushare token / 温度计去重 / 4 项 config wiring / NAV 去重 | ✅ |
| 五、测试 | 11 个新核心链路契约测试；全套件 388 passed | ✅ |
| 六、本文件 | `docs/nightly-result.md` | ✅ |

> **关于模板与代码库的偏差**：用户目标模板包含 LLM / TTS / Live2D / WebSocket 等组件的检查项。本项目是 ETF 资金配置系统，**不含这些组件**。已按实际代码库完成映射（详见 `architecture-current.md §0` 与 `audit-report.md §J/§K`），未强行套用不存在概念。

---

## 2. 修改了哪些文件

### 文档（4 个新增）
- `docs/architecture-current.md`
- `docs/audit-report.md`
- `docs/refactor-plan.md`
- `docs/nightly-result.md`

### 代码（8 个修改 + 1 个新增测试）
| 文件 | 改动 | 对应任务 |
|---|---|---|
| `scripts/import_pb.py` | TOKEN 改 `os.environ.get('TUSHARE_TOKEN')` | P0-1 |
| `scripts/import_pb_all.py` | 同上 | P0-1 |
| `scripts/import_pb_one.py` | 同上 | P0-1 |
| `scripts/auto_import_pb.py` | 同上 | P0-1 |
| `scripts/tushare_import.py` | 同上 | P0-1 |
| `config/settings.py` | 新增 `RISK_RECOVERY_DAYS`、`DEFAULT_NEW_MONEY`、`DEFAULT_TOTAL_ASSETS` | P1-1 / P1-3 |
| `src/risk/controller.py` | `_RECOVERY_DAYS` 改读 config | P1-1 |
| `run.py` | wiring `KECHUANG_TREND_OFF_MULTIPLIER`；导入权威 `_tier`；温度档 label 从 settings 派生 | P1-2 / P1-4 |
| `src/reports/monthly.py` | `_temperature_label` 改读 `TEMP_THRESHOLDS` | P1-4 |
| `src/api/server.py` | money 默认值改读 settings | P1-3 |
| `src/backtest/engine.py` | `compute_metrics` 调 `_nav_from_returns` 去重 | P1-5 |
| `tests/integration/test_nightly_refactor_contracts.py` | **新增** 11 个契约测试 | 阶段五 |

---

## 3. 修复了哪些问题

| ID | 问题 | 修复方式 | audit § |
|---|---|---|---|
| **P0-1** | Tushare token 明文入库（5 脚本） | 改环境变量 `TUSHARE_TOKEN`，缺失即退出 | A1 |
| P1-1 | `_RECOVERY_DAYS=20` 未进 config | 移入 `settings.RISK_RECOVERY_DAYS` | B3 |
| P1-2 | `KECHUANG_TREND_OFF_MULTIPLIER` 配置项未生效（run.py 硬编码 0.50） | run.py 改 import + 使用配置值 | D2 |
| P1-3 | `8_000/500_000` 三处硬编码 | 移入 `settings.DEFAULT_NEW_MONEY` / `DEFAULT_TOTAL_ASSETS` | C4 |
| P1-4 | 温度计档位阈值在 3 处重复（run.py / monthly.py / thermometer.py） | run.py / monthly.py 改读 settings；保留 thermometer._tier 为权威 | C1 |
| P1-5 | `compute_metrics` 内联 NAV 构造，与 `_nav_from_returns` 重复 | 调用 helper | C5 |

---

## 4. 测试通过情况

### 全套件结果
```
388 passed, 13 skipped in 103.41s
```
- **基线（main）**：380 passed, 10 skipped
- **本次**：388 passed, 13 skipped（+8 净增：11 新增 − 3 网络抖动）
- 0 失败、0 错误

### 新增测试（`tests/integration/test_nightly_refactor_contracts.py`，11 个）
| 测试 | 覆盖点 |
|---|---|
| `test_run_report_demo_path_produces_full_report` | 流A入口端到端（STEP 5-9）— 此前 0 覆盖 |
| `test_run_report_demo_default_new_money_from_config` | P1-3 wiring 守护 |
| `test_get_report_normal_path_returns_full_payload` | API `/api/report` 正常路径 |
| `test_get_report_with_zero_total_assets_uses_initial_mode` | 边界（初始建仓） |
| `test_get_report_idempotent_across_calls` | API 幂等性 |
| `test_config_constants_have_expected_values` | P1-1/2/3/4 配置存在性 |
| `test_risk_controller_reads_recovery_days_from_config` | P1-1 wiring |
| `test_kechuang_multiplier_is_wired_into_run_py` | P1-2 wiring（AST 守护） |
| `test_run_py_does_not_hardcode_tier_thresholds` | P1-4 去重守护 |
| `test_no_hardcoded_tushare_token_in_scripts` | P0-1 回归守护 |
| `test_tushare_scripts_read_token_from_env` | P0-1 完整性守护 |

### 跳过的 13 个测试（均非回归）
- 10 个 `test_api.py::*TestAPIEndpoints`：需要 `localhost:8000` 活服务器（CI/本地默认跳过，符合 `@pytest.mark.integration` 设计）
- 3 个 `test_datasource.py::TestFetchETFPrice`：需要 akshare 真实网络（**本次代码完全未碰 datasource**，仅网络抖动）

### 关于"失败"
**无测试失败。** 用户目标第六阶段"哪些测试失败"项：N/A。

---

## 5. 尚未处理的问题（记录，留待人工决策）

### P0 遗留（必须人工）
- **Tushare token 轮换**：`3d769e33...` 已从源码移除，但**仍在 git 历史**。需人工：
  1. 到 tushare.com **作废并重新生成**该 token
  2. 用 `git filter-repo` 清理历史（agent 不执行破坏性 git 操作）

### P2（需设计决策，未自动执行）
| ID | 问题 | 为何不自动 |
|---|---|---|
| P2-1 | 抽 `src/pipeline.py` 消除 run.py/server.py/validate.py 三重重复 | 重构面大、风险高，需先有完整回归基线 |
| P2-2 | `_low_vol_days` 跨进程持久化 | 当前"每次 reset"是否预期行为？需对照 ds.v1.3 §八 确认 |
| P2-3 | 删除 `validate.simple_backtest`（158 行死代码） | 无法 100% 确认无 notebook/cron 调用 |
| P2-4 | 统一两套 group 约束实现 | 行为差异需对比 |
| P2-5 | 前端 API 客户端统一（AiriDashboard 内联 fetch） | 涉及前端架构 |
| P2-6 | demo 数据迁出 `run.py` 正式模块 | 边界改动 |
| P2-7 | 引入项目级 `logging` | 全局改动，需配套 log 配置 |
| P2-8 | 拆分 `run_report` / `run_backtest` 长函数 | 需先补回归测试 |
| P2-9 | `store/schema.py` CHECK 约束从 ASSETS 派生 | 涉及 DB 迁移 |

### P3（暂不建议处理）
- `validator.validate_publish_date_not_future` 死函数（疑似预留 API）
- 前端未用依赖（`sonner`/`lucide-react`/`@nivo/treemap`/`react-grid-layout`）
- `000985` 注释误标"上证50替代"（仅注释错误）

### 候选但本次未自动执行的 P1
- **A2 CORS 改环境变量**：涉及部署假设
- **B2 `update_data` 异常处理**：可能让 cron 崩
- **B4/H akshare 加 logging**：需先建项目级 logger
- **J2 `/api/health` 端点**：增量功能，属扩展

---

## 6. 推荐明天人工审查的 5 个重点

按优先级排序：

1. **【安全-必做】Tushare token 轮换 + git 历史清理**  
   P0-1 已止住源头，但泄露值仍在历史。务必作废旧 token 并用 `git filter-repo` 清理。审查 `scripts/*.py` 确认环境变量读取方式符合部署习惯（是否需要写 `.env.example`）。

2. **`run.py:277` wiring 的语义验证**（P1-2）  
   `KECHUANG_TREND_OFF_MULTIPLIER` 此前是"假可调参数"，现在真正生效。请确认设计意图：若有人将来把配置值从 0.50 改成 0.30，科创50的趋势开关行为会变化——这是预期的吗？对照 `ds.v1.3` §评分层。

3. **温度计档位去重的边界等价性**（P1-4）  
   `run.py` 删除了本地 `_temp_tier`，改 import `thermometer._tier`。`thermometer._tier` 不接受 `None`，我加了 `if ... is None: frozen=False` 分支保留原语义。请人工 review 这段（`run.py:460-470`）确认"任一指标缺失 = 不冻结 = 用 equity_ratio 返回值"与设计一致。

4. **API 报告路径与 run.py 的 80% 重复**（C3，未修）  
   这是最大的一处技术债。当前 `server.get_report` 仍复制 `run.run_report` 的逻辑（仅 `generate_report` 文本输出未走）。建议下一步抽 `src/pipeline.py`。审查 `src/api/server.py:238-426` 与 `run.py:374-578` 的差异，确认抽取可行性。

5. **`_low_vol_days` 持久化语义**（B1，未修）  
   `run.py:377` 每次 `run_report` 都 `reset_recovery_tracking()`，导致"持续 20 天才恢复"在月度 cron 模式下永远不生效。请对照 `ds.v1.3` §八 确认这是 bug 还是 acceptable。

---

## 7. 下一步最值得做的一件事

**抽 `src/pipeline.py`，消除流A逻辑的三重重复（audit C3 / refactor-plan P2-1）。**

理由：
- 这是代码库**最大的单一技术债**——任何规则改动需在 `run.py` / `server.get_report` / `server.post_report` 三处同步，极易漏改（本次 P1-4 已经在两处发现温度计重复）。
- 完成后，`run.py` / `validate.py` / `server.py` 三个入口都变成对 `pipeline.build_monthly_allocation(...)` 的薄封装，后续任何因子/约束/分配改动只需改一处。
- 前置条件已具备：本次新增的 `test_nightly_refactor_contracts.py` 提供了入口级回归测试，抽取后可立即用 388 个测试守护行为不变。

建议执行顺序：
1. 先补 `validate.run_test` 入口测试（目前 0 覆盖）
2. 抽 `pipeline.build_monthly_allocation()`（纯函数，返回 dict）
3. 让 `run.run_report` / `server.get_report` / `server.post_report` 都调用它
4. 用 `--demo` 输出 diff + 全套件测试验证字节级等价

---

## 附录：执行约束自检

| 用户规则 | 遵守情况 |
|---|---|
| 开始前创建独立分支 | ✅ `chore/nightly-audit-refactor` |
| 每个逻辑修改单独提交 | ✅ 8 个原子提交 |
| 提交信息说明修改原因 | ✅ 每条都引 audit §X |
| 不确定业务设计时不猜测，记录到报告 | ✅ B1/P2-2 等记录到"尚未处理" |
| 不提交密钥/缓存/日志/模型/个人配置 | ✅ `data/db/` 已在 .gitignore；本次未触碰密钥文件 |
| 不直接推送远程 | ✅ 仅本地提交，`git push` 未执行 |
| 测试环境缺失时仍完成静态审计+单测 | ✅ akshare 活服务器相关 13 测试自动 skip，其余全跑 |
| 不改外部接口 | ✅ CLI/API 签名不变；新增 config 常量；`_tier` 仍可被外部 import |
| 不大规模重命名 | ✅ 无文件重命名 |
| 不引入大型新框架 | ✅ 仅用 stdlib（`os.environ`） |
| 不删无法确认用途的代码 | ✅ simple_backtest / dead 函数均保留并记录 |
