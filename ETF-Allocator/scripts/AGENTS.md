# scripts/ — 数据导入脚本

Python | AkShare | Tushare | SQLite

从外部数据源拉取 ETF 价格、指数估值和 PB 数据，写入 `data/db/etf_data.db`。

## STRUCTURE

```
scripts/
├── import_data.py       # 主入口：批量拉取 ETF 价格 + 指数估值（AkShare）
├── import_pb_all.py     # 批量 PB 数据导入（Tushare，含限速处理）
├── import_pb_one.py     # 单指数 PB 导入
├── import_pb.py         # PB 导入核心逻辑
├── auto_import_pb.py    # 自动定时 PB 导入
├── auto_import_pb.bat   # Windows 批处理包装
└── tushare_import.py    # Tushare 通用数据导入（价格+估值，590 行）
```

## WHERE TO LOOK

| 需求 | 文件 | 说明 |
|------|------|------|
| 第一次拉全量数据 | `import_data.py` | AkShare → SQLite，覆盖价格和估值 |
| 补 PB 数据 | `import_pb_all.py` | Tushare，带 65 秒限速 |
| 定时自动导入 | `auto_import_pb.py` | 可配置调度 |
| 了解 Tushare 流程 | `tushare_import.py` | 最大文件，含完整导入逻辑 |

## CONVENTIONS

- **数据写入统一走 `src/store/`**：不直接写 SQL，通过 `src/store/schema.py` 的表结构
- **限速处理**：Tushare 免费接口有频率限制，`import_pb_all.py` 含 `time.sleep(65)` 限速
- **输出数据库**：`../data/db/etf_data.db`（相对路径）
- **错误处理**：导入失败不崩，记录日志后继续下一批

## ANTI-PATTERNS

- **不要**跳过 `publish_date` 字段 — 回测依赖它防未来函数
- **不要**修改 `src/store/schema.py` 而不更新导入脚本 — schema 变了导入就炸
- **不要**在生产导入中关闭限速 — Tushare 会封 IP

## COMMANDS

```bash
# 批量导入（AkShare）
python scripts/import_data.py

# PB 数据导入（Tushare）
python scripts/import_pb_all.py

# 定时自动导入
python scripts/auto_import_pb.py

# Windows 双击运行
scripts/auto_import_pb.bat
```
