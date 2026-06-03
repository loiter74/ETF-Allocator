## Why

当前温度计使用多档 AND 逻辑（<60%/60-80%/80-90%/>90%）+ 双指标不一致时冻结上期比例，规则复杂导致三个问题：边缘值决策跳变（79% vs 81%）、不一致时的"冻住"状态难以解释、参数空间过大增加过拟合风险。简化为单一触发规则——仅当双指标均 >90% 时降温，使温度计从"连续调节器"变为"极端估值风控阀"，规则零歧义。

同时修正科创50资产标签，准确反映其半导体行业集中度。

## What Changes

- **BREAKING** 温度计规则重大简化：删除四档阈值、AND 多档逻辑、不一致冻结机制、`max()` 加权，改为仅当双分位均 >90% 时触发降温
- **BREAKING** 降温动作从 30%/40%/70% 多档改为单一的 50%（可通过 config 调整）
- **BREAKING** 删除 `_last_equity_ratio` 持久化缓存和 `equity_ratio_with_persistence()` 函数——不再需要
- 删除 `temperature()` 辅助函数——无多档加权需求
- 删除 `_get_band()` 和 `_BAND_EQUITY` 字典——规则表化
- 修正 `config/settings.py` 中科创50的资产描述为"半导体主导的硬科技成长"
- 简化 `config/settings.py` 的 `TEMP_*` 参数：只保留阈值和降温比例

## Capabilities

### Modified Capabilities
- `market-regime`: 温度计从多档 AND 逻辑改为单一双>90%触发规则。删除所有档位阈值、不一致逻辑、持久化缓存。权益比例从 100%/70%/40%/30% 简化为 100%/50%（可配置）。

## Impact

- `src/regime/thermometer.py` — 大幅简化（~84 行 → ~30 行），删除 `_last_equity_ratio`、`_last_bond_ratio`、`equity_ratio_with_persistence()`、`temperature()`、`_get_band()`、`_BAND_EQUITY`、`reset_persistence()`
- `config/settings.py` — 简化 `TEMP_*` 参数段，修正科创50描述
- `run.py` — 删除对 `equity_ratio_with_persistence()` 的调用，改为直接调用简化后的 `equity_ratio()`
- `validate.py` — 同上；回测中不再需要 `reset_persistence()`
- `src/backtest/engine.py` — 同上
- `tests/unit/test_regime.py` — 测试用例需重写
- `src/risk/controller.py` — 不再需要 `reset_recovery_tracking()` 的 import（若由 regime 触发；核查后清理）
