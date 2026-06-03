## MODIFIED Requirements

### Requirement: 市场温度计计算
系统 SHALL 基于沪深300 PE 滚动分位（5年 expanding window）和全A等权 PB 滚动分位（5年 expanding window）计算市场温度，输出本月权益投资比例和国债比例。

仅当双分位均超过 90% 触发阈值时降温；其他任何情况（数据缺失、不一致、个别低于阈值等）均维持全仓权益。

#### Scenario: 双指标均超过 90% 触发降温
- **WHEN** 沪深300 PE 分位 > 90% 且 全A PB 分位 > 90%
- **THEN** 权益投资比例 = 50%（可通过 config 调整 TEMP_COOL_EQUITY），国债比例 = 50%

#### Scenario: 任一指标等于或低于 90%
- **WHEN** 沪深300 PE 分位 ≤ 90% 或 全A PB 分位 ≤ 90%
- **THEN** 权益投资比例 = 100%，国债比例 = 0%

#### Scenario: 双指标不一致（一高一低）
- **WHEN** 沪深300 PE 分位 > 90% 但 全A PB 分位 ≤ 90%
- **THEN** 权益投资比例 = 100%，国债比例 = 0%

#### Scenario: 数据缺失
- **WHEN** 任一指标为 None
- **THEN** 权益投资比例 = 100%，国债比例 = 0%（保守默认全仓）

## REMOVED Requirements

### Requirement: 双指标不一致时的冻结机制
**Reason**: 简化后规则无需冻结——任何不一致情况直接返回全仓权益。
**Migration**: 删除 `_last_equity_ratio`、`_last_bond_ratio` 全局状态；删除 `equity_ratio_with_persistence()` 函数。调用方直接使用 `equity_ratio(p1, p2)`，返回值永不为 None。

### Requirement: 多档阈值调节（<60% / 60-80% / 80-90%）
**Reason**: 中温区阈值缺乏有效的调参依据，过度拟合历史。温度计降级为极端估值风控阀，不再做连续调节。
**Migration**: 删除 `_get_band()`、`_BAND_EQUITY`；删除 `TEMP_THRESHOLDS` 配置项。温度计输出从 `(100%/70%/40%/30%)` 简化为 `(100%/50%)`。
