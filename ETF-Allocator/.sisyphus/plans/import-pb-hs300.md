# PB 数据导入执行计划 — 行业指数 PB + 沪深300全量估值

## 背景

ETF-Allocator 系统需要 4 个行业指数（中证白酒/中证银行/中证红利/科创50）的 PB 数据，以及沪深300的完整 PE+PB 估值历史，用于因子计算（PE分位/PB分位/股息率分位）。

当前状态：
- 所有指数 **PE 已入库**（来自 AkShare `stock_index_pe_lg`）
- 所有行业指数 **PB 为 0**（Tushare `index_dailybasic` 未成功运行）
- 沪深300 PE+PB 已有基础数据（AkShare `import_data.py`），但数据可能不完整

## 执行步骤

### Step 1: 行业指数 PB 导入（Tushare，~4小时）

Tushare 免费版 `index_dailybasic` 接口限制：**1次/小时**。

```
python scripts/import_pb_all.py
```

自动流程：
- 等待 ~1h（距上次调用的冷却窗口）
- 逐次拉取 4 个指数的 PE+PB（每次间隔61分钟）
- 通过 `ON CONFLICT DO UPDATE` 合并到 `index_valuation` 表
- 预计总耗时：~4-5小时
- 预计拉取：每个指数约 1500-2000 条记录（2020-01-01 ~ 2026-05-31）

日志会实时输出到终端，显示每个指数的入库行数和进度。

### Step 2: 沪深300 PE+PB 全量估值（AkShare）

沪深300是温度计核心指标，需要完整的 PE+PB 历史。AkShare 的 `stock_index_pe_lg` / `stock_index_pb_lg` 提供 5000+ 行历史数据。

```
python scripts/import_data.py
```

注意：这个脚本会拉取**所有**ETF价格和指数估值，如果之前跑过，用 `ON CONFLICT` 自动跳过已有数据，只补缺。

### Step 3: 验证数据完整性

确认所有字段齐全后，再跑流A月度报告：

```bash
# 1. 检查数据库
python -c "
import sqlite3
db = 'data/db/etf_data.db'
conn = sqlite3.connect(db)

# 行业指数 PB
for code,name in [('399997','中证白酒'),('399986','中证银行'),('000922','中证红利'),('000688','科创50')]:
    total = conn.execute('SELECT COUNT(*) FROM index_valuation WHERE index_code=?',[code]).fetchone()[0]
    pb = conn.execute('SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL',[code]).fetchone()[0]
    pe = conn.execute('SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pe IS NOT NULL',[code]).fetchone()[0]
    print(f'{name}: PE={pe} PB={pb} total={total}')

# 沪深300
r = conn.execute(\"SELECT COUNT(*) FROM index_valuation WHERE index_code='000300' AND pb IS NOT NULL\").fetchone()
print(f'沪深300 PB: {r[0]} rows')

# ETF价格
for code in ['512690','512800','510880','510300','588000','511010']:
    r = conn.execute('SELECT COUNT(*), MAX(trade_date) FROM etf_price WHERE code=?',[code]).fetchone()
    print(f'{code}: {r[0]} rows, latest={r[1]}')

conn.close()
"

# 2. 跑月度报告（演示模式先验证流程）
python run.py report --demo

# 3. 确认逻辑无误后，跑真实数据
python run.py report
```

## 关键技术点

| 项目 | 说明 |
|------|------|
| Tushare Token | 已内置，`3d769e33...` |
| 数据源 | 行业指数 PB → Tushare（唯一可用源）；PE → AkShare（已有） |
| 入库策略 | `ON CONFLICT DO UPDATE` — 不会重复，只补缺 |
| 数据库路径 | `data/db/etf_data.db` |
| 沪深300 PE/PB | AkShare `stock_index_pe_lg` / `stock_index_pb_lg`（5000+行全历史） |
| 全A PB(A股等权) | AkShare `stock_a_all_pb` → 用于温度计双指标 |

## 预计耗时

| 步骤 | 耗时 | 自动化 |
|------|------|--------|
| Step 1: 行业PB导入 | ~4-5小时 | 全自动（import_pb_all.py） |
| Step 2: 沪深300估值 | ~2-5分钟 | 全自动（import_data.py） |
| Step 3: 验证+报告 | ~1分钟 | 手动验证 |
| **总计** | **~5小时** | Step 1-2 可无人值守 |

## 涉及的脚本文件

| 文件 | 用途 |
|------|------|
| `scripts/import_pb_all.py` | Tushree 行业指数 PB 自动导入（含等待） |
| `scripts/import_pb_one.py` | 同上，手动单次版本（每小时跑一次） |
| `scripts/import_pb.py` | 原始版本（一次性跑4个，不适用） |
| `scripts/import_data.py` | AkShare 全部数据导入（价格+估值） |
| `src/datasource/akshare_adapter.py` | AkShare 适配器（被 run.py 调用） |

## 注意事项

1. **不要关终端** — Step 1 需要 ~4 小时持续运行（或使用 `start /b` 后台运行）
2. **网络稳定** — Tushare 和 AkShare 都需要网络访问
3. **磁盘空间** — 数据库预计增长到 50-100MB
4. **Tushare 免费额度** — `index_dailybasic` 每小时1次，每天约24次额度，够用
5. **如果中断** — 重新运行 `import_pb_all.py`，已入库的数据不会重复（ON CONFLICT）
