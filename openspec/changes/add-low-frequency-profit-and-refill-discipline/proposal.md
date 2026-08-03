## Why

V1.3 只会分配新增资金，无法在持仓明显超出战略上限或科创50大幅盈利回吐时给出纪律化处理，也缺少基于真实份额、成本和现金的可执行交易计划。此次升级在保留低频、可解释和防未来函数原则的前提下，补上有限卖出、分层补仓和可验证的影子利润保护。

## What Changes

- 将系统定位改为“每月新增资金分配器＋低频风险再平衡器”，重写根 README 为五章核心准则和技术附录。
- 新增统一 `PortfolioSnapshot` 输入和 `TradePlan` 输出，系统复算总资产、权重、现金轧差与交易成本；旧 `weights + total_assets` 继续作为只买不卖的兼容模式。
- 新增全账户权益闸门、三阶段补仓、战略硬上限月度卖出和按目标比例计算的年度软再平衡。
- 将沪深300从 VALUE 拆为 CORE；取消卫星仓；非白名单持仓只计入全账户风险并提示，不自动交易。
- 新增国债一手保护、多手年度整手再平衡和防御桶现金标记规则。
- 新增科创50利润保护状态机；预注册参数固定，默认只输出影子卖单，显式成交确认后才更新持久化状态。
- 运行流、API 和回测复用同一纯决策函数；预览保持只读，有卖单时采用“先确认卖出成交、再重算买入”的两阶段执行。
- 回测升级为真实份额、现金、买卖、整手、佣金、滑点、国债池和科创状态的月度回放，并增加参数锁与四策略对照验收。

## Capabilities

### New Capabilities

- `portfolio-snapshot-trade-plan`: 统一月度持仓快照、交易订单、交易前后暴露和现金轧差契约。
- `disciplined-contribution-allocation`: 全账户权益闸门、三阶段补仓、防御封顶及权益待投现金规则。
- `low-frequency-rebalance`: 战略硬上限月度卖出、年度相对软带和国债低频例外卖出。
- `kechuang-profit-protection`: 科创50影子利润保护、冷静期、重新激活和确认成交状态机。
- `sell-aware-backtest`: 支持真实份额、交易成本、卖出状态和预注册参数验收的月度回测。

### Modified Capabilities

- `dashboard-api`: 新增只读交易计划预览和显式成交确认接口，同时保持现有报告接口兼容。

## Impact

- 配置：`ETF-Allocator/config/settings.py` 的资产分组、仓位带、闸门、成本和利润保护参数。
- 核心：allocation、rebalance、execution、reports、backtest 新增共享交易决策域模型与状态机。
- 存储：SQLite 新增月度持仓快照、科创策略状态和成交确认记录，schema 版本升级。
- 接口：CLI/API 增加完整快照与交易计划，旧报告输入不删除。
- 验证：扩充单元、集成、PIT、参数锁和现金守恒测试；该变更依赖已完成的 `harden-core-and-preview-dashboard` 核心加固成果。
