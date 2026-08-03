# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

ETF 月度新增资金配置＋低频风险再平衡系统（V2 候选，保留 v1.3 兼容入口）。每月用新增资金纠偏；卖出只处理战略硬上限、年度软带和科创50专属保护。每个决策可追溯到因子值、状态和规则。

核心代码在 `ETF-Allocator/` 子目录下。

> 权威架构地图见 `docs/architecture-current.md`（更新日期 2026-08-02，含 v1.3 兼容流与 V2 strategy 模块）；设计哲学与硬性约束见根目录 `README.md`。改架构前先读这两份。

## Commands

```bash
# 月度报告（流A，v1.3 兼容入口：仅分配新增资金，无卖出能力）
python ETF-Allocator/run.py report --demo          # 演示模式，无需真实数据
python ETF-Allocator/run.py report --weights '{"白酒ETF":0.12,...}' --total 200000

# 完整快照交易计划（V2 入口：含三阶段补仓、战略硬上限卖出、科创影子单）
python ETF-Allocator/run.py plan --snapshot snapshot.json   # 只读预览 TradePlan

# 回测验证（流B）
python ETF-Allocator/validate.py train              # 训练期（调参）
python ETF-Allocator/validate.py test               # 测试期（锁死参数验证）
python ETF-Allocator/validate.py sensitivity        # 预注册敏感性网格（仅看稳健性，不挑参数）

# 年度再平衡检查
python ETF-Allocator/run.py rebalance

# 一键启动前后端（FastAPI + Vite）— 必须用子agent启动，见 Critical Rules
ETF-Allocator/start.bat                             # API :8000, Dashboard :5173

# 测试
pytest ETF-Allocator/tests/ -v                      # 全部
pytest ETF-Allocator/tests/unit/test_scoring.py -v  # 单文件
pytest ETF-Allocator/tests/ -v -k "test_regime"     # 按关键词

# 前端
cd ETF-Allocator/dashboard && npm run dev            # 开发
cd ETF-Allocator/dashboard && npm run build          # 构建

# 数据导入脚本
python ETF-Allocator/scripts/import_data.py          # 批量拉取（AkShare，腾讯API）
python ETF-Allocator/scripts/tushare_import.py       # 主数据补全脚本（PB/DY 成分股加权）
```

## API 端点（V2）

| 端点 | 用途 | 副作用 |
|---|---|---|
| `GET /api/report` | v1.3 旧报告，模拟只读 | 无 |
| `POST /api/report` | v1.3 带参数报告 | 无 |
| `POST /api/trade-plan/preview` | **V2 完整快照只读预览**（TradePlan） | 无（内存计算）|
| `POST /api/trade-plan/confirm` | **显式确认**月度观察/真实卖出 | **写**快照+成交+科创状态 |
| `GET/POST /api/portfolio-snapshot/ocr-config` / `parse-text` | 券商截图 OCR 自动填充 | 无（仅结构化文字）|
| `GET /api/history` | PIT 历史估值序列 | 无 |

**预览/GET/报告模拟均不得更新任何状态**；只有 `trade-plan/confirm` 会持久化。

## Architecture: Two Independent Flows

**流A（运行流）** — 每月执行，有两个入口：
- `run.py report`（v1.3 兼容）：数据更新 → 因子 → 机会分 → 温度计 → 风险 → 约束 → 资金分配 → 国债累积池 → 月报。**只分配新钱，不卖**。
- `run.py plan`（V2 完整）：完整券商快照 → 校验/复算总资产 → 非白名单告警 → 因子/温度计/风险上限 → **先正式卖出+科创影子卖出** → 三阶段买入（下限修复→目标补齐→高机会扩展）→ 现金轧差 → `TradePlan`

**流B（验证流）** — `validate.py`，离线定期跑：
训练期调参 → 锁死 → 测试期只验 → 四策略并列回测（V1.3/静态年度/新策略不含利润保护/完整策略）→ 指标（年化/最大回撤/夏普/Calmar）

