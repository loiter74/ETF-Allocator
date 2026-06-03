# shared-test-fixtures

共享测试数据构造 fixtures，集中管理 16 个测试文件共同使用的数据构造函数。

## ADDED Requirements

### Requirement: 内存 SQLite 数据库 fixture
系统 SHALL 提供 `memory_db` fixture，返回已建表（调用 `create_tables()`）的 `sqlite3 :memory:` 连接，每个测试函数独立隔离。

#### Scenario: 每个测试获得独立空库
- **WHEN** 两个不同的测试函数各自使用 `memory_db` fixture 插入数据
- **THEN** 每个测试 SHALL 看到自己插入的数据，看不到另一个测试的数据（fixture scope=function 隔离）

### Requirement: 标准价格序列 fixture
系统 SHALL 提供 `sample_prices` fixture，返回 300 天 pd.Series，价格从 100 单调上升至 ~150，包含真实日期索引。

#### Scenario: 价格序列包含 300 天数据
- **WHEN** 测试函数使用 `sample_prices` fixture
- **THEN** 返回的 pd.Series SHALL 包含 ≥300 个数据点，第一个值 ≈100，最后一个值 >100，索引为 DatetimeIndex

### Requirement: 标准估值序列 fixture
系统 SHALL 提供 `sample_valuations` fixture，返回 `(pe_series, pb_series, dy_series)` 三元组，每个 Series 包含 300 天数据。

#### Scenario: 估值序列三元组完整
- **WHEN** 测试函数使用 `sample_valuations` fixture
- **THEN** 返回的元组 SHALL 包含 3 个 pd.Series，每个长度 ≥300，pe 值在 [10, 30] 范围，pb 值在 [0.8, 2.0] 范围，dy 值在 [2.0, 5.0] 范围

### Requirement: 标准权重 fixture
系统 SHALL 提供 `standard_weights` fixture，返回 6 资产标准权重 dict，总和为 1.0。

#### Scenario: 权重和为 1.0 且覆盖 6 资产
- **WHEN** 测试函数使用 `standard_weights` fixture
- **THEN** 返回的 dict SHALL 包含 6 个 key（白酒/银行/红利/沪深300/科创50/国债ETF），所有权重之和 SHALL 等于 1.0 ± 0.001

### Requirement: 标准机会分 fixture
系统 SHALL 提供 `standard_scores` fixture，返回 6 资产机会分 dict，国债 ETF 为 None。

#### Scenario: 国债机会分为 None
- **WHEN** 测试函数使用 `standard_scores` fixture
- **THEN** `standard_scores["国债ETF"]` SHALL 为 None，其余 5 个资产的机会分 SHALL 均在 [0, 1] 范围
