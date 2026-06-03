## ADDED Requirements

### Requirement: SQLite 数据库建表
系统 SHALL 在首次运行时创建符合设计文档的表结构，包括 index_info、etf_info、index_valuation、etf_price、etf_factor 表。

#### Scenario: 首次运行自动建表
- **WHEN** 系统首次启动且数据库文件不存在
- **THEN** 系统自动创建所有表并写入初始元数据

#### Scenario: 重复建表安全
- **WHEN** 数据库已存在各表
- **THEN** 系统跳过建表步骤，不报错

### Requirement: AntiLookAhead 校验器
系统 SHALL 在写入估值数据时验证 publish_date 字段，确保所有查询在 point-in-time 模式下只能访问在决策日已公开的数据。

#### Scenario: 数据写入校验
- **WHEN** 写入 index_valuation 数据
- **THEN** 系统确保 publish_date 不为空

#### Scenario: Point-in-time 查询
- **WHEN** 回测引擎在日期 T 查询估值数据
- **THEN** 查询条件为 trade_date <= T AND publish_date <= T

### Requirement: 指数回填段标记
系统 SHALL 根据 index_info 的 base_date 和 publish_date 识别回填段数据，并可在查询时选择性排除。

#### Scenario: 回填段识别
- **WHEN** 查询 index_valuation 在 base_date 到 publish_date 之间的数据
- **THEN** 系统返回数据时附带回填段标记
