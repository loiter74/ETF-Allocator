## Context

当前温度计（`src/regime/thermometer.py`）实现多档 AND 逻辑：四档阈值 + 双指标必须落在同一区间才行动 + 不一致时冻结上期比例。已定稿规则要求改为极简版：仅当双分位均 >90% 时降温到 50% 权益，其余情况 100% 权益。

同时修正科创50在资产配置中的行业标签准确性。

## Goals / Non-Goals

**Goals:**
- 温度计从 ~84 行简化到 ~30 行，逻辑零歧义
- 删除全局状态变量（`_last_equity_ratio`），消除测试间状态泄漏
- 所有调用方（run.py、validate.py、backtest/engine.py）同步更新
- 修正 config/settings.py 中科创50的描述

**Non-Goals:**
- 不修改因子计算层
- 不修改评分层、风险层、约束层、分配层
- 不改变组合约束规则（已定稿，保持不变）
- 不改变资产池成员或权重上下限

## Decisions

### D1: 极简二元规则

**决策**：`equity_ratio(p1, p2)` 直接返回 `(equity, bond)`，不再返回 `(None, None)`。

**新逻辑**：
```
if p1 is not None and p2 is not None and p1 > 0.90 and p2 > 0.90:
    return (TEMP_COOL_EQUITY, 1.0 - TEMP_COOL_EQUITY)   # 默认 (0.50, 0.50)
else:
    return (1.0, 0.0)                                      # 全仓权益
```

**理由**：规则从"连续档位调节"变为"极端估值阀门"。历史上 60-90% 区间那些档位的调参空间是过拟合的主要来源，二元规则没有可调档位，等于自带正则化。

### D2: 删除全局状态

**决策**：删除 `_last_equity_ratio`、`_last_bond_ratio`、`equity_ratio_with_persistence()`、`reset_persistence()`。

**理由**：新规则没有任何"不一致→冻结"概念——任何状态都直接返回确定值。全局状态是测试间污染和 bug 的常见来源，消除后所有测试可以独立运行。

### D3: 配置参数简化

**决策**：`config/settings.py` 中温度计相关参数从 10+ 行简化为：

```python
# 市场温度计：仅当双分位均 > 此阈值时触发降温
TEMP_TRIGGER_THRESHOLD = 0.90    # 双分位均 >90% 降温
TEMP_COOL_EQUITY = 0.50          # 降温时权益比例
```

删除：`TEMP_INDICATOR_WINDOW_YEARS`（与 `WINDOW_PE_PERCENTILE_YEARS` 重复）、`TEMP_THRESHOLDS`、`TEMP_DEFAULT_EQUITY_RATIO`。

### D4: 科创50标签修正

**决策**：`config/settings.py` 中科创50的注释从 `"宽基成长"` 改为 `"半导体主导的硬科技成长"`，并在资产描述中注明"权重高度集中于半导体行业（约30-40%）"。

**理由**：与设计文档 ds.v1.2.winner.md 补充建议一致——科创50本质是半导体指数，不是宽基。

## Risks / Trade-offs

- **[过度简化]** 80-90%区间不再降温，极端高估但未到90%时仍满仓 → 这正是设计意图：温度计从"微调器"降级为"逃生阀"，组合约束层（VALUE组上限 60%）仍然在控制集中度
- **[调用方兼容]** run.py/validate.py/backtest 中调用 `equity_ratio_with_persistence()` 的地方需要改为 `equity_ratio()` → 代码量小，但需要逐一检查，确保不回传 None 值导致下游崩溃
- **[测试重写]** `test_regime.py` 的原有测试用例覆盖多档阈值和不一致逻辑，需全部重写 → 测试文件规模从 ~50 行缩减到 ~20 行

## Migration Plan

1. 修改 `config/settings.py` — 替换 TEMP 参数段
2. 重写 `src/regime/thermometer.py` — 核心逻辑
3. 更新调用方 — `run.py`、`validate.py`、`src/backtest/engine.py`
4. 重写 `tests/unit/test_regime.py`
5. 运行 `pytest tests/unit/test_regime.py` 验证
6. 运行 `python run.py report --demo` 端到端验证
7. 清理废弃引用（`reset_persistence`、`equity_ratio_with_persistence` 等）

**无回滚风险**：`config/settings.py` 保留旧参数注释便于对照，必要时可直接恢复。
