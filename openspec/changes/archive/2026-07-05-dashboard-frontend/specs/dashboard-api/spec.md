## ADDED Requirements

### Requirement: 月报数据接口
系统 SHALL 提供 `GET /api/report?date=<date>` 接口，返回完整月度配置报告数据。

#### Scenario: 获取当月报告
- **WHEN** 客户端请求 `GET /api/report`
- **THEN** 系统使用最新数据日期，返回温度计、各资产因子/机会分/分配、组合约束等完整 JSON

#### Scenario: 获取指定日期报告
- **WHEN** 客户端请求 `GET /api/report?date=2026-04-30`
- **THEN** 系统计算该日期的因子和分配结果，返回对应 JSON

#### Scenario: 自定义参数模拟
- **WHEN** 客户端请求 `POST /api/report` 并传入 `current_weights` 和 `total_assets`
- **THEN** 系统使用传入的仓位权重计算分配，返回模拟结果

### Requirement: 历史数据接口
系统 SHALL 提供 `GET /api/history?index=<code>&field=<field>&years=<n>` 接口，返回指定指数的历史 PE 或 PB 序列。

#### Scenario: 获取沪深300 PE 历史
- **WHEN** 客户端请求 `GET /api/history?index=000300&field=pe&years=5`
- **THEN** 系统从 SQLite 读取近 5 年的 PE 数据，返回日期-数值-分位序列

#### Scenario: 不支持的字段
- **WHEN** 客户端请求 `GET /api/history?index=000300&field=dividend_yield`
- **THEN** 系统返回空数组并标注 `"available": false`
