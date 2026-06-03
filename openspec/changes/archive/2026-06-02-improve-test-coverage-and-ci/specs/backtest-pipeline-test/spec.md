# backtest-pipeline-test

全流程 point-in-time 回测管道集成测试。

## ADDED Requirements

### Requirement: 回测管道冒烟测试
系统 SHALL 提供至少一个冒烟测试，验证 `run_backtest()` 在基础场景下不崩溃且返回预期结构的输出。

#### Scenario: 3个月平静行情回放
- **WHEN** 用内存 SQLite 构造 3 个月（每月末一个决策日）的 PE/PB/股息率/价格数据，沪深300 PE 分位~50%、全A PB 分位~45%，调用 `run_backtest(conn, mode='test')`
- **THEN** 函数正常返回 dict，包含 `annualized_return`, `max_drawdown`, `calmar`, `sharpe` 四个键，且均不为 None

### Requirement: 极端高估触发温度计降温
系统 SHALL 验证市场温度计在双指标均 >90% 分位时正确触发权益比例降至 30%。

#### Scenario: 极端高估→70%新钱进国债
- **WHEN** 构造沪深300 PE 分位 95%、全A PB 分位 92% 的估值数据，运行 3 个月回测
- **THEN** 回测过程中每个决策月的权益投资比例 SHALL 为 0.30（30%），且 equity_budget 中至少一次调用 `allocate()` 时传入的 `equity_budget = new_money * 0.30`

### Requirement: 温度计不一致冻结
系统 SHALL 验证当双指标档位不一致时，权益比例冻结为上期值，不随意跳动。

#### Scenario: 不一致冻结→权益维持上期
- **WHEN** 第 1 月双指标均 <60%（权益 100%），第 2 月沪深300 PE 分位 95% 但全A PB 分位 50%（不一致），第 3 月双指标重新一致 <60%
- **THEN** 第 2 月权益比例 SHALL 为 1.00（冻结上期），第 3 月权益比例 SHALL 为 1.00（重新一致后恢复）

### Requirement: 指数回填段排除
系统 SHALL 验证 `EXCLUDE_INDEX_BACKFILL=True` 时，指数在 `base_date` 到 `publish_date` 之间的回填段数据被排除在因子计算之外。

#### Scenario: 回填段数据不可见
- **WHEN** 构造 `index_info` 中沪深300 `base_date=2023-01-01`, `publish_date=2023-06-01`，在 `index_valuation` 中插入 2023-03-15 的估值数据（处于回填段），开启 `EXCLUDE_INDEX_BACKFILL=True` 运行回测
- **THEN** 2023-03-15 的估值数据 SHALL 不在因子计算中被使用（被 `_is_backfill()` 过滤）

### Requirement: 年度再平衡触发检测
系统 SHALL 验证当某资产权重偏离目标中点超过 10 个百分点时，`check_rebalance()` 正确标记需要卖出。

#### Scenario: 白酒权重28%→触发再平衡卖出
- **WHEN** 当前日期为 12 月 1 日（第一个交易日），白酒 ETF 当前权重 28%，目标带 [10%, 25%]，中点 17.5%
- **THEN** `check_rebalance()` 返回结果中白酒 ETF 的 `needs_rebalance` 为 True，且 `sell_amount` > 0
