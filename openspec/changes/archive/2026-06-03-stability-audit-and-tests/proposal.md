## Why

ETF-Allocator v1.2 生产代码存在多个逻辑缺陷：温度计首调用返回 100% 权益、初始建仓模式跳过组合约束、分配函数未使用约束模块输出、前端缺失股票代码显示。需要在修复这些 bug 的同时，建立覆盖全部 10 个模块的自动化测试体系，确保每次代码变更不会引入回归。

## What Changes

- **修复温度计初始状态**：首调用且双指标不一致时，默认权益 70% 而非 100%
- **修复初始建仓不在组合约束内**：`_initial_build_allocation` 后强制运行因子组约束检查
- **修复约束层输出未使用**：`apply_constraints()` 的 buy_coefficients 应传入 `allocate()`
- **前端显示股票代码**：分配卡片和报告 API 返回 code 字段
- **新增 20+ 单元测试**：覆盖因子层、温度计、约束层、分配层的核心逻辑
- **新增 4 个集成测试**：端到端验证过热市场、低估市场、年度再平衡、无未来函数
- **新增 CI 回归测试**：参数边界测试、数据缺失处理测试

## Capabilities

### New Capabilities

- `thermometer-initial-state`: 温度计首调用默认权益比例修正
- `initial-build-constraints`: 初始建仓路径增加因子组约束检查
- `constraint-integration`: 约束层 buy_coefficients 集成到分配算法
- `frontend-stock-codes`: 前端分配卡片显示股票代码
- `factor-layer-tests`: 因子层单元测试（银行复合 z-score、科创50 趋势开关）
- `regime-tests`: 温度计单元测试（双指标一致/不一致/冻结）
- `constraint-tests`: 约束层单元测试（价值组超限、单资产惩罚函数）
- `allocation-tests`: 分配层单元测试（缺口分、混合优先级、边界）
- `integration-tests`: 端到端集成测试（4 场景）
- `regression-tests`: 参数边界和数据缺失回归测试

## Impact

- `src/regime/thermometer.py` — 修改首调用默认权益比
- `src/allocation/allocator.py` — `_initial_build_allocation` 增加约束调用
- `src/api/server.py` — 将 `apply_constraints()` 结果传入 `allocate()`
- `dashboard/src/widgets/AllocationCardsWidget.tsx` — 显示股票代码
- `dashboard/src/types.ts` — 类型定义增加 code 字段
- `tests/` — 新增 20+ 测试文件
