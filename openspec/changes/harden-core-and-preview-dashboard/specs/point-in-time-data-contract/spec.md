## ADDED Requirements

### Requirement: 统一日期格式
系统 SHALL 在数据库写入边界将所有交易日期、发布日期、基日和上市日期规范为 ISO `YYYY-MM-DD` 文本。

#### Scenario: 导入八位日期
- **WHEN** 数据源返回 `20260703`、`"20260703"` 或 Pandas 时间对象
- **THEN** 系统写入 `2026-07-03` 且 SQLite `typeof()` 返回 `text`

#### Scenario: 拒绝无效日期
- **WHEN** 输入无法转换为有效日历日期
- **THEN** 系统拒绝该行并输出可定位的错误，不得静默写入

### Requirement: Point-in-time 双日期过滤
系统 SHALL 只向决策日 T 返回 `trade_date <= T` 且 `publish_date <= T` 的估值记录。

#### Scenario: 交易日早但发布日晚
- **WHEN** 估值交易日为 2024-01-15、发布日期为 2024-01-17、决策日为 2024-01-16
- **THEN** 该记录不可见

#### Scenario: 历史数据库含混合日期类型
- **WHEN** 数据库同时含 ISO 文本与八位整数日期
- **THEN** 查询仍按真实日历顺序过滤和排序，不读取决策日后的记录

### Requirement: 可回滚数据迁移
系统 SHALL 提供 dry-run 和带备份的事务迁移，将现有日期转换为 ISO 文本并验证主键完整性。

#### Scenario: 迁移成功
- **WHEN** 用户应用日期迁移
- **THEN** 系统先创建备份，迁移后所有日期为 ISO 文本，表行数和唯一键保持一致

#### Scenario: 迁移冲突
- **WHEN** 两条脏记录规范化后产生无法自动合并的主键冲突
- **THEN** 系统回滚事务并保留原数据库

### Requirement: 价格与因子单位契约
系统 SHALL 将 ETF 价格保存为后复权口径，将股息率内部单位保存为小数。

#### Scenario: ETF 行情请求
- **WHEN** 系统通过 AkShare 拉取 ETF 日线
- **THEN** 请求使用 `hfq` 并映射到 `close_adj`

#### Scenario: 百分数股息率
- **WHEN** 数据源返回股息率 `4.2`
- **THEN** 系统在进入因子层前规范为 `0.042`
