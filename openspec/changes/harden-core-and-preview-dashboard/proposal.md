## Why

当前系统已经具备流 A、流 B、API 与 Dashboard 的完整模块外形，但日期存储混型导致回测既会崩溃又可能读取未来数据，银行评分字段、约束传递、复权口径和现金流指标也在不同入口间不一致。必须先建立可验证的数据与决策契约，再继续依赖回测结果或扩展前端。

## What Changes

- 统一数据库日期为 ISO `YYYY-MM-DD`，在写入、读取和迁移时校验，并修复 point-in-time 查询对混合历史数据的处理。
- 明确估值 `publish_date`、价格复权和股息率单位契约，拒绝无法证明的数据口径。
- 统一流 A、流 B 与 API 的银行 z-score 评分输入和完整分配链路。
- 修复单资产惩罚系数与因子组上限在所有入口中的传递及投后校验。
- 修复初始建仓、国债吸收口和温度计跨进程冻结行为。
- 使用现金流调整后的收益序列计算 CAGR、最大回撤、Sharpe 与 Calmar，并加入可审计的参数锁定快照。
- 将报告 API 改为无副作用读取，将国债累积状态变更限制到显式执行路径。
- 增加覆盖真实 SQLite 类型、未来数据、跨入口一致性和回归公式的测试与数据审计命令。
- 产出一份独立、响应式、无需启动服务即可查看的 Dashboard 优化 HTML 稿，供视觉和信息架构确认，不直接替换现有 React 页面。

## Capabilities

### New Capabilities

- `point-in-time-data-contract`: 日期、发布日期、复权价格和因子单位的统一数据契约与迁移验证。
- `decision-pipeline-consistency`: 流 A、流 B、API 使用相同评分、风险、约束与分配语义。
- `cashflow-aware-backtest`: 使用外部现金流调整后的组合收益和锁定参数快照进行训练/测试验证。
- `dashboard-redesign-preview`: 可独立查看并确认的可信决策工作台 HTML 视觉稿。

### Modified Capabilities

- `dashboard-api`: 报告读取接口必须幂等，不得因 GET 或模拟请求重复写入国债累积池。

## Impact

- 后端：`src/store/`、`src/datasource/`、`src/factors/`、`src/scoring/`、`src/regime/`、`src/constraints/`、`src/allocation/`、`src/backtest/`、`src/api/`。
- 入口：`run.py`、`validate.py` 与数据导入脚本。
- 数据：现有 `data/db/etf_data.db` 需要可重复、可备份的数据迁移与审计。
- 测试：单元、集成与回归测试将新增混合日期、未来数据和跨入口一致性场景。
- 前端：新增独立 HTML 设计稿；现有 React 路由和页面在用户确认前不替换。