## Key Modules (`ETF-Allocator/src/`)

| 模块 | 职责 | 关键文件 |
|---|---|---|
| `store/` | SQLite 建表 + AntiLookAhead 校验 | `schema.py`, `validator.py` |
| `datasource/` | AkShare 适配器 | `akshare_adapter.py` |
| `factors/` | PE/PB 分位、股息率、动量、波动率 | `value.py`, `dividend.py`, `momentum.py`, `risk.py` |
| `scoring/` | 因子 → [0,1] 机会分 | `engine.py` |
| `regime/` | 市场温度计（双指标 AND） | `thermometer.py` |
| `risk/` | 波动率 → 仓位上限调整 | `controller.py` |
| `constraints/` | 单资产 + 因子组约束 | `portfolio.py` |
| `allocation/` | 资金分配（缺口分+机会分混合） | `allocator.py` |
| `execution/` | 国债虚拟累积池（v1.3 新增，解决 511010 最低买入门槛） | `bond_liquidity.py` |
| `strategy/` | 完整快照、共享买卖计划、科创影子状态和确认持久化 | `models.py`, `planner.py`, `kechuang.py`, `repository.py` |
| `backtest/` | point-in-time 回测引擎 | `engine.py`, `splitter.py` |
| `reports/` | 月报文本生成 | `monthly.py` |
| `rebalance/` | 年度再平衡检查 | `checker.py` |
| `api/` | FastAPI 后端 | `server.py` |

**所有可调参数**集中在 `config/settings.py`：资产池、因子权重、温度计阈值、风险控制参数、约束带、分配权重、回测期间。模块内部不硬编码阈值。

## Critical Rules

1. **防未来函数**：所有分位用 expanding window（`_expand_truncate` 截断到 N 年），严禁全历史分位。回测估值数据必须带 `publish_date` 过滤。
2. **后复权价**：`etf_price.close_adj`，分红正确再投资。
3. **风险不进评分**：波动率高 → 降仓位上限，不影响机会分。两者逻辑分开。
4. **参数集中**：`config/settings.py` 是唯一参数来源。
5. **测试期不可调参**：流 B 的测试期只验不调，严禁"看着回测结果回头改参数"。
6. **服务启动必须用子 agent**：启动前后端服务时，必须单独启动一个子 agent，严禁主 agent 直接启动后端或前端服务（会导致主 agent 卡死无响应）。

   子 agent 启动协议（成功判定 = 端口监听 + API 返回 200，不依赖进程退出）：
   ```bash
   # Step 1: 清理旧进程
   for /f "tokens=5" %a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do taskkill /F /PID %a 2>nul
   for /f "tokens=5" %a in ('netstat -ano ^| findstr ":5173.*LISTENING"') do taskkill /F /PID %a 2>nul

   # Step 2: 后台启动后端（不阻塞）
   cmd /c start /b python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000

   # Step 3: 轮询后端直到就绪
   :wait_backend
   curl -s http://localhost:8000/api/report?demo=true >nul 2>&1 && goto start_frontend
   sleep 2 && goto wait_backend

   # Step 4: 后台启动前端
   :start_frontend
   cmd /c start /b npm.cmd run dev

   # Step 5: 轮询前端直到就绪
   :wait_frontend
   curl -s http://localhost:5173 >nul 2>&1 && goto success
   sleep 2 && goto wait_frontend

   # Step 6: 报告成功
   :success
   echo "SUCCESS: Backend :8000 OK, Frontend :5173 OK"
   ```
   ⚠️ 子 agent 必须持续检查自己是否卡死（超过 60s 无进展 → 报告失败），主 agent 也应定期检查子 agent 状态。
