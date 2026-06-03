# src/backtest/ — 回测引擎（流B）

Point-in-time 月度回放 + 训练/测试分离验证。

## STRUCTURE

```
backtest/
├── engine.py      # run_backtest() — 逐月模拟流A，计算指标
├── splitter.py    # split_by_date() — 训练/测试期切分
└── __init__.py
```

## WHERE TO LOOK

| 需求 | 函数/位置 |
|------|----------|
| 运行回测 | `run_backtest(conn, mode='train'|'test')` |
| 指标计算 | `compute_metrics(portfolio_values, total_invested, monthly_returns)` |
| 训练/测试切分 | `split_by_date(df, date_col, ...)` 或直接用 `config.settings` 的 `TRAIN_START/END, TEST_START/END` |

## CONVENTIONS

- **Point-in-time 约束**：每个决策月 `T`，只用 `publish_date ≤ T` 的估值和 `trade_date ≤ T` 的价格
- **expanding window 验证**：每个决策点重建因子序列，确保无未来泄漏
- **月度决策**：`_monthly_dates()` 生成月末日期序列
- **指标**：年化收益（CAGR）、最大回撤、Calmar、夏普
- **回填段控制**：`exclude_backfill=True` 时排除指数在 `base_date` 到 `publish_date` 之间的数据

## ANTI-PATTERNS

- **不要**在测试期调参 — 参数在训练期确定后锁死
- **不要**把回测指标当成实盘预期 — Calmar > 1 有效，< 0.5 需重新评估
- **不要**用全市场指数数据当温度计 p2 时假设 `000985`（万得全A）一定有数据 — 无数据时 fallback 到沪深300 PE
