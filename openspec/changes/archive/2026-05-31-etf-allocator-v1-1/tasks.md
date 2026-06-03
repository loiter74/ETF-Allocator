## 1. 项目骨架与配置

- [x] 1.1 创建 ETF-Allocator/ 目录结构（config/ data/ src/ tests/ notebooks/）
- [x] 1.2 实现 config/settings.py：所有可调参数（窗口长度、温度计阈值、上下限带、权重参数）
- [x] 1.3 实现 config/assets.py：资产池定义（6个 ETF 的 code、name、asset_class、tracking_index、因子类型）
- [x] 1.4 实现 config/targets.py：各资产目标权重上下限、因子组约束

## 2. 数据层（store + datasource）

- [x] 2.1 实现 src/store/schema.py：SQLite 建表语句（index_info、etf_info、index_valuation、etf_price、etf_factor）
- [x] 2.2 实现 src/store/validator.py：AntiLookAhead 校验器（publish_date 非空检查、回填段标记、point-in-time 查询函数）
- [x] 2.3 实现 src/datasource/akshare_adapter.py：AkShare 数据获取（指数估值、ETF 价格、后复权处理、增量更新、异常重试）
- [x] 2.4 实现 src/datasource/akshare_adapter.py：添加 publish_date 获取（防未来函数）

## 3. 因子层

- [x] 3.1 实现 src/factors/value.py：PE/PB 分位计算（expanding window，5年上限，支持数据不足时用全量）
- [x] 3.2 实现 src/factors/dividend.py：股息率分位计算（expanding window，5年上限）
- [x] 3.3 实现 src/factors/momentum.py：120 日动量计算 + 200 日均线趋势开关（含数据不足处理）
- [x] 3.4 实现 src/factors/risk.py：60 日波动率（年化）和 252 日最大回撤计算

## 4. 评分层

- [x] 4.1 实现 src/scoring/engine.py：白酒机会分（1 - PE分位）
- [x] 4.2 实现 src/scoring/engine.py：银行机会分（z-score 合成 → sigmoid）
- [x] 4.3 实现 src/scoring/engine.py：红利机会分（股息率分位直接映射）
- [x] 4.4 实现 src/scoring/engine.py：沪深300机会分（1 - PE分位）
- [x] 4.5 实现 src/scoring/engine.py：科创50机会分（动量分位 + 趋势开关减半）

## 5. 市场温度计

- [x] 5.1 实现 src/regime/thermometer.py：沪深300 PE 分位 + 全A PB 分位计算
- [x] 5.2 实现 src/regime/thermometer.py：双指标规则引擎（四档阈值 + 不一致维持上期）
- [x] 5.3 实现 src/regime/thermometer.py：上期比例持久化（用于不一致时的维持逻辑）

## 6. 风险控制层

- [x] 6.1 实现 src/risk/controller.py：各资产波动率检查与动态上限调整（5个 ETF 的单独阈值）
- [x] 6.2 实现 src/risk/controller.py：波动率回落后自动恢复正常上限的逻辑（20个交易日观察期）

## 7. 组合约束层

- [x] 7.1 实现 src/constraints/portfolio.py：单资产上下限检查
- [x] 7.2 实现 src/constraints/portfolio.py：因子组约束（价值+红利组上限 60%，成长组上限 15%）
- [x] 7.3 实现 src/constraints/portfolio.py：平滑惩罚函数（线性递减，含边缘值处理）
- [x] 7.4 实现 src/constraints/portfolio.py：综合上限计算（取三者最小值）

## 8. 资金分配层

- [x] 8.1 重写 src/allocation/allocator.py：缺口分计算（设计为 0.5×缺口分 + 0.5×机会分）
- [x] 8.2 重写 src/allocation/allocator.py：全缺口分≤0时跳过缺口，直接用机会分
- [x] 8.3 重写 src/allocation/allocator.py：综合优先级排序与依次分配（含超额资金处理）

## 9. 年度再平衡

- [x] 9.1 实现 src/rebalance/checker.py：年度再平衡检查（12月第一个交易日触发）
- [x] 9.2 实现 src/rebalance/checker.py：再平衡执行（偏离 > 10pp时调整，±5%缓冲）

## 10. 回测引擎（流 B）

- [x] 10.1 实现 src/backtest/splitter.py：训练期/测试期切分（默认 2015-2021/2022-2025）
- [x] 10.2 实现 src/backtest/engine.py：Point-in-time 回放框架（逐月模拟流 A 完整逻辑）
- [x] 10.3 实现 src/backtest/engine.py：估值/价格数据过滤（publish_date 约束、回填段排除选项）
- [x] 10.4 实现 src/backtest/engine.py：分位计算中的 expanding window 验证
- [x] 10.5 实现 src/backtest/engine.py：评价指标计算（年化收益、最大回撤、Calmar、夏普）

## 11. 报告层

- [x] 11.1 实现 src/reports/monthly.py：月报输出（市场温度 + 资金分配表 + 触发原因 + 组合风险）
- [x] 11.2 实现 src/reports/monthly.py：数据可追溯格式（每个金额旁显示因子值和规则名称）

## 12. 入口组装

- [x] 12.1 实现 run.py：流 A 入口（数据更新 → 因子 → 评分 → 温度计 → 风险 → 约束 → 分配 → 报告）
- [x] 12.2 实现 validate.py：流 B 入口（训练期调参 → 参数锁死 → 测试期验证 → 指标输出）

## 13. 测试与验证

- [x] 13.1 为 config 模块编写单元测试
- [x] 13.2 为 store 模块编写单元测试（含 AntiLookAhead 校验）
- [x] 13.3 为 factors 模块编写单元测试（含 expanding window 验证）
- [x] 13.4 为 scoring/regime/risk/constraints 编写单元测试
- [x] 13.5 为 allocation 模块编写单元测试
- [x] 13.6 运行流 B 测试期验证，检查 2022-2025 年回测指标（需安装 akshare 并拉取数据后跑）
- [x] 13.7 验证所有估值分位来自 expanding window，无未来函数泄漏（40/40 factor tests pass）
