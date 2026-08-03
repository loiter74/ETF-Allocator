# 当前架构（Architecture — V2 Candidate State）

> 更新日期：2026-08-02
>
> 适用状态：V1.3 兼容报告＋V2 完整快照交易计划候选

## 0. 迁移状态

- `run.py report`、`GET/POST /api/report` 和 `allocation.allocator` 保留 V1.3 权重输入兼容；该模式没有真实份额和成本，因此只能分配新增资金，不能生成卖单。
- V2 完整能力由 `src/strategy/` 提供，入口为 `run.py plan`、Dashboard“盈利收获与交易计划”、`POST /api/trade-plan/preview`、`POST /api/trade-plan/confirm` 和卖出感知回测。
- 核心规则处于代码候选阶段；科创50利润保护由锁定配置强制为 `shadow`，只有后续新参数锁版本可转 `live`。

---

## 1. 项目概述

ETF 月度新增资金配置＋低频风险再平衡系统。每月回答两个有先后顺序的问题：**是否命中有限卖出规则；可用新增资金和真实卖出净收入如何分到 6 个 ETF / 国债。**

- 不预测涨跌；卖出只处理战略硬上限、年度明显漂移和科创专属保护
- 每个决策可追溯到因子值和规则
- 核心代码在 `ETF-Allocator/` 子目录

资产池（6 个）：白酒ETF / 银行ETF / 红利ETF / 沪深300ETF / 科创50ETF / 国债ETF。资产名用中文字符串做 key，贯穿所有模块。

---

## 2. 两条独立数据流

### 流 A（运行流 / Runtime）
每月执行一次：

```
数据更新（AkShare）→ 因子计算 → 机会分评分 → 市场温度计
   → 风险买入上限 → PortfolioSnapshot → strategy.planner
   → 正式/影子卖单 → [真实卖出确认] → 三阶段买入 → TradePlan
```

旧 `run.py report` 继续走 V1.3 兼容分配；完整快照走 `run.py plan` 或交易计划 API。

Dashboard 可用截图减少完整快照手填：

```text
浏览器原图 → Tesseract.js 本地 OCR → OCR 文字
  → snapshot_import.service
       ├─ DeepSeek JSON 结构化（可选）
       ├─ 确定性本地解析（默认/回退）
       └─ PIT 本地行情只补缺失现价
  → 可编辑 SnapshotDraft → 显式应用到页面表单
  → [用户另行点击] trade-plan/preview
```

原图不跨浏览器边界；导入草稿不进入 `strategy.repository`，不写 SQLite，也不自动预览或确认交易。

### 流 B（验证流 / Backtest）— `validate.py`
离线定期执行：

