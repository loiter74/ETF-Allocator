## 1. 参数更新（config/settings.py）

- [ ] 1.1 更新 RISK_CONTROL：银行ETF (0.25,0.20,0.25)→(0.30,0.25,0.25)，沪深300ETF (0.25,0.20,0.30)→(0.30,0.25,0.30)
- [ ] 1.2 从 RISK_CONTROL 中删除"国债ETF"条目
- [ ] 1.3 更新 TARGET_BANDS：银行ETF (0.10,0.25)→(0.10,0.30)，沪深300ETF (0.10,0.25)→(0.10,0.30)
- [ ] 1.4 新增配置块：BOND_MIN_PURCHASE=14000, BOND_UNIT_SIZE=100, BOND_EXECUTION_MODE="ACCUMULATE", BOND_CASH_YIELD=0.018

## 2. BondAccumulator 实现（TDD）

- [ ] 2.1 创建 src/execution/__init__.py 和 src/execution/bond_liquidity.py 骨架
- [ ] 2.2 编写 tests/unit/test_bond_liquidity.py 测试用例（deposit、execute触发/不触发、多手、逆回购计息、状态快照）
- [ ] 2.3 实现 BondAction dataclass（buy, lots, amount）
- [ ] 2.4 实现 BondAccumulator.deposit() — 累加余额
- [ ] 2.5 实现 BondAccumulator.accrue_interest() — 按月计息 (balance × 0.018 / 12)
- [ ] 2.6 实现 BondAccumulator.execute() — 判断是否触发买入，计算手数，扣减余额
- [ ] 2.7 实现 BondAccumulator.get_status() — 返回状态快照 dict
- [ ] 2.8 实现 BondAccumulator.save()/load() — JSON持久化到 data/db/bond_accumulator.json
- [ ] 2.9 运行测试，全部通过

## 3. 报告层更新（src/reports/monthly.py）

- [ ] 3.1 generate_report() 新增 bond_status: dict 参数
- [ ] 3.2 实现"国债执行状态"区块渲染逻辑（触发/未触发两种展示）
- [ ] 3.3 更新 tests/unit/test_monthly_report.py 验证新区块

## 4. 回测引擎集成（src/backtest/engine.py）

- [ ] 4.1 在回测循环外创建 BondAccumulator 实例（贯穿全程）
- [ ] 4.2 每月调用 deposit → accrue_interest → execute 流程
- [ ] 4.3 未触发买入时，余额不计入固收持仓，不产生国债ETF资本利得
- [ ] 4.4 更新 tests/integration/test_backtest_pipeline.py 验证累积池行为

## 5. 流A集成（run.py + API）

- [ ] 5.1 run.py report 中加载/保存 BondAccumulator 状态
- [ ] 5.2 将 bond_status 传入 generate_report()
- [ ] 5.3 API (/api/report) 透传 bond_status 到前端
- [ ] 5.4 更新 tests/integration/test_api.py

## 6. 验证

- [ ] 6.1 运行全量测试 pytest tests/ -v，确认无回归
- [ ] 6.2 运行 python run.py report --demo，确认报告包含国债执行状态
- [ ] 6.3 验证月投10,000元时固收金额正确进入累积池
