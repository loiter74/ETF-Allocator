## Why

国债ETF（511010）场内最低买入门槛约14,000元（100份×140元/份）。月投金额≤2万时，系统输出的固收分配金额（通常0~7,000元）几乎永远无法实盘执行。同时，银行ETF和沪深300ETF作为流动性最好的资产，常态上限25%偏低，限制了组合作为"压舱石"的能力。

## What Changes

- **新增流动性执行层**：BondAccumulator 虚拟累积池，固收应配金额累加到≥14,000元才触发买入，解决小额资金无法购买国债ETF的问题
- **现金管理**：累积池中闲置资金按1.8%年化计息（逆回购近似），月报单独展示
- **参数调整**：银行ETF和沪深300ETF常态上限25%→30%，高波动上限20%→25%
- **国债脱离风险控制**：固收不再受波动率影响，从RISK_CONTROL中移除
- **报告层更新**：月报新增"国债执行状态"区块，展示累积池余额、触发状态、买入后余留

## Capabilities

### New Capabilities
- `bond-accumulator`: 国债ETF虚拟累积池管理——deposit/execute/persist生命周期，解决场内最低买入门槛问题
- `bond-execution-report`: 月报中国债执行状态展示——累积池余额、逆回购收益、触发/未触发状态、买入后余留

### Modified Capabilities
- `risk-parameters`: 银行ETF和沪深300ETF的常态上限从25%提升至30%，高波动上限从20%提升至25%；国债ETF从风险控制层移除

## Impact

- **新增文件**：`src/execution/bond_liquidity.py`、`data/db/bond_accumulator.json`
- **修改文件**：`config/settings.py`（参数）、`src/reports/monthly.py`（报告模板）、`src/backtest/engine.py`（回测集成）、`src/api/server.py`（API透传）
- **无破坏性变更**：分配算法、因子计算、评分层、约束层逻辑均不变
- **回测影响**：累积池行为需正确模拟——未达门槛资金不计入固收持仓
