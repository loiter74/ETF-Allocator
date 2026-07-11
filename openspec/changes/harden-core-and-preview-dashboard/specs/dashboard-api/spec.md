## MODIFIED Requirements

### Requirement: 月报数据接口
系统 SHALL 提供 `GET /api/report?date=<date>` 接口返回完整月度配置报告，并提供 `POST /api/report` 进行无副作用的自定义参数模拟。两个接口均不得写入持仓、国债累积池或温度计持久化状态。

#### Scenario: 获取当月报告
- **WHEN** 客户端请求 `GET /api/report`
- **THEN** 系统使用最新数据日期，返回温度计、各资产因子/机会分/分配、组合约束等完整 JSON，且不修改任何业务状态

#### Scenario: 获取指定日期报告
- **WHEN** 客户端请求 `GET /api/report?date=2026-04-30`
- **THEN** 系统只使用该日期可见的数据计算结果，返回对应 JSON，且重复请求返回相同结果

#### Scenario: 自定义参数模拟
- **WHEN** 客户端请求 `POST /api/report` 并传入 `current_weights` 和 `total_assets`
- **THEN** 系统使用传入的仓位权重计算分配并返回模拟结果，不保存国债累积池或真实持仓
