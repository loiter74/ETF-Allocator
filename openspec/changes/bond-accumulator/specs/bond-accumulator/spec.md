## ADDED Requirements

### Requirement: BondAccumulator 累积池管理
系统 SHALL 维护一个虚拟累积池（BondAccumulator），管理固收应配金额的累积和触发买入逻辑。累积池 SHALL 包含以下状态：`balance`（当前余额）、`total_interest`（累计逆回购收益）。

#### Scenario: 每月固收金额入池
- **WHEN** 分配层输出固收应配金额 ¥3,000
- **THEN** 累积池余额增加 ¥3,000，`balance = balance + 3000`

#### Scenario: 余额不足不触发买入
- **WHEN** 累积池余额为 ¥8,000（< ¥14,000门槛）
- **THEN** 返回 `BondAction(buy=False, lots=0, amount=0.0)`，本月不买入，余额继续累积

#### Scenario: 余额达到门槛触发买入
- **WHEN** 累积池余额为 ¥17,000（≥ ¥14,000门槛）
- **THEN** 返回 `BondAction(buy=True, lots=1, amount=14000.0)`，余额变为 ¥3,000

#### Scenario: 余额足够买多手
- **WHEN** 累积池余额为 ¥31,000
- **THEN** 返回 `BondAction(buy=True, lots=2, amount=28000.0)`，余额变为 ¥3,000

### Requirement: 逆回购收益计息
累积池中的闲置资金 SHALL 按年化1.8%收益率按月计息，模拟场内逆回购（GC001）收益。计息公式：`interest = balance × 0.018 / 12`。利息 SHALL 累加到余额中。

#### Scenario: 月初计息
- **WHEN** 累积池余额为 ¥11,000，执行月度计息
- **THEN** 产生利息 ¥16.50（11000 × 0.018 / 12），余额变为 ¥11,016.50，`total_interest` 累加 ¥16.50

#### Scenario: 空池不计息
- **WHEN** 累积池余额为 ¥0
- **THEN** 利息为 ¥0，余额不变

### Requirement: 状态持久化（流A）
流A（`run.py report`）每月独立运行，累积池状态 SHALL 通过 `data/db/bond_accumulator.json` 持久化。`save()` 将余额和累计收益写入JSON，`load()` 从JSON恢复状态。

#### Scenario: 保存并恢复状态
- **WHEN** 累积池余额 ¥3,000、累计收益 ¥8.50，执行 `save()`
- **THEN** JSON文件包含 `{"balance": 3000.0, "total_interest": 8.50, "last_update": "2026-07-01"}`
- **WHEN** 下月执行 `load()`
- **THEN** 恢复余额 ¥3,000、累计收益 ¥8.50

#### Scenario: 首次运行无状态文件
- **WHEN** `bond_accumulator.json` 不存在，执行 `load()`
- **THEN** 返回余额 ¥0、累计收益 ¥0 的新实例

### Requirement: 回测中无持久化
回测（流B）中 SHALL 使用内存中的单一 BondAccumulator 实例贯穿全程，不读写文件。未达门槛的资金 SHALL NOT 计入固收持仓，不产生国债ETF的资本利得。

#### Scenario: 回测累积池行为
- **WHEN** 回测中连续3个月各输出固收 ¥3,000（累积池 ¥9,000）
- **THEN** 前3个月均不买入，第4个月再入 ¥3,000 后累积池达 ¥12,000 仍不买入，第5个月入 ¥3,000 后达 ¥15,000 触发买入1手

#### Scenario: 回测中未触发资金不计入固收
- **WHEN** 累积池余额 ¥9,000 未触发买入
- **THEN** 这 ¥9,000 不计入固收持仓市值，不产生国债ETF价格变动收益