```
训练期（2015–2021）调参 → SHA-256 锁定参数 → 测试期（2022–2025）只验
   → V1.3 / 静态年度 / 新策略无保护 / 完整保护四组对照
   → 年化 / 最大回撤 / 夏普 / Calmar / 成本 / 卖出与触发次数
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
│   │   ├── schema.py        DDL（SCHEMA_VERSION=4，含快照/状态/确认/成交）
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
│   ├── snapshot_import/
│   │   ├── parser.py          确定性 OCR 文字解析、别名归一和标签证据
│   │   ├── deepseek.py        可选 JSON Output 结构化适配器（只接收文字）
│   │   ├── models.py          字段级来源/置信度/证据草稿
│   │   └── service.py         输入限制、安全回退与 PIT 现价补齐
│   ├── strategy/
│   │   ├── models.py         PortfolioSnapshot / TradeOrder / TradePlan / 现金账
│   │   ├── planner.py        共享闸门、三阶段补仓、低频卖出和两阶段执行
│   │   ├── kechuang.py       科创利润保护月频状态机
│   │   └── repository.py     快照、成交、状态和幂等确认事务
│   ├── backtest/
│   │   ├── engine.py        V1.3基线＋真实份额/成本/卖出/敏感性回放
│   │   ├── splitter.py      训练/测试日期切分
│   │   └── parameter_lock.py 参数 SHA-256 锁定
│   ├── rebalance/
│   │   └── checker.py       权重兼容模式的年度相对软带检查
│   ├── reports/
│   │   └── monthly.py       月报文本生成（generate_report）
│   └── api/
│       └── server.py        FastAPI（旧报告＋trade-plan＋只读截图文字导入＋history/investments）
├── dashboard/              React 19 + TS + Vite 8 + Tailwind 4
│   ├── src/components/BrokerScreenshotImport.tsx  本地 OCR、核对和显式应用
│   ├── src/hooks/useSnapshotImport.ts             只读配置与文字结构化 API
│   ├── src/hooks/useTradePlan.ts       完整快照只读预览
│   └── src/widgets/ProfitProtectionWidget.tsx  盈利保护状态、正式/影子/买单与现金轧差
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

### 4.2 完整交易计划（CLI / API / 回测共享）

```
PortfolioSnapshot + scores + risk buy limits + thermometer + persisted K state
  → build_trade_plan()                         # 纯函数，预览无写入
       ├─ 复算全账户/受管组合双口径
       ├─ 释放国债池超额标记
       ├─ 核心硬上限 / 年度软带 / K50状态机
       ├─ [有正式卖单] TradePlan(sell_preview)
       └─ [无正式卖单] 战略闸门 → 三阶段买入 → 成本/取整 → TradePlan(complete)

POST /api/trade-plan/confirm
  → 校验 plan_id + idempotency_key
  → apply_confirmed_sells(真实成交)
  → build_trade_plan(成交后派生快照)            # 重算买单
  → 单事务保存 snapshot/items/state/confirmation/fills
```

### 4.3 兼容 API 调用（`GET /api/report`）
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

### 4.4 回测（`python validate.py test`）
```
run_test()
  ├─ verify_snapshot(PARAMETER_LOCK_PATH)   # SHA-256 校验参数锁定
  └─ run_strategy_comparison(conn, mode="test")
       ├─ run_backtest()                    # V1.3 兼容基线
       ├─ run_trade_backtest(static_target_annual)
       ├─ run_trade_backtest(new_no_protection)
       └─ run_trade_backtest(full_protection)
            ├─ PIT factors/prices
            ├─ build_trade_plan()           # 与实盘相同
            ├─ 真实份额、现金、整手、佣金、滑点、国债池和K状态
            └─ metrics + cost/sell/trigger acceptance
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
| `strategy.planner.build_trade_plan` | 完整快照、分数、风险买入上限、温度计、K状态 | 无副作用 `TradePlan`＋确认后状态补丁 |
| `api.server.preview_trade_plan` | `PortfolioSnapshot`＋可选决策输入 | 只读正式/影子/买入计划 |
| `api.server.confirm_trade_plan` | plan_id、幂等键、真实卖出成交 | 成交审计＋成交后重算计划 |

---

## 6. 状态存储位置

| 状态 | 位置 | 作用域 |
|---|---|---|
| SQLite 主库 | `ETF-Allocator/data/db/etf_data.db` | 持久（价格/估值/因子/投资记录/月度快照/成交/K状态） |
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
│  hooks/useTradePlan      │   /api/trade-plan/preview    │  preview_trade_plan      │
│  ProfitProtectionWidget  │   完整快照＋保护/订单展示      │  strategy.planner         │
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
7. **现金不重复计数**：国债池和权益待投现金都是账户现金标记；防御到20%后不再吸收溢出。
8. **趋势开关 OFF ≠ 归零**：减半（×0.50）保留反转参与权。
9. **卖出与买入上限分离**：风险上限只限制买入；静态战略硬上限和年度软带才允许核心卖出。
10. **预览无副作用**：GET/模拟/preview 不写策略状态，只有带幂等键的 confirm 写入。
11. **影子隔离**：`KECHUANG_PROTECTION_MODE=shadow` 时 K50 订单不得进入正式卖单或现金账。
