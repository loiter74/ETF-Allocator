## ADDED Requirements

### Requirement: 白酒机会分计算
系统 SHALL 将白酒的 PE 分位转换为 [0,1] 机会分。

#### Scenario: 白酒机会分
- **WHEN** 白酒 PE 分位为 P
- **THEN** 机会分 = 1 - P（PE 分位越低机会分越高）

### Requirement: 银行机会分计算
系统 SHALL 将银行的 PB 分位和股息率分位通过 z-score 合成后转换为 [0,1] 机会分。

#### Scenario: 银行机会分
- **WHEN** 银行 PB 分位和股息率分位已计算
- **THEN** 分别计算 z-score，等权加总，经 sigmoid 映射到 (0,1)

### Requirement: 红利机会分计算
系统 SHALL 将红利的股息率分位直接作为 [0,1] 机会分。

#### Scenario: 红利机会分
- **WHEN** 红利股息率分位为 D
- **THEN** 机会分 = D（分位越高机会越高）

### Requirement: 沪深300 机会分计算
系统 SHALL 将沪深300 的 PE 分位反转后作为 [0,1] 机会分。

#### Scenario: 沪深300 机会分
- **WHEN** 沪深300 PE 分位为 P
- **THEN** 机会分 = 1 - P

### Requirement: 科创50 机会分计算
系统 SHALL 计算科创50 的动量分位，并在趋势开关关闭时减半。

#### Scenario: 科创50 机会分（趋势开）
- **WHEN** 科创50 趋势开关 = ON（Price > MA200）
- **THEN** 机会分 = 120 日动量在 5 年窗口内的分位

#### Scenario: 科创50 机会分（趋势关）
- **WHEN** 科创50 趋势开关 = OFF（Price <= MA200）
- **THEN** 机会分 = 动量分位 × 0.5
