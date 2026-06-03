## ADDED Requirements

### Requirement: 月报生成
系统 SHALL 生成月度配置报告，包含市场温度、新增资金分配、各资产触发原因、组合风险状态。

#### Scenario: 完整月报
- **WHEN** 运行 python run.py report
- **THEN** 输出报告包含：市场温度（PE/PB分位和投资比例）、资金分配表（每行有金额、机会分、当前/上限权重）、因子组权重、再平衡检查日期

#### Scenario: 决策可追溯
- **WHEN** 报告中显示某资产的分配金额
- **THEN** 同时显示该资产的因子值和触发规则名称

#### Scenario: 风险显性化
- **WHEN** 报告中显示组合风险
- **THEN** 展示价值+红利组和成长组的当前总权重及上限
