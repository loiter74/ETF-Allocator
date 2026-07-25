# 当前架构（Architecture — Current State）

> 审计日期：2026-07-25  
> 分支：`chore/nightly-audit-refactor`  
> 适用代码版本：`main @ 2799cda`

## 0. 重要前置说明（与目标模板的差异）

用户提供的审计目标模板（第一阶段第 3 项）要求描述 **LLM / TTS / Live2D / WebSocket / Socket.IO** 的连接关系。

**本项目是 ETF 月度新增资金配置系统，不包含上述任何组件。** 该模板来自其他项目（AI 虚拟人/对话系统）的通用审计清单。本文件按实际代码库（Python + FastAPI + React/Vite + SQLite）描述架构，不强行套用不存在概念。后续 `audit-report.md` 第 11、12 项（"inspection/healthcheck/mock 消息误入 LLM 链路"、"persona/memory/message filter/Agent loop 边界"）同理：本项目无 LLM 链路，相关条目将标注为"不适用"，并替换为实际存在的对应风险（如 demo 数据是否误入正式计算链路、`run.py` / API / 前端之间的边界是否清晰）。

---

## 1. 项目概述

ETF 月度新增资金配置系统（v1.3）。每月回答一个问题：**本月新增资金怎么分到 6 个 ETF / 国债**。

- 不预测涨跌，不卖已有仓位
- 每个决策可追溯到因子值和规则
- 核心代码在 `ETF-Allocator/` 子目录

资产池（6 个）：白酒ETF / 银行ETF / 红利ETF / 沪深300ETF / 科创50ETF / 国债ETF。资产名用中文字符串做 key，贯穿所有模块。

---

## 2. 两条独立数据流

### 流 A（运行流 / Runtime）— `run.py report`
每月执行一次：

```
数据更新（AkShare）→ 因子计算 → 机会分评分 → 市场温度计
   → 风险控制 → 组合约束 → 资金分配 → 国债累积池 → 月报
```

### 流 B（验证流 / Backtest）— `validate.py`
离线定期执行：

```
训练期（2015–2021）调参 → SHA-256 锁定参数 → 测试期（2022–2025）只验
   → 年化收益 / 最大回撤 / 夏普 / Calmar
```

---

## 3. 模块职责图

```
ETF-Allocator/
├── run.py                 流A入口（report / rebalance CLI）
├── validate.py            流B入口（train / test CLI）
├── start.py / start.bat   一键启动 API + Dashboard（开发用）
├── config/
│   └── settings.py        【唯一参数源】资产池/因子权重/阈值/约束/回测期
├── src/
│   ├── store/             SQLite 建表 + PIT（point-in-time）校验
│   │   ├── schema.py        DDL（SCHEMA_VERSION=3，含 investment_record）
│   │   ├── validator.py     AntiLookAhead：publish_date 过滤
│   │   └── normalization.py 日期 / 股息率标准化
│   ├── datasource/
│   │   └── akshare_adapter.py  AkShare → DataFrame（PE/PB/价格/指数元信息）
│   ├── factors/
│   │   ├── value.py         PE/PB 分位 + z-score（expanding + truncate）
│   │   ├── dividend.py      股息率分位
│   │   ├── momentum.py      120d 动量 + 200d MA 趋势开关 + 科创50机会分
│   │   └── risk.py          年化波动率 + 最大回撤
│   ├── scoring/
│   │   └── engine.py        因子 → [0,1] 机会分（国债永远 None）
│   ├── regime/
│   │   └── thermometer.py   市场温度计：沪深300PE分位 AND 全APB分位
│   │                        双 > 90% 触发降温；模块级全局 _last_equity_ratio
│   ├── risk/
│   │   └── controller.py    波动率 → 仓位上限调整；模块级 _low_vol_days
│   ├── constraints/
│   │   └── portfolio.py     单资产带 + 因子组（VALUE≤60% / GROWTH≤15%）
│   ├── allocation/
│   │   └── allocator.py     缺口分+机会分混合 → 最终资金分配
│   ├── execution/
│   │   └── bond_liquidity.py BondAccumulator（国债累积池，解决最低买入门槛）
│   ├── backtest/
│   │   ├── engine.py        run_backtest：PIT 回测（最长 489 行）
│   │   ├── splitter.py      训练/测试日期切分
│   │   └── parameter_lock.py 参数 SHA-256 锁定
│   ├── rebalance/
│   │   └── checker.py       年度再平衡（12/1–3 触发，只卖不买）
│   ├── reports/
│   │   └── monthly.py       月报文本生成（generate_report）
│   └── api/
│       └── server.py        FastAPI（/api/report、/api/history、/api/investments、SPA）
├── dashboard/              React 19 + TS + Vite 8 + Tailwind 4
│   └── src/{pages,hooks,components}/  通过 hooks 调用 /api/*
├── scripts/               数据导入（AkShare / Tushare PB）
└── tests/                 pytest（unit + integration + fixtures）
```

