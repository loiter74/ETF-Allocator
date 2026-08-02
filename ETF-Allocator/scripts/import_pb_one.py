"""
scripts/import_pb_one.py — One index at a time, Tushare PB import (1 req/hour limit).

Usage: python scripts/import_pb_one.py
Automatically finds indices with zero PB, processes the first one, then exits.
Re-run every hour until all 4 indices have PB data.
"""
import tushare as ts, time, sqlite3, sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.secrets import get_tushare_token

TOKEN = get_tushare_token()
DB = PROJECT_ROOT / 'data' / 'db' / 'etf_data.db'

TUSHARE_CODE_MAP = {
    '399997': ('399997.SZ', 'Zhongzheng Baijiu'),
    '399986': ('399986.SZ', 'Zhongzheng Bank'),
    '000922': ('000922.SH', 'Zhongzheng Dividend'),
    '000688': ('000688.SH', 'Kechuang 50'),
}

ts.set_token(TOKEN)
pro = ts.pro_api()
conn = sqlite3.connect(str(DB))

# Find indices still missing PB
pending = []
for idx_code, (ts_code, name) in TUSHARE_CODE_MAP.items():
    row = conn.execute(
        "SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL",
        [idx_code]
    ).fetchone()
    if row and row[0] > 0:
        print(f"{name}({idx_code}): PB OK ({row[0]} rows)")
    else:
        pending.append((ts_code, idx_code, name))

if not pending:
    print("\n[DONE] All PB data imported!")
    conn.close()
    sys.exit(0)

ts_code, idx_code, name = pending[0]
print(f"\n>> Processing {name}({ts_code}) — {len(pending)-1} remaining")

try:
    df = pro.index_dailybasic(
        ts_code=ts_code,
        start_date='20200101',
        end_date='20260531',
        fields='ts_code,trade_date,pe,pb'
    )
    if df is None or len(df) == 0:
        print(f"  -> {name}: no data")
    else:
        count = 0
        for _, r in df.iterrows():
            conn.execute(
                '''INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date)
                   VALUES (?,?,?,?,NULL,?)
                   ON CONFLICT(index_code,trade_date) DO UPDATE SET
                   pb=COALESCE(excluded.pb,index_valuation.pb),
                   pe=COALESCE(excluded.pe,index_valuation.pe)''',
                (idx_code, str(r.trade_date),
                 float(r.pe) if r.pe else None,
                 float(r.pb) if r.pb else None,
                 str(r.trade_date))
            )
            count += 1
        conn.commit()
        print(f"  -> {name}: {count} rows PE+PB imported OK")
except Exception as e:
    err = str(e)
    if 'frequency' in err.lower() or 'exceed' in err.lower() or 'interval' in err.lower():
        print(f"  -> {name}: RATE LIMITED (1 req/hour). Wait and retry.")
    else:
        print(f"  -> {name}: ERROR - {err[:120]}")

# Print progress
conn.close()
ver = sqlite3.connect(str(DB))
print("\n-- Progress --")
for idx_code, (ts_code, name) in TUSHARE_CODE_MAP.items():
    total = ver.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=?", [idx_code]).fetchone()[0]
    pb_rows = ver.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL", [idx_code]).fetchone()[0]
    status = "OK" if pb_rows > 0 else "PENDING"
    print(f"  [{status}] {name}({idx_code}): PB={pb_rows} / total={total}")
ver.close()
print(f"\nNext run: python scripts/import_pb_one.py")
