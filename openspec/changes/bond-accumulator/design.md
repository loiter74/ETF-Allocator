## Context

ETF-Allocator v1.2 的分配层输出固收金额后直接记为"买入国债ETF"，但511010场内交易有14,000元最低门槛。月投≤2万时固收分配金额不足一手，实盘无法执行。同时银行/沪深300的25%常态上限偏低，限制了组合作为压舱石的能力。

当前代码：`config/settings.py`（参数）、`src/allocation/allocator.py`（分配）、`src/reports/monthly.py`（报告）、`src/backtest/engine.py`（回测）。

## Goals / Non-Goals

**Goals:**
- 固收分配金额通过虚拟累积池攒够14,000元才触发买入，解决小额资金门槛问题
- 累积池中闲置资金按1.8%年化计息（逆回购近似），月报独立展示
- 银行/沪深300常态上限提升至30%，高波动时降至25%
- 国债ETF从风险控制层移除（固收不受波动率影响）

**Non-Goals:**
- 不修改分配算法、因子计算、评分层、约束层的核心逻辑
- 不引入场外基金替代品（保持511010作为固收标的）
- 不实现逆回购自动执行（仅在回测中按1.8%模拟收益）

## Decisions

### D1: 累积池为纯内存+JSON持久化，不用数据库表

**选择**: BondAccumulator 类 + `data/db/bond_accumulator.json` 状态文件

**替代方案**: 在SQLite中新增`bond_accumulator`表

**理由**: 累积池只有两个字段（balance, total_interest），JSON文件更简单、可读、无schema迁移成本。回测中用内存实例即可，流A用JSON持久化。

### D2: 逆回购收益按月简单计息，不逐日模拟

**选择**: 每月月初按 `balance × 1.8% / 12` 计息

**替代方案**: 逐日模拟GC001逆回购

**理由**: 逐日模拟复杂度高但收益差异极小（年化误差<0.1%）。1.8%是保守估计，不会虚增收益。

### D3: 国债从RISK_CONTROL中完全移除

**选择**: 删除`RISK_CONTROL["国债ETF"]`条目

**替代方案**: 保留条目但设None

**理由**: v1.3明确固收不受波动率影响，直接删除比保留None更清晰，避免controller.py中多余的判断分支。

### D4: 报告层通过参数传入bond_status，不直接依赖accumulator实例

**选择**: `generate_report()` 新增 `bond_status: dict` 参数

**替代方案**: report函数内部持有accumulator引用

**理由**: 保持报告层的纯函数特性——输入数据、输出文本，不持有状态。accumulator的状态快照通过get_status()转为dict传入。

## Risks / Trade-offs

- **[累积池资金闲置]** → 通过1.8%年化逆回购收益缓解，月报展示"现金管理收益"让投资者知情
- **[首次建仓时累积池为空]** → 前几个月固收全部累积不买入，组合波动略大。可考虑首次建仓时如果总额≥14,000直接买入一手
- **[JSON文件并发写入]** → 不适用，每月只运行一次`run.py report`，无并发风险
