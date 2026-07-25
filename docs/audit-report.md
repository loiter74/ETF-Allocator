# 工程审计报告（Engineering Audit Report）

> 审计日期：2026-07-25  
> 分支：`chore/nightly-audit-refactor`  
> 范围：`ETF-Allocator/` 全部 Python + 前端代码  
> 说明：本项目无 LLM/TTS/Live2D/WebSocket 组件（详见 architecture-current.md §0）。模板第 11、12 项已按实际代码库重映射。

风险等级：**P0 = 安全/数据正确性**，**P1 = 明显结构问题**，**P2 = 需设计决策**，**P3 = 暂不建议处理**。

---

## A. 安全 / 密钥（P0）

### A1. Tushare Token 硬编码并提交到仓库（密钥泄露）
- **问题**：Tushare Pro API token 以明文常量写在 5 个脚本里，并已进入 git 历史。
- **位置**：
  - `ETF-Allocator/scripts/import_pb.py:10`
  - `ETF-Allocator/scripts/import_pb_all.py:14`
  - `ETF-Allocator/scripts/import_pb_one.py:11`
  - `ETF-Allocator/scripts/auto_import_pb.py:14`
  - `ETF-Allocator/scripts/tushare_import.py:34`
  - 值：`REDACTED_TUSHARE_TOKEN`
- **风险**：P0 — 已泄露的 token 可被滥用拉数据 / 触发 Tushare 配额计费，且永久留在 git 历史里。
- **产生原因**：早期为方便调试硬编码；无 secret 管理规范。
- **推荐修改**：改为 `os.environ["TUSHARE_TOKEN"]`，缺失时报错退出；在 README 增补说明；**人工轮换该 token**（agent 不应也不能完成轮换）。
- **是否适合自动修改**：**是**（代码侧），git 历史清理与 token 轮换需人工。

### A2. CORS 全开
- **问题**：FastAPI `allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]`。
- **位置**：`src/api/server.py:38`
- **风险**：P1 — 部署到公网后任意站点可调用 API（投资记录 CRUD 可被 CSRF 触发）。
- **产生原因**：开发期为方便前端跨域。
- **推荐修改**：用环境变量配置白名单（默认 `http://localhost:5173`）。
- **是否适合自动修改**：是（P1 候选）。

---

## B. 数据正确性 / 隐式状态（P0/P1）

### B1. 风险恢复计数器 `_low_vol_days` 不跨进程持久化（与设计语义冲突）
- **问题**：`risk.controller._low_vol_days` 是模块级 dict，`run_report` 每次启动都调用 `reset_recovery_tracking()` 清空。设计文档说"持续 20 个交易日才恢复上限"，但月度 cron 每次都是新进程，计数器永远到不了 20。
- **位置**：`src/risk/controller.py:15-16, 19-65`，`run.py:377`
- **风险**：P1（实际表现 = 高波动资产一旦触发，月度运行维度内永远降上限；可能偏保守但与文档不一致）。
- **产生原因**：温度计有 JSON 持久化，风险层没有。
- **推荐修改**：与温度计同样持久化 `_low_vol_days` 到 JSON，跨月加载。**需设计决策**（实际行为是否已 acceptable？）→ 记录，不在自动修改范围。
- **是否适合自动修改**：否（需先与设计文档对齐）。

### B2. 数据更新失败被静默吞掉
- **问题**：`update_data()` 用 `try/except Exception` 包裹，捕获后仅 `print` 一行警告就继续。
- **位置**：`run.py:407-411`
- **风险**：P1 — AkShare 挂了 / 改字段 / 网络断了，系统会用旧 DB 数据当"本月最新"出报告，用户察觉不到。
- **产生原因**：避免崩溃影响演示模式。
- **推荐修改**：非 demo 模式下捕获后重新抛出或显式记录；demo 模式提前分流（已经是 `if demo` 分支外）。
- **是否适合自动修改**：是（但需谨慎，避免改外部行为）→ 列入 P1 候选但**不自动改**，仅记录。

