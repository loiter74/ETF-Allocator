# src/factors/ — 因子计算

5 个模块：PE/PB 分位、股息率分位、动量+趋势、波动率+回撤。

## STRUCTURE

```
factors/
├── value.py       # pe_percentile(), pb_percentile() — expanding window 分位
├── dividend.py    # dividend_yield_percentile() — 股息率分位（反向：越高越好）
├── momentum.py    # momentum_120d(), ma_trend_200d(), kechuang_opportunity()
├── risk.py        # annualized_volatility(), max_drawdown() — 不进评分
└── __init__.py
```

## WHERE TO LOOK

| 需求 | 函数 | 文件 |
|------|------|------|
| PE / PB 历史分位 | `pe_percentile()`, `pb_percentile()` | `value.py` |
| 股息率分位 | `dividend_yield_percentile()` | `dividend.py` |
| 120日动量 | `momentum_120d()` | `momentum.py` |
| 200日均线趋势 | `ma_trend_200d()` | `momentum.py` |
| 科创50综合机会分 | `kechuang_opportunity()` | `momentum.py` |
| 年化波动率 | `annualized_volatility()` | `risk.py` |
| 最大回撤 | `max_drawdown()` | `risk.py` |

## CONVENTIONS

- **expanding window**：`_expand_truncate()` 截断到最近 N 年，不足 1 年返回 None
- **分位计算**：`expanding_percentile()` 用 `rank / (n-1)`，最小值→0，最大值→1
- **数据不足 → None**：调用方（scoring/engine.py）跳过 None 的资产
- **股息率方向**：股息率越高→分位越高（与 PE 分位相反）
- **动量分位**：先算 120 日收益率，再算该收益率在历史中的分位

## ANTI-PATTERNS

- **不要**直接用全历史算分位 — `_expand_truncate` 已经做了截断
- **不要**在这里做资产硬编码 — 所有参数（窗口年限）从 `config.settings` 读
- **趋势开关 OFF ≠ 归零**：减半不是关掉，保留反转初期的参与权
