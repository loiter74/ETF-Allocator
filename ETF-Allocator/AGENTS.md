# ETF-Allocator — 低频再平衡系统 V2 候选

Python 3.10+ | SQLite | FastAPI | React 19 | pytest

每月新增资金配置 + 低频风险再平衡。每个决策可追溯到因子值、状态和规则。
权威设计见根目录 `README.md`（五章准则）；架构现状见 `docs/architecture-current.md`。

## STRUCTURE

```
ETF-Allocator/
├── run.py                  # 流A入口：report（v1.3兼容）/ plan（V2完整快照）/ rebalance
├── validate.py             # 流B入口：train / test / sensitivity 回测验证
├── config/settings.py      # ★ 所有可调参数集中定义（资产/阈值/窗口/上下限/科创预注册）
├── src/
│   ├── store/              # SQLite 建表（schema v4）+ AntiLookAhead 校验
│   ├── datasource/         # AkShare 适配器
│   ├── factors/            # PE/PB 分位、股息率、动量、波动率
│   ├── scoring/            # 因子→[0,1]机会分
│   ├── regime/             # 市场温度计（双指标 AND）
│   ├── risk/               # 波动率→仓位上限调整
│   ├── constraints/        # 单资产 + 因子组约束
│   ├── allocation/         # v1.3 分配算法（保留为回测基准）
│   ├── strategy/           # ★ V2 决策内核（models/planner/kechuang/repository）
│   ├── snapshot_import/    # 券商截图 OCR 文字结构化（parser/deepseek/service）
│   ├── execution/          # 国债虚拟累积池（v1.3，仅流A+回测用）
│   ├── backtest/           # point-in-time 回测（四策略并列 + 参数锁 + 敏感性）
│   ├── reports/            # 月报生成
│   ├── rebalance/          # 年度再平衡检查
│   └── api/server.py       # FastAPI 后端
├── mcp_server/             # MCP server（5 tool，HTTP代理型，stdio传输）
├── tests/                  # unit + integration（26+ 文件）
├── dashboard/              # React 前端（详见 dashboard/AGENTS.md）
├── scripts/                # 数据导入脚本（详见 scripts/AGENTS.md）
└── data/db/etf_data.db     # SQLite（首次运行自动创建）
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| 改 V2 决策逻辑 | `src/strategy/planner.py` | 三阶段补仓 + 卖出 + 科创保护 |
| 改科创利润保护 | `src/strategy/kechuang.py` | 激活/高水位/回撤/冷静期状态机 |
| 改参数/阈值 | `config/settings.py` | 资产池/因子权重/温度计/约束带/科创预注册 |
| 改 API 端点 | `src/api/server.py` | GET report（市场状态）/ trade-plan preview+confirm |
| 跑 V2 交易计划 | `python run.py plan --snapshot s.json` | 完整快照只读预览 |
| 跑 v1.3 兼容报告 | `python run.py report --demo` | 仅分配新钱，无卖出 |
| 跑回测验证 | `python validate.py test` | 四策略并列 + 上线门槛 |
| 看数据表结构 | `src/store/schema.py` | schema v4（含 V2 确认审计表） |

## COMMANDS

```bash
# V2 完整快照交易计划（核心入口）
python run.py plan --snapshot snapshot.json

# v1.3 兼容月报（仅分配，无卖出能力）
python run.py report --demo
python run.py report --weights '{"白酒ETF":0.12}' --total 200000

# 回测验证
python validate.py train         # 训练期调参
python validate.py test          # 测试期四策略并列 + 上线门槛
python validate.py sensitivity   # 预注册敏感性网格（不择优）

# 年度再平衡检查
python run.py rebalance

# 测试
pytest tests/ -v

# MCP server（注册在 .zcode/config.json，自动启动）
# 前端（详见 dashboard/AGENTS.md）
```

## API 端点

| 端点 | 用途 | 副作用 |
|---|---|---|
| `GET /api/report` | 市场状态（温度计/估值/因子），v1.3 退役后不含决策 | 无 |
| `POST /api/report` | 委托 GET（向后兼容） | 无 |
| `POST /api/trade-plan/preview` | V2 完整快照只读预览 | 无 |
| `POST /api/trade-plan/confirm` | 显式确认（写库+推进科创状态） | **有** |
| `GET/POST /api/portfolio-snapshot/*` | 券商截图 OCR | 无 |
| `GET /api/history` | PIT 估值历史 | 无 |

## CONVENTIONS

- **双流分离**：流A（run.py，只执行不调参）| 流B（validate.py，训练调参→锁死→测试只验）
- **防未来函数**：分位用 expanding window，回测估值必须 `publish_date ≤ 决策日`
- **后复权价**：`etf_price.close_adj`
- **风险不进评分**：波动率高→降仓位上限，不影响机会分
- **参数集中**：`config/settings.py` 是唯一参数来源
- **资产名中文 key**：`"白酒ETF"` 等贯穿所有模块
- **温度计**：沪深300 PE AND 全A PB 双指标，档位不一致时冻结上期
- **因子组**：VALUE（白酒+银行+红利）≤60%，CORE（沪深300）≤30%，GROWTH（科创50）≤15%
- **防御桶**：国债ETF+累积池+逆回购 ≤20%；超限后溢出标记为权益待投现金
- **预览无副作用**：只有 `trade-plan/confirm` 才持久化
- **科创利润保护**：默认 shadow，未通过参数锁升级不得生成正式卖单
- **国债累积池**：跨月状态走 JSON 文件（`bond_accumulator.json`），仅流A+回测读写

## ANTI-PATTERNS

- **不要**在模块内硬编码阈值 — 读 `config.settings`
- **不要**用全历史分位 — expanding window（`_expand_truncate`）
- **不要**给"预计年化X%"点估计 — 标"样本内历史"
- **不要**在测试期调参 — 严禁"看着回测改参数"
- **不要**用主 agent 启动服务 — 用子 agent 执行 `start.bat`