### B3. `_RECOVERY_DAYS = 20` 未进 config（违反"参数集中"原则）
- **位置**：`src/risk/controller.py:16`
- **风险**：P1 — 唯一一个未进 `settings.py` 的可调阈值。
- **推荐修改**：移入 `settings.py`（如 `RISK_RECOVERY_DAYS = 20`）。
- **是否适合自动修改**：是（P1 候选）。

### B4. AkShare 适配器多处裸 `except Exception` 返回空 DataFrame
- **位置**：`src/datasource/akshare_adapter.py:76, 100, 116-118, 166-168`
- **风险**：P1 — 网络故障 / 接口变更被静默成"无数据"，下游无法区分。
- **推荐修改**：抛出更具体的异常或返回哨兵值；至少 `logging.warning`。
- **是否适合自动修改**：部分（最小改动 = 加 logging；改语义需设计决策）。

---

## C. 重复代码 / DRY 违反（P1）

### C1. 温度计档位逻辑三处重复
- **问题**：`run.py:458-468` 的 `_temp_tier` + `labels` 字典与 `thermometer.py:_tier` (line 27-39) + `TEMP_THRESHOLDS` 重复。阈值 `0.60/0.80/0.90` 在两处硬编码，且 `reports/monthly.py:18-24` 第三处又写了一遍（顺序倒着 `0.90/0.80/0.60`）。
- **位置**：`run.py:458-469`、`src/regime/thermometer.py:27-39`、`src/reports/monthly.py:18-24`
- **风险**：P1 — 改任一处其他不会跟，温度计行为会漂移。
- **推荐修改**：所有地方从 `settings.TEMP_THRESHOLDS` / `TEMP_EQUITY_RATIOS` 读取，删除重复函数。
- **是否适合自动修改**：是（P1 候选，但需谨慎）。

### C2. 科创50动量历史构造循环重复
- **问题**：`momentum.py:77-89` 和 `backtest/engine.py:159-169` 有逐月构造动量序列的近乎逐字符相同循环。
- **位置**：`src/factors/momentum.py:77-89`、`src/backtest/engine.py:159-169`
- **风险**：P1 — bug 修复需两处同步。
- **推荐修改**：在 `momentum.py` 暴露 `kechuang_opportunity` 已有版本，回测引擎调用它。
- **是否适合自动修改**：否（涉及回测精确行为，列 P2）。

### C3. `run.py` 与 `api/server.py` 的报告逻辑 80% 重复
- **问题**：`server.py:get_report` (232-426) 和 `post_report` (430-543) 把 `run.run_report` 的 因子→评分→温度→风险→约束→分配→国债 整条链又写了一遍（且 GET/POST 之间还互相重复）。`run.py` 的 `generate_report` 文本输出在 API 路径根本没被调用。
- **位置**：`src/api/server.py:232-543`、`run.py:374-578`
- **风险**：P1 — 任何规则改动需在 3 处（run / GET / POST）同步，极易漏改。
- **推荐修改**：抽取共享 `build_report_payload(...)` 函数，三个入口都调用它。
- **是否适合自动修改**：否（重构面大，列 P2 重大决策）。

### C4. `NEW_MONEY=8000` / `DEFAULT_TOTAL=500000` 三处硬编码
- **位置**：`run.py:378-379`、`src/api/server.py:41-42`、`reports/monthly.py`（间接）
- **风险**：P2 — 不一致风险（如 `run_rebalance_check` 又用 `100_000`，`run.py:592`）。
- **推荐修改**：移入 `settings.py`（`DEFAULT_NEW_MONEY` / `DEFAULT_TOTAL_ASSETS`）。
- **是否适合自动修改**：是（P1 候选）。

