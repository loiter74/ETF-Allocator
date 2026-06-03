## 1. Config 层

- [x] 1.1 简化 `config/settings.py` 温度计参数
- [x] 1.2 修正 `config/settings.py` 科创50 标签

## 2. 温度计核心重写

- [x] 2.1 重写 `src/regime/thermometer.py`
- [x] 2.2 实现新的 `equity_ratio(p1, p2)` 极简二元规则

## 3. 调用方更新

- [x] 3.1 更新 `run.py` temperature import 和调用逻辑
- [x] 3.2 更新 `run.py` 报告层温度标签为二元规则
- [x] 3.3 确认 `validate.py` 无需修改（通过 backtest/engine.py 间接调用）
- [x] 3.4 更新 `src/backtest/engine.py` temperature import 和调用逻辑

## 4. 测试重写

- [x] 4.1 重写 `tests/unit/test_regime.py`（6 条用例）
- [x] 4.2 删除对废弃函数的引用

## 5. 验证

- [x] 5.1 运行 `pytest tests/unit/test_regime.py -v`
- [x] 5.2 运行 `python run.py report --demo`
- [x] 5.3 检查科创50标签已改正
