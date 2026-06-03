## ADDED Requirements

### Requirement: 白酒 ETF PE 分位计算
系统 SHALL 计算白酒 ETF 的 PE 滚动历史分位（5年 expanding window），分位越低机会越高。

#### Scenario: PE 分位计算
- **WHEN** 在日期 T 计算白酒因子
- **THEN** 使用 [T-5年, T] 的 PE 数据计算分位，基于 expanding window

#### Scenario: 数据不足时处理
- **WHEN** 可用历史数据不足 5 年
- **THEN** 使用现有全部数据计算分位

### Requirement: 银行 ETF PB 和股息率分位计算
系统 SHALL 计算银行 ETF 的 PB 分位和股息率分位（各 5年 expanding window）。

#### Scenario: PB 分位计算
- **WHEN** 在日期 T 计算银行 PB 分位
- **THEN** 使用 [T-5年, T] 的 PB 数据计算分位

#### Scenario: 股息率分位计算
- **WHEN** 在日期 T 计算银行股息率分位
- **THEN** 使用 [T-5年, T] 的股息率数据计算分位

### Requirement: 红利 ETF 股息率分位计算
系统 SHALL 计算红利 ETF 的股息率分位（5年 expanding window），分位越高机会越高。

#### Scenario: 股息率分位计算
- **WHEN** 在日期 T 计算红利因子
- **THEN** 使用 [T-5年, T] 的股息率数据计算分位

### Requirement: 沪深300 PE 分位计算
系统 SHALL 计算沪深300 的 PE 分位（5年 expanding window），分位越低机会越高。

#### Scenario: PE 分位计算
- **WHEN** 在日期 T 计算沪深300 因子
- **THEN** 使用 [T-5年, T] 的 PE 数据计算分位

### Requirement: 科创50 动量和趋势开关计算
系统 SHALL 计算科创50 的 120 日动量和 200 日均线趋势开关。

#### Scenario: 动量计算
- **WHEN** 在日期 T 计算科创50 动量
- **THEN** 计算过去 120 个交易日的价格涨幅

#### Scenario: 趋势开关计算
- **WHEN** 在日期 T 计算科创50 趋势开关
- **THEN** 计算 200 日均线，比较当前价格，输出 ON（Price > MA200）或 OFF

#### Scenario: 数据不足处理
- **WHEN** 历史数据不足 120 或 200 个交易日
- **THEN** 使用现有数据计算，标记为低置信度

### Requirement: 波动率和最大回撤计算（风险因子）
系统 SHALL 计算每个 ETF 的 60 日波动率（年化）和 252 日最大回撤。

#### Scenario: 波动率计算
- **WHEN** 在日期 T 计算某 ETF 的波动率
- **THEN** 计算过去 60 个交易日的对数收益率标准差，年化乘以 sqrt(252)

#### Scenario: 最大回撤计算
- **WHEN** 在日期 T 计算某 ETF 的最大回撤
- **THEN** 计算过去 252 个交易日的峰值到谷值最大跌幅