---

## 4. 完整调用链（用户输入 → 输出）

### 4.1 CLI 月报（`python run.py report`）
```
main(argv)
  └─ run_report(verbose, demo, weights_override, total_assets_input)
       ├─ reset_recovery_tracking()                  # 清 risk.controller._low_vol_days
       ├─ [demo 分支] _demo_factors() / _demo_weights()
       ├─ [真实分支]
       │    ├─ get_db_connection() → create_tables()
       │    ├─ ensure_etf_seed_data()
       │    ├─ update_data()  → fetch_etf_price/fetch_index_valuation  (try/except 吞错)
       │    └─ calculate_factors()
       │         ├─ load_price_series / load_valuation_series
       │         ├─ pe_percentile / pb_percentile / compute_zscore    (value.py)
       │         ├─ dividend_yield_percentile                         (dividend.py)
       │         ├─ momentum_120d / ma_trend_200d / kechuang_opportunity (momentum.py)
       │         └─ annualized_volatility / max_drawdown              (risk.py)
       ├─ score_all(factors)                          # scoring.engine
       ├─ load_persistence(regime_state.json)
       │   equity_ratio(hs300_pe_pct, all_a_pb_pct)   # 改全局 _last_equity_ratio
       │   save_persistence()
       ├─ all_effective_limits(volatilities)          # risk.controller
       ├─ apply_constraints(current_weights, limits)  # constraints.portfolio
       ├─ allocate(scores, weights, limits, ...)      # allocation.allocator
       ├─ BondAccumulator.load → deposit → accrue_interest → execute → save
       └─ generate_report(...)                        # reports.monthly → 打印到 stdout
```

### 4.2 API 调用（`GET /api/report`）
```
浏览器 (React useDashboardData hook)
  → GET /api/report?total_assets=...&current_weights=...
     → server.get_report
          ├─ _import_run_functions()   # 每请求 from run import ...（动态导入）
          ├─ 重复 run_report 内 80% 逻辑（不走 run.run_report，而是复制粘贴）
          │    calculate_factors / score_all / equity_ratio / all_effective_limits
          │    / apply_constraints / allocate / BondAccumulator.load（只读投影）
          └─ 返回 JSON（不调用 generate_report，自建 JSON 结构）
```

### 4.3 回测（`python validate.py test`）
```
run_test()
  ├─ verify_snapshot(PARAMETER_LOCK_PATH)   # SHA-256 校验参数锁定
  └─ run_backtest(conn, mode="test")        # backtest.engine
       └─ 逐月迭代（_monthly_dates）
            ├─ get_available_valuations/prices   # PIT 过滤
            ├─ （同流A的 因子→评分→温度计→风险→约束→分配→国债）
            └─ 累计 portfolio_values → compute_metrics（年化/MDD/夏普/Calmar）
```

---

## 5. 输入 / 输出契约

| 模块 | 输入 | 输出 |
|---|---|---|
| `run.py:run_report` | `demo`, `weights_override`, `total_assets_input` | 月报字符串（stdout）+ 副作用：写 `regime_state.json` / `bond_accumulator.json` |
| `validate.py:run_test` | 无（读 DB + 锁文件） | 指标 dict + 打印 |
| `scoring.engine.score_all` | `factors: Dict[str, Dict]` | `Dict[str, Optional[float]]`（国债=None） |
| `regime.thermometer.equity_ratio` | `(p1: float, p2: float)` | `(equity_ratio, bond_ratio)` + **副作用**：改全局状态 |
| `risk.controller.all_effective_limits` | `Dict[资产, vol]` | `Dict[资产, 上限]` + **副作用**：改 `_low_vol_days` |
| `allocation.allocator.allocate` | scores/weights/limits/total/budget | `Dict[资产, 金额]` |
| `api.server.get_report` | Query: total_assets, current_weights | JSON 报告 |
| `reports.monthly.generate_report` | temp_result/factors/scores/... | 月报字符串 |

