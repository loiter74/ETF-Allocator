## Why

每月有一笔新增资金需要配置到多个ETF和国债上。当前缺乏一个系统化的决策框架，导致三个问题：无法判断各资产的估值高低、长期组合权重容易失控、市场极端情绪影响决策纪律。

需要一个可量化的配置系统，让每个分配决策都有数据支撑，同时约束极端暴露和伪分散。

## What Changes

- 实现一个完整的ETF月度新增资金配置系统（流A），从数据获取到最终分配报告
- 建立回测验证框架（流B），保证所有参数在样本外验证后才上线
- 使用科创50替代原方案中的机器人ETF，作为成长因子的长期承载者
- 实现市场温度计（MarketRegime），在高估时将新钱导向国债
- 实现因子组约束（PortfolioConstraint），防止伪分散（价值组上限60%）
- 实现现金流再平衡分配算法，优先补仓不足资产
- 所有估值分位基于 expanding window 计算，严格防范未来函数
- 年度再平衡机制（偏离目标10个百分点触发）
- 完整的月报输出，每个数字可追溯到因子值和触发规则

## Capabilities

### New Capabilities
- `data-source`: AkShare 数据获取与带 publish_date 的入库逻辑
- `data-store`: SQLite 数据库建表、落库、AntiLookAhead 校验
- `factor-calculation`: 各资产因子计算（PE/PB/股息率分位、动量、趋势开关），全部基于 expanding window
- `market-regime`: 市场温度计，根据沪深300和全A估值分位决定权益/国债投资比例
- `risk-control`: 波动率/回撤计算，动态调整各资产仓位上限
- `portfolio-constraint`: 单资产和因子组两层约束，带平滑惩罚函数
- `scoring-engine`: 因子值到 [0,1] 机会分的标准化转换
- `cash-flow-allocation`: 现金流再平衡分配算法（缺口分 + 机会分混合）
- `backtest-engine`: Point-in-time 回测引擎，训练/测试分离验证
- `report-generation`: 每月配置报告生成，可追溯的决策记录
- `annual-rebalance`: 年度再平衡检查与执行

### Modified Capabilities
- （无，所有能力均为新建）

## Impact

- 新增约15-20个Python模块，分布在 src/ 下各子目录
- 依赖新增：akshare, akshare, pandas, numpy, sqlite3（内置）
- 目录结构：ETF-Allocator/ 下新建 config/, data/, src/, tests/ 等目录
- 数据层：需要首次运行时从 AkShare 拉取历史数据入库
- 不修改任何现有系统（这是一个绿色项目）
