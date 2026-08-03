## ADDED Requirements

### Requirement: 交易计划预览与成交确认接口
系统 SHALL 提供完整快照的只读交易计划预览接口和显式成交确认接口；预览 MUST 幂等且不得修改持仓、累积池、温度计或科创状态，确认接口 MUST 使用幂等键防止重复记账。

#### Scenario: 预览完整快照
- **WHEN** 客户端向 `POST /api/trade-plan/preview` 提交有效 `PortfolioSnapshot`
- **THEN** 系统返回 `TradePlan`，不写入任何业务状态

#### Scenario: 确认卖出后重算
- **WHEN** 客户端向 `POST /api/trade-plan/confirm` 提交计划标识、幂等键和真实卖出成交
- **THEN** 系统记录一次成交与策略状态，并返回基于真实净收入重算的后续交易计划

#### Scenario: 重复确认
- **WHEN** 客户端使用相同幂等键重复提交确认
- **THEN** 系统返回第一次确认结果且不重复改变份额、现金或状态

