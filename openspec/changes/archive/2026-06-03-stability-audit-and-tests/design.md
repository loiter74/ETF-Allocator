## Context

当前 v1.2 管线存在四个已知缺陷：

1. **温度计首调用**：当 PE 和 PB 指标不一致且无历史状态时，返回 100% 权益比——这过于激进
2. **初始建仓无约束**：`_initial_build_allocation()` 跳过 `_apply_group_constraint()`，导致 VALUE 组可达 90%
3. **约束输出未使用**：`server.py:117` 的 `apply_constraints()` 输出只用于显示，未传入 `allocate()`
4. **前端缺少代码**：分配卡片不显示 ETF 代码，用户无法快速确认标的

同时缺少覆盖核心管线的自动化测试，每次手动验证成本高。

## Goals / Non-Goals

**Goals:**
- 温度计首调用默认 70% 权益（而非 100%），更保守
- 初始建仓模式自动执行因子组约束（VALUE ≤ 60%, GROWTH ≤ 15%）
- 约束层的 `buy_coefficients` 传入分配器，按比例限制每个资产的可买入金额
- 前端卡片显示 ETF 代码（如 "161725"）
- 20+ 单元测试覆盖因子/温度计/约束/分配核心逻辑
- 4 个集成测试验证端到端场景

**Non-Goals:**
- 不修改 config/settings.py 的参数值
- 不重构整个约束或分配模块架构
- 不添加新的外部依赖
- 不改变已有 API 接口签名

## Decisions

### D1: 温度计默认权益比

**选择**：首调用不一致时默认 70%（参数字段 `ThermometerDefault.equity_first_run = 0.70`）

**理由**：70% 是 4 档（100/70/40/30）的中点。首次运行无法判断方向时，取中间值保守。

**备选**：50%（过于保守，初始建仓阶段应给予信任）、100%（当前行为，过于激进）

### D2: 初始建仓约束

**选择**：在 `_initial_build_allocation()` 返回前调用 `_apply_group_constraint()`

**理由**：约束函数接收 `allocation`、`current_weights`、`total_assets` 三个参数。初始建仓时 `current_weights` 全是 0，`total_assets=0`，约束函数内部用 `new_total = 0 + sum(allocation)` 计算分配后总资产。计算逻辑兼容此场景。

**备选**：在 server.py 中包装调用（耦合度更高）；新增独立约束函数（重复代码）

### D3: 约束集成方式

**选择**：在 server.py 中将 `cons["buy_coefficients"]` 传入 `allocate()`，分配器用 coefficient 缩放 `max_buy`

**理由**：现有代码 `allocate()` 内部已有 `_apply_group_constraint()`，但缺少单资产惩罚。传入 `buy_coefficients` 作为可选的第三个约束维度（risk cap × constraint coefficient × gap/priority）。

**实现**：`allocate()` 新增可选参数 `buy_coefficients: Optional[Dict[str, float]]`。当传入时，`max_buy = min(risk_cap, coeff * total_assets) * equity_budget`。向后兼容（默认 None 时行为不变）。

### D4: 前端代码显示

**选择**：在 `AllocationCardsWidget` 的资产名下方增加一行灰色小字 `(代码 161725)`

**理由**：API 已返回 `code` 字段。前端只需在 `types.ts` 中新增字段，在卡片中显示。

## Risks / Trade-offs

- **温度计默认 70% 可能过于保守**：如果数据充分且市场正常，70% 会少分配权益。缓解：仅影响首次运行，后续有历史状态后自动恢复正常
- **`buy_coefficients` 集成增加复杂度**：分配函数参数增多。缓解：使用 Optional 参数，默认 None 保持向后兼容
- **测试覆盖率上升但维护负担增加**：20+ 测试需要维护。缓解：测试聚焦核心逻辑，避免测实现细节