### C5. 单元 NAV 构造逻辑两份
- **问题**：`compute_metrics` 内联重建 NAV（engine.py:240），`_nav_from_returns` (engine.py:270-277) 也做同样事。
- **位置**：`src/backtest/engine.py:240, 270-277`
- **风险**：P2 — 回测指标计算口径漂移风险。
- **推荐修改**：`compute_metrics` 调用 `_nav_from_returns`。
- **是否适合自动修改**：是（P1 候选，回测有 `test_backtest_pipeline.py` 守护）。

---

## D. 无效 / 死代码（P1/P2）

### D1. `validate.py:simple_backtest` ~158 行死代码
- **位置**：`ETF-Allocator/validate.py:81-239`
- **风险**：P2 — 主流程走 `run_backtest`；这段独立 backtest 含自己的指标计算（192-228），易被误读为活路径。
- **推荐修改**：删除或加 `# DEPRECATED` 注释。
- **是否适合自动修改**：否（无法 100% 确认无外部调用）→ P2 记录。

### D2. `KECHUANG_TREND_OFF_MULTIPLIER` 配置项未使用
- **问题**：`settings.py:78` 定义了 `= 0.50`，但 `run.py:277` 和 `momentum.py:85` 直接硬编码 `0.50`，配置项从未被 import。
- **位置**：`config/settings.py:78`、`run.py:277`、`src/factors/momentum.py:85`
- **风险**：P1 — 改配置不生效（虚假的可调参数）。
- **推荐修改**：两处硬编码改为读 `KECHUANG_TREND_OFF_MULTIPLIER`。
- **是否适合自动修改**：是（P1 候选）。

### D3. `store.validator.validate_publish_date_not_future` 无调用方
- **位置**：`src/store/validator.py:15-26`
- **风险**：P3 — 看起来像设计预留 API。
- **推荐修改**：保留，加注释说明用途。
- **是否适合自动修改**：否。

### D4. `constraints.check_factor_group_constraint` 未被主流程调用
- **问题**：`apply_constraints` 只算 `buy_coefficients`/`max_buy`/`group_caps`，但 `check_factor_group_constraint`（含 scale-down 逻辑）从未被 `run_backtest` 或 `run_report` 调用。约束实际生效靠 allocator 内部的 `_apply_group_constraint`。
- **位置**：`src/constraints/portfolio.py:80-147`
- **风险**：P2 — 两套 group 约束实现，可能行为不一致。
- **推荐修改**：明确单一权威实现，删除另一套。
- **是否适合自动修改**：否（需设计决策）→ P2。

### D5. 前端未用依赖（4 个）
- **位置**：`dashboard/package.json`：`sonner`, `lucide-react`, `@nivo/treemap`, `react-grid-layout`
- **风险**：P3 — 增大 `node_modules` / 构建扫描面。
- **推荐修改**：逐个确认后从 package.json 移除。
- **是否适合自动修改**：否（需逐个验证无引用）。

---

## E. 过长函数 / 过大类（P2）

| 位置 | 行数 | 问题 |
|---|---|---|
| `run.py:run_report` | ~205 行 | 数据/因子/温度/风险/约束/分配/国债/报告全揉在一起 |
| `run.py:calculate_factors` | ~84 行 | 每资产 `if name == ...` 分支 |
| `backtest/engine.py:run_backtest` | ~205 行 | 同 run_report 在回测里的镜像 |
| `validate.py:simple_backtest` | ~158 行 | 且为死代码 |
| `constraints._apply_group_constraint` | ~62 行 | 边界 |
| `api/server.get_report` | ~195 行 | 且与 post_report / run.py 三重重复 |

**推荐**：P2，分阶段抽取 `pipeline.py`（流A核心步骤），让 `run.py` / `validate.py` / `server.py` 都调它。不在本次自动修改范围。

---

## F. 配置散落 / 硬编码（P1）

