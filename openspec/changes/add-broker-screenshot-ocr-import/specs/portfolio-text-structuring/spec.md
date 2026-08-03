## ADDED Requirements

### Requirement: 文字结构化接口必须只读并有界

系统 SHALL 提供只读结构化接口，限制段数和字符数，且 SHALL NOT 保存 OCR 草稿、写策略状态或生成交易确认。

#### Scenario: 合法 OCR 文字

- **WHEN** 客户端提交不超过限制的非空文字段
- **THEN** 接口返回候选快照、字段来源、置信度、证据、警告和所用解析器

#### Scenario: 超限或空请求

- **WHEN** 请求为空或超过段数/字符限制
- **THEN** 接口返回 4xx，且不调用 DeepSeek、不写数据库

### Requirement: DeepSeek 失败必须安全回退

系统 SHALL 把 DeepSeek 作为可选增强器，并对输出做严格验证；不可用时 SHALL 返回本地解析结果而非让整个导入失败。

#### Scenario: DeepSeek 返回有效 JSON

- **WHEN** 已配置 API Key 且模型响应通过 schema 和数值校验
- **THEN** 系统返回归一后的 DeepSeek 草稿并标记 provider/model

#### Scenario: DeepSeek 空响应或无效 JSON

- **WHEN** 两次有界尝试仍为空、非 JSON、HTTP 失败或 schema 无效
- **THEN** 系统使用本地解析器，返回降级警告，且不暴露 Key 或原始模型响应

### Requirement: 资产和数字必须经过确定性校验

系统 SHALL 仅把六资产白名单及明确的非白名单持仓映射为候选行，并 SHALL 校验份额、价格、成本、市值和现金均为有限非负数。

#### Scenario: 识别白名单别名或代码

- **WHEN** 文字包含已配置资产别名或证券代码
- **THEN** 系统映射为标准中文资产名并保留代码和证据行

#### Scenario: 数字角色不明确

- **WHEN** 一行数字无法可靠区分份额、现价、成本或市值
- **THEN** 系统保留可确认字段，其余返回空值和警告，不按位置盲猜

### Requirement: 市场数据只能补现价

系统 SHALL 仅在现价缺失时用快照日可见的最近本地市场价格补齐，且 SHALL NOT 推断或覆盖份额、平均成本和账户现金。

#### Scenario: 缺失现价但有本地历史价格

- **WHEN** 候选持仓有代码、缺失现价且本地存在 `price_date <= snapshot_date` 的价格
- **THEN** 系统补现价，标记来源为 `market_data` 并返回实际价格日期

### Requirement: 服务端配置不得泄密

系统 SHALL 只从服务端环境读取 DeepSeek 凭证，配置接口 SHALL NOT 返回 Key。

#### Scenario: 查询 OCR 配置

- **WHEN** 客户端请求 OCR 配置
- **THEN** 系统只返回是否启用增强解析、模型名、隐私说明和输入限制

