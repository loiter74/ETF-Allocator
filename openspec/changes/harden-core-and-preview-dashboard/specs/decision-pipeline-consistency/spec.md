## ADDED Requirements

### Requirement: 银行 z-score 评分一致
系统 SHALL 在流 A、流 B 与 API 中使用 `pb_zscore` 和 `dividend_zscore` 按配置权重合成并通过 sigmoid 得到银行机会分。

#### Scenario: 相同输入跨入口评分
- **WHEN** 三个入口收到相同历史 PB、股息率和决策日
- **THEN** 银行机会分相同且位于 `[0,1]`

#### Scenario: 中性 z-score
- **WHEN** 两个 z-score 均为 0
- **THEN** 银行机会分为 0.5

### Requirement: 约束强制传递
系统 SHALL 在每个分配入口应用单资产可买系数、风险调整上限和因子组投后上限。

#### Scenario: 接近单资产上限
- **WHEN** 当前权重进入上限前 5 个百分点缓冲区
- **THEN** 分配器按平滑可买系数缩减最大买入金额

#### Scenario: VALUE 组已有其他资产持仓
- **WHEN** VALUE 组已有持仓接近 60% 且本月只给其中一个资产分配
- **THEN** 允许新增金额基于 VALUE 组全部当前持仓计算，投后权重不得超过 60%

#### Scenario: 多组同时超限
- **WHEN** 一次候选分配会同时突破 VALUE 与 GROWTH 上限
- **THEN** 系统依次缩减两个组并将全部溢出计入国债

### Requirement: 初始建仓遵守上限
系统 SHALL 在总资产为零时按机会分排序建仓，并始终遵守单资产与因子组上限。

#### Scenario: 权益预算仍有剩余
- **WHEN** 所有合格权益资产达到上限后仍有权益预算
- **THEN** 剩余资金进入国债，不得通过第二轮分配越过上限

### Requirement: 温度计冻结可恢复
系统 SHALL 在真实 CLI 月度运行之间保存上一次有效权益比例，并在指标档位不一致时使用该比例。

#### Scenario: 跨进程冻结
- **WHEN** 上月双指标一致得到 40% 权益，本月新进程中双指标档位不一致
- **THEN** 本月权益比例为 40%

#### Scenario: 首次不一致
- **WHEN** 没有历史状态且双指标档位不一致
- **THEN** 系统使用 100% 默认权益比例