7. **QA 测试必须重新获取数据**：启动测试步骤时，必须使用 `qa` skill 并结合 `playwright` 技能进行页面捕获和验证。**严禁复用上一次 playwright 的缓存结果**，每次测试前必须重新获取最新测试数据。
8. **设计文档权威来源**：设计哲学与硬性约束以根目录 `README.md` 为准；当前架构现状（含 v1.3 兼容入口与 V2 strategy 模块）以 `docs/architecture-current.md` 为准。任何实现必须可追溯到这两份文档中的具体章节。

## Design Workflow

**Brainstorming → OpenSpec Propose**：所有设计讨论完成后，使用 `/opsx:propose` 创建 OpenSpec change（包含 proposal.md、design.md、specs/、tasks.md），不要写独立的 spec 文档到 `docs/superpowers/specs/`。OpenSpec artifacts 存放在 `openspec/changes/<name>/`，是唯一的设计-实现桥梁。

## Conventions

- 资产名用中文字符串做 key（`"白酒ETF"`, `"科创50ETF"`），贯穿所有模块
- 机会分统一 `[0,1]`，国债永远 `None`（不参与评分）
- 温度计：沪深300 PE 分位 AND 全A PB 分位，双指标同档时分别给 100%/70%/40%/30% 权益比例；档位不一致或数据缺失时冻结上期已确认比例（详见 README §2.1）
- 因子组约束：VALUE 组（白酒+银行+红利）上限 60%，沪深300 独立为 CORE 上限 30%，GROWTH（科创50）上限 15%（见 `GROUP_CAPS`）
- 防御桶（国债ETF＋累积池＋逆回购）上限 20%；达 20% 后停止新增固收，溢出标记为权益待投现金，不得自动改投国债
- 完整快照预览必须无副作用；只有显式幂等确认（`POST /api/trade-plan/confirm`）才写月度快照、成交和科创状态
- 科创利润保护默认 `shadow`，未通过参数锁版本升级不得生成正式卖单
- 趋势开关 OFF ≠ 归零，减半（乘以 0.50）保留反转参与权
- 全局状态模块变量（温度计持久化 `_last_equity_ratio`、波动率恢复 `_low_vol_days`）：测试后需 `reset_persistence()` / `reset_recovery_tracking()`
- 国债虚拟累积池（`execution/BondAccumulator`）跨月状态走 JSON 文件持久化（`save`/`load`，路径在 settings），不是模块变量；测试时直接 new 一个空实例，别误读旧状态文件

## Frontend

`dashboard/` 是 React 19 + TypeScript + Vite 8 + Tailwind 4 应用，通过 `src/api/server.py` FastAPI 后端获取数据。
首页"盈利收获与交易计划"走 V2 完整快照预览（`/api/trade-plan/preview`），支持券商截图 OCR 自动填充（Tesseract.js 本地 OCR + 可选 DeepSeek 结构化）。
**页面扫描本身不确认观察、不写策略状态、不执行交易** —— 只有用户显式确认才推进状态。
详见 `ETF-Allocator/dashboard/AGENTS.md`。

## Data

SQLite 数据库在 `ETF-Allocator/data/db/etf_data.db`，首次运行自动创建（schema v4）。

- **PIT 数据表**（v1.3）：`etf_info`, `index_info`, `etf_price`, `index_valuation`, `etf_factor`
- **V2 确认审计表**：`portfolio_snapshot` / `portfolio_snapshot_item`（月度券商快照）、`strategy_state`（科创状态机）、`trade_plan_confirmation` / `trade_fill`（幂等确认+真实成交）

## AGENTS.md Hierarchy

```
./AGENTS.md                          # 项目总览（本文件）
ETF-Allocator/AGENTS.md              # ETF-Allocator 核心系统
├── src/backtest/AGENTS.md           # 回测引擎（流B）
├── src/factors/AGENTS.md            # 因子计算
├── tests/AGENTS.md                  # 测试
├── dashboard/AGENTS.md              # 前端 Dashboard
└── scripts/AGENTS.md                # 数据导入脚本
```
