## ADDED Requirements

### Requirement: AkShare 数据获取适配器
系统 SHALL 通过 AkShare 库获取指数估值数据和 ETF 价格数据，并在入库时附带 publish_date 字段。

#### Scenario: 获取指数估值数据
- **WHEN** 用户调用 datasource 模块获取指数估值
- **THEN** 系统从 AkShare 获取 PE、PB、股息率、publish_date，并写入 index_valuation 表

#### Scenario: 获取 ETF 价格数据
- **WHEN** 用户调用 datasource 模块获取 ETF 价格
- **THEN** 系统从 AkShare 获取后复权收盘价和成交量，写入 etf_price 表

#### Scenario: 异常重试
- **WHEN** AkShare 请求失败（网络超时、接口错误）
- **THEN** 系统自动重试最多 3 次，间隔 2 秒，全部失败后记录错误日志

#### Scenario: 增量更新
- **WHEN** 系统已存在历史数据
- **THEN** 只拉取缺失交易日期的数据，不重复拉取已有数据

### Requirement: 数据降级路径
系统 SHALL 在 AkShare 不可用时支持从本地 CSV 文件手动导入数据。

#### Scenario: 手动数据导入
- **WHEN** 用户提供符合格式要求的 CSV 文件
- **THEN** 系统解析文件并写入对应数据表