| 字面量 | 位置 | 应去 |
|---|---|---|
| `0.60/0.80/0.90` 温度阈值 | `run.py:461-465`, `reports/monthly.py:18-24` | `settings.TEMP_THRESHOLDS` |
| `8_000` / `500_000` | `run.py:378-379`, `server.py:41-42` | 新增 `DEFAULT_NEW_MONEY` / `DEFAULT_TOTAL_ASSETS` |
| `_RECOVERY_DAYS = 20` | `risk/controller.py:16` | 新增 `RISK_RECOVERY_DAYS` |
| `KECHUANG_TREND_OFF_MULTIPLIER` 实际值 `0.50` | `run.py:277`, `momentum.py:85` | 已存在配置，需 wiring |
| `ALL_MARKET_INDEX = "000985"` | `backtest/engine.py:51` | 新增 `ALL_MARKET_INDEX_CODE` |
| `PE < 500`, `PB < 50` 截断 | `factors/value.py:78, 96` | 新增 `PE_MAX_VALID` / `PB_MAX_VALID` |
| `14000`（最低买入）回退 | `reports/monthly.py:177` | 已存在 `BOND_MIN_PURCHASE` |
| 资产名硬编码 | `reports/monthly.py:207`, `store/schema.py:78-79` CHECK | `settings.ASSETS.keys()` |
| `localhost:8000` | `dashboard/vite.config.ts:16` | 仅开发用，保留 |
| 前端 `BASE='/api'` 重复 3 处 | hooks/* | 抽 `lib/api.ts`（P2） |

---

## G. 异常处理缺失（P1/P2）

| 位置 | 问题 |
|---|---|
| `api/server.get_report` / `post_report` / `get_history` | 无 try/except，`run.py` import 错 / `BondAccumulator.load` 失败 → 未捕获 500 |
| `datasource.akshare_adapter.py:76,100,116-118,166-168` | 裸 `except Exception` → 空 DataFrame |
| `execution/bond_liquidity.py:125` | `except (JSONDecodeError, KeyError): pass` — 文件损坏静默成空状态 |
| `run.py:407-411` | 数据更新失败被吞 |
| `risk/controller.effective_upper_limit` | 无 vol 符号/范围校验 |

---

## H. 日志（P1）

- **问题**：整个 `src/`、`run.py`、`validate.py`、`scripts/` **完全没用 `logging` 模块**。所有诊断输出靠 `print()` 和返回 `None`。
- **位置**：全部
- **风险**：P1 — 服务器/回测出问题无法定位（无时间戳、无级别、无文件）。
- **推荐修改**：引入 `logging.getLogger(__name__)`，按模块替换 `print`。最低限度：先在 `api/server.py`、`run.py`、`akshare_adapter.py` 加 logger。
- **是否适合自动修改**：部分（最小风险 = 在 akshare_adapter 的 except 里加 `logger.warning`）。

---

## I. 测试覆盖薄弱（P1）

### 完全无测试的核心入口
- **`run.py`（流A CLI）**：没有任何测试 import `run.main` / `run.run_report` / `run._demo_factors`。`--demo` 分支从未被自动验证。
- **`validate.py`（流B CLI）**：`tests/` 中 grep `validate` 零结果。train/test 入口完全未测。
- **`api.server.post_report`**：无进程内单元测试。
- **`api.server.get_history`**：仅 `test_api.py`（跳过型，需活服务器）覆盖。
- **`rebalance/checker.py`**：无独立测试文件（仅 `test_backtest_pipeline.py:404-450` 间接调到）。
- **`datasource.akshare_adapter`**：`test_datasource.py` 发真实网络请求 → CI 上必失败/跳过，等于无单测。

### 用户目标第 5 阶段要求补的"核心链路测试"映射
| 模板要求 | 本项目对应 | 当前覆盖 |
|---|---|---|
| 普通聊天消息 | 月度报告正常路径（`run.run_report` 真实分支） | **0** |
| inspection ping | API `/api/report` 可达性 | **跳过型** test_api.py |
| healthcheck | 无 `/api/health` 端点 | **0** |
| 空消息/非法 payload | `post_report` / investment 非法输入 | investment 有；report 无 |
| LLM 调用失败 | AkShare 拉数失败时系统行为 | **0**（且被吞掉） |
| TTS 调用失败 | 国债执行失败时行为 | 部分（`test_bond_liquidity.py`） |
| persona drift 检测 | 不适用（无 LLM） | n/a |

---

## J. inspection / healthcheck / mock 链路风险（模板第 11 项重映射）

### J1. demo 数据路径在正式模块内
- **问题**：`run.py` 的 `--demo` 分支（`_demo_factors` / `_demo_weights`）写在正式入口里，`api/server.py` 通过 `from run import ...` 把整个 run 模块拉进请求热路径。如果未来不小心让 `demo=True` 流入 server 调用，会用假数据出"真"报告。
- **位置**：`run.py:347-395`、`src/api/server.py:216 (_import_run_functions)`
- **风险**：P1 — 当前 server 没传 demo，但耦合度高。
- **推荐**：将 demo 数据隔离到 `tests/fixtures/` 或 `scripts/`，正式模块不持有 mock。
- **是否适合自动修改**：否（边界改动需设计决策）→ P2。

### J2. 无独立 healthcheck 端点
- **问题**：前端 liveness 探活只能打 `/api/report`（重计算），无法区分"进程活着"和"DB/数据源正常"。
- **位置**：`src/api/server.py`（缺失）
- **推荐**：新增 `GET /api/health`（仅返回 `{ok:true}` 或带 DB ping）。
- **是否适合自动修改**：是（P1 候选，纯增量）。

---

## K. 模块边界（模板第 12 项重映射）

模板的 persona/memory/message filter/Agent loop → 本项目对应：

| 模板概念 | 本项目映射 | 边界是否清晰 |
|---|---|---|
| persona | 资产配置"风格"（防御/平衡）— 隐含在温度计 + 约束里 | **不清晰**：风格没显式抽象，散在阈值里 |
| memory | `regime_state.json` + `bond_accumulator.json` + `_low_vol_days` | **部分清晰**：温度计/国债有持久化，风险层没有（B1） |
| message filter | 因子→机会分的转换 + 国债永远 None 的特殊处理 | **清晰**（scoring.engine 集中） |
| Agent loop | 流A 9 步流水线 | **不清晰**：流水线在 run.py / validate.py / server.py 三处复制（C3） |

---

## L. 循环依赖 / 架构耦合（P2）

- **API → run.py**：`server.py` 每请求 `from run import ...`，而 `run.py` 是 CLI 模块（有 `sys.path.insert`、模块级副作用）。方向反了——应 `run.py` 调 `src/`，`server.py` 也调 `src/`，两者平级。
- **store/schema.py → 资产名硬编码**：CHECK 约束里写死 6 个中文名，与 `config/settings.ASSETS` 重复定义"资产池"真相。
- 未发现 Python 层循环 import（`src/*` 子包之间无环）。

---

## M. 审计结论汇总（按风险等级）

| 等级 | 数量 | 是否自动修改 |
|---|---|---|
| P0 | 1（A1 密钥，代码侧自动 / 轮换人工） | 部分 |
| P1 | ~12 | 选 ≤5 个最低风险者自动改 |
| P2 | ~7 | 仅记录 |
| P3 | 3 | 仅记录 |

**最值得立即处理的 5 项**（按 ROI）：
1. A1 密钥改环境变量（P0，代码侧）
2. C1 温度计档位去重（P1，行为正确性）
3. D2 `KECHUANG_TREND_OFF_MULTIPLIER` wiring（P1，虚假配置）
4. B3 `_RECOVERY_DAYS` 进 config（P1，参数集中原则）
5. C4 `NEW_MONEY` / `DEFAULT_TOTAL` 进 config（P1，去重）
