# ETF-Allocator — 月度新增资金配置系统 v1.2

Python 3.10+ | SQLite | pandas | AkShare | pytest

每月一问你该问的问题：这笔新钱怎么分到 6 个 ETF / 债，该不该全分出去。
每个决策可追溯到"哪条数据 + 哪条规则"。不预测涨跌，不择时进出。

## STRUCTURE

```
ETF-Allocator/
├── run.py                  # 流A入口：月度配置报告
├── validate.py             # 流B入口：回测验证
├── config/
│   └── settings.py         # ★ 所有可调参数集中定义（权重/阈值/窗口/上下限）
├── src/
│   ├── store/              # SQLite 建表 + AntiLookAhead 校验
│   ├── datasource/         # AkShare 适配器（估值/价格拉取）
│   ├── factors/            # 因子计算（PE/PB/股息/动量/趋势/波动率）
│   ├── scoring/            # 因子→[0,1]机会分
│   ├── regime/             # 市场温度计（双指标 AND 逻辑）
│   ├── risk/               # 波动率→仓位上限调整
│   ├── constraints/        # 组合约束（单资产 + 因子组 + 平滑惩罚）
│   ├── allocation/         # 资金分配（缺口分+机会分混合 + 初始建仓模式）
│   ├── backtest/           # 回测引擎（point-in-time + 训练/测试分离）
│   ├── reports/            # 月报生成
│   ├── rebalance/          # 年度再平衡检查
│   └── api/                # FastAPI 后端
├── tests/
│   ├── unit/               # 14 个单元测试文件
│   └── integration/
├── dashboard/              # React 前端（详见 dashboard/AGENTS.md）
│   ├── src/pages/          # AiriDashboard, Simulator, Trends
│   ├── src/widgets/        # 8 个可拖拽小组件
│   └── src/hooks/          # useReport, useDashboardData, useHistory
├── scripts/                # 数据导入脚本（详见 scripts/AGENTS.md）
│   ├── import_data.py      # AkShare 批量拉取
│   └── import_pb_all.py    # Tushare PB 数据导入
└── data/db/etf_data.db     # SQLite（首次运行自动创建）
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| 改参数 / 调阈值 | `config/settings.py` | 所有旋钮集中在此 |
| 加新 ETF | `config/settings.py` → ASSETS 字典 | 同步更新 TARGET_BANDS / FACTOR_WEIGHTS |
| 改分配算法 | `src/allocation/allocator.py` | `allocate()` 主函数 |
| 改温度计规则 | `src/regime/thermometer.py` | `equity_ratio()` + `equity_ratio_with_persistence()` |
| 跑月度报告 | `python run.py report` | `--demo` 模式无需真实数据 |
| 跑回测验证 | `python validate.py train/test` | 训练期调参，测试期只看不调 |
| 看数据表结构 | `src/store/schema.py` | DDL 字符串 |

## CONVENTIONS

- **双流分离**：`run.py`（流A，只执行不调参）→ `validate.py`（流B，训练期调参后锁死到测试期验证）
- **点对点时间**：所有估值分位用 expanding window，上限 5 年，严禁全历史分位
- **后复权价**：`etf_price.close_adj`，分红必须正确再投资
- **publish_date**：`index_valuation.publish_date`，回测只能查 `publish_date ≤ 决策日`
- **风险不进评分**：波动率高 → 降仓位上限，不影响机会分
- **参数集中**：`config/settings.py` 是唯一参数来源，模块内部不硬编码阈值
- **设计文档唯一**：`ds.v1.2.winner.md` 是唯一设计规范，所有架构/公式/规则以该文件为准，实现必须可追溯到其具体章节

## ANTI-PATTERNS

- **不要**在模块内部硬编码窗口长度/阈值 — 一律读 `config.settings`
- **不要**用全历史数据算分位 — 用 expanding window（`src/factors/value.py::_expand_truncate`）
- **不要**拿 PE 分位(0-1) 和股息率(%) 直接比大小 — 统一转成 `[0,1]` 机会分
- **不要**给"预计年化 X%"这种点估计 — 要给就标"样本内历史，仅供参考"
- **不要**在未来函数上自欺 — 回测的估值数据必须带 `publish_date` 过滤
- **不要**用主 agent 启动后端服务 — 必须用子 agent 执行 `start.bat`，否则主 agent 卡死无响应，无法校验程序

## UNIQUE STYLES

- 资产名用中文字符串作为 key（`"白酒ETF"`, `"银行ETF"` 等），贯穿所有模块
- 机会分输出统一 `[0,1]`，国债永远 `None`（不参与评分）
- 温度计双指标：沪深300 PE分位 AND 全A PB分位，不一致时冻结上期比例
- 因子组约束：VALUE 组（白酒+银行+红利+沪深300）上限 60%，防伪分散
- 国债是"吸收口"：温度计强制债比例 + 分配溢出都进国债

## COMMANDS

```bash
# 月度报告（演示模式，无需真实数据）
python run.py report --demo

# 初始建仓（总资产=0）
python run.py report --demo --total 0

# 指定真实持仓
python run.py report --weights '{"白酒ETF":0.12,"银行ETF":0.22,...}' --total 200000

# 回测（需先有数据）
python validate.py train    # 训练期调参
python validate.py test     # 测试期验证

# 年度再平衡检查
python run.py rebalance

# 运行所有测试
pytest tests/ -v
```

## QA TESTING CONVENTIONS

- **必须使用子 agent 启动服务**：QA 测试前用子 agent 执行 `start.bat`，确保前后端均正常运行且日志无报错
- **必须使用 `qa` skill**：所有前端测试步骤必须通过 `qa` skill 执行，结合 `playwright` 技能进行页面捕获
- **严禁复用 playwright 缓存**：每次测试前必须重新获取最新数据，不得使用上一次 playwright 的缓存截图或结果
- **主 agent 禁止启动后端**：主 agent 直接启动 uvicorn/Vite 会导致进程阻塞、无法响应后续指令

## NOTES

- **科创50 替代机器人ETF**：行业过于集中的主题赌注替换为宽基成长
- **回填段 = 危险段**：指数 `base_date` 到 `publish_date` 之间的回填数据带着未来视角
- **AkShare 依赖**：首次运行需 `pip install akshare`，或使用 `--demo` 模式
- **全局状态**：温度计持久化（`_last_equity_ratio`）和波动率恢复计数（`_low_vol_days`）是模块级变量，测试后需 `reset_persistence()` / `reset_recovery_tracking()`
