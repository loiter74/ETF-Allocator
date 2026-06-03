## ADDED Requirements

### Requirement: Point-in-time 回放
回测引擎 SHALL 在决策日期 T 模拟流A的完整逻辑，每步只使用在 T 时刻可见的数据。

#### Scenario: 估值数据过滤
- **WHEN** 回测在日期 T 查询估值数据
- **THEN** 只使用 trade_date <= T AND publish_date <= T 的数据

#### Scenario: 分位 expanding window
- **WHEN** 回测计算分位
- **THEN** 只使用 [数据起点, T] 的数据，上限 5 年

#### Scenario: 回填段选择
- **WHEN** 回测日期 T 在指数的 base_date 和 publish_date 之间
- **THEN** 根据配置决定是否使用该段数据，数据打标供审计

### Requirement: 训练/测试分离
回测引擎 SHALL 支持将数据分为训练期和测试期。

#### Scenario: 默认切分
- **WHEN** 使用默认参数运行回测
- **THEN** 训练期 = 2015-01-01 到 2021-12-31，测试期 = 2022-01-01 到 2025-12-31

#### Scenario: 参数锁定
- **WHEN** 从训练期进入测试期
- **THEN** 所有参数锁定，测试期只执行不调参

### Requirement: 回测指标计算
回测引擎 SHALL 计算年化收益、最大回撤、Calmar 比率、夏普比率。

#### Scenario: 指标计算
- **WHEN** 回测完成
- **THEN** 输出年化收益率、最大回撤、Calmar = 年化收益/最大回撤、夏普比率