---

## 6. 状态存储位置

| 状态 | 位置 | 作用域 |
|---|---|---|
| SQLite 主库 | `ETF-Allocator/data/db/etf_data.db` | 持久（价格/估值/因子/投资记录） |
| 温度计状态 | `data/db/regime_state.json`（`_last_equity_ratio`） | 跨月持久化 |
| 国债累积池 | `data/db/bond_accumulator.json`（BondAccumulator） | 跨月持久化 |
| 参数锁 | `data/db/locked_parameters.json`（SHA-256） | 训练→测试锁定 |
| 风险恢复计数 | `risk.controller._low_vol_days`（**仅内存**） | **进程内**，每次 `run_report` 被 reset — 见 audit §7 |
| AkShare 请求 | 无缓存 | 每次全量拉取 |

---

## 7. 主要依赖

### Python（`pyproject.toml`）
- `akshare>=1.12.0` — 行情/估值数据源
- `pandas>=2.0`, `numpy>=1.24` — 因子计算
- `fastapi>=0.100`, `uvicorn>=0.30` — API
- 测试：`pytest`, `pytest-cov`

**未声明但代码中 import**：`tushare`（scripts/）、`requests`（scripts/ + tests/integration/test_api.py）、`pydantic`（经 fastapi 传递依赖，server.py 直接 import）。

### 前端（`dashboard/package.json`）
- React 19 / react-router-dom / Recharts / Framer Motion / Tailwind 4 / KaTeX
- `clsx` + `tailwind-merge`（样式合并）
- **声明但未用**：`sonner`, `lucide-react`, `@nivo/treemap`，`react-grid-layout`（实际页面用 CSS grid）

---

## 8. 前后端连接关系

```
┌──────────────────────────┐         HTTP (JSON)          ┌─────────────────────────┐
│  React Dashboard (5173)  │  ─────────────────────────>  │  FastAPI server (8000)  │
│  ──────────────────────  │                               │  ─────────────────────  │
│  hooks/useReport         │   /api/report (GET/POST)     │  get_report / post_report│
│  hooks/useDashboardData  │   /api/history?index=&field= │  get_history             │
│  hooks/useHistory        │   /api/history               │                          │
│  hooks/useInvestmentRecords │ /api/investments (CRUD)   │  investment handlers     │
│  pages/AiriDashboard     │   ⚠ 还有一处内联 fetch       │                          │
│                          │     /api/history (违反规约)   │  SPA fallback (dist/)    │
└──────────────────────────┘                              └────────────┬────────────┘
                                                                        │
                                                           直接调用 src/* 模块
                                                                        ▼
                                                           SQLite (etf_data.db)
                                                           JSON 状态文件
```

开发期通过 `dashboard/vite.config.ts` 把 `/api` 代理到 `localhost:8000`。生产期 FastAPI 直接托管 `dashboard/dist/`（SPA fallback，server.py:598）。

**无 WebSocket / Socket.IO** — 所有交互均为 HTTP 请求-响应，部分前端 hook 有 10s 轮询。

---

## 9. 数据流的关键不变量（来自 AGENTS.md / ds.v1.3）

1. **防未来函数**：所有分位用 expanding window（`_expand_truncate` 截断到 N 年），回测估值必须 `publish_date` 过滤。
2. **后复权价**：`etf_price.close_adj`。
3. **风险不进评分**：波动率高 → 降仓位上限，不影响机会分。
4. **参数集中**：`config/settings.py` 是唯一参数源（实际有少量例外，见 audit-report）。
5. **测试期不可调参**：流 B 测试期只验不调。
6. **温度计双指标 AND**：沪深300 PE 分位 AND 全A PB 分位，双 > 90% 才触发降温。
7. **国债是吸收口**：温度计强制债比例 + 分配溢出都进国债。
8. **趋势开关 OFF ≠ 归零**：减半（×0.50）保留反转参与权。
