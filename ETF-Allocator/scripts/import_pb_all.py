"""
scripts/import_pb_all.py — Auto PB import with built-in Tushare rate-limit handling.

Tushare free tier: index_dailybasic = 1 req/hour.
This script makes one request per index, waits 65 min between each.
Total runtime: ~4.5 hours for all 4 indices.

Usage: python scripts/import_pb_all.py
"""
import tushare as ts, time, sqlite3, sys
from datetime import datetime
from pathlib import Path

TOKEN = 'REDACTED_TUSHARE_TOKEN'
DB = Path(__file__).resolve().parent.parent / 'data' / 'db' / 'etf_data.db'

WAIT_SECONDS = 3900  # 65 minutes between requests (safe margin over 1 hour)

INDICES = [
    ('399997.SZ', '399997', 'Zhongzheng Baijiu'),
    ('399986.SZ', '399986', 'Zhongzheng Bank'),
    ('000922.SH', '000922', 'Zhongzheng Dividend'),
    ('000688.SH', '000688', 'Kechuang 50'),
]

ts.set_token(TOKEN)
pro = ts.pro_api()


def has_pb(idx_code: str) -> bool:
    conn = sqlite3.connect(str(DB))
    row = conn.execute(
        "SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL",
        [idx_code]
    ).fetchone()
    conn.close()
    return row and row[0] > 0


def import_one(ts_code: str, idx_code: str, name: str) -> bool:
    """Import PB data for one index. Returns True on success."""
    conn = sqlite3.connect(str(DB))
    try:
        df = pro.index_dailybasic(
            ts_code=ts_code,
            start_date='20200101',
            end_date='20260531',
            fields='ts_code,trade_date,pe,pb'
        )
        if df is None or len(df) == 0:
            print(f"  [{name}] No data returned")
            conn.close()
            return False

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
        print(f"  [{name}] {count} rows imported OK [{datetime.now().strftime('%H:%M:%S')}]")
        conn.close()
        return True
    except Exception as e:
        err = str(e)
        if 'frequency' in err.lower() or 'exceed' in err.lower() or 'interval' in err.lower():
            print(f"  [{name}] RATE LIMITED - will retry after wait period")
        else:
            print(f"  [{name}] ERROR: {err[:120]}")
        conn.close()
        return False


def print_progress():
    conn = sqlite3.connect(str(DB))
    print("\n--- Progress ---")
    for ts_code, idx_code, name in INDICES:
        total = conn.execute(
            "SELECT COUNT(*) FROM index_valuation WHERE index_code=?", [idx_code]
        ).fetchone()[0]
        pb_rows = conn.execute(
            "SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL", [idx_code]
        ).fetchone()[0]
        status = "DONE" if pb_rows > 0 else "TODO"
        print(f"  [{status}] {name}: PB={pb_rows}/{total}")
    conn.close()
    print()


def main():
    print("=" * 60)
    print(f"Tushare PB Auto Import - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Each request spaced by {WAIT_SECONDS}s ({WAIT_SECONDS/60:.0f} min)")
    print("=" * 60)

    pending = [(ts, ix, nm) for ts, ix, nm in INDICES if not has_pb(ix)]
    
    if not pending:
        print("\nAll PB data already imported. Nothing to do.")
        print_progress()
        return

    print(f"\n{pending[0][2]} already has PB, skipping\n" if len(pending) < 4 else "")
    print(f"Indices to process: {len(pending)}")
    
    for i, (ts_code, idx_code, name) in enumerate(pending):
        print(f"\n[{i+1}/{len(pending)}] Requesting {name} ({ts_code})...")
        print(f"    Time: {datetime.now().strftime('%H:%M:%S')}")
        
        # Try up to 3 times with wait
        for attempt in range(3):
            if import_one(ts_code, idx_code, name):
                break
            if attempt < 2:
                print(f"    Attempt {attempt+1} failed, waiting {WAIT_SECONDS}s before retry...")
                time.sleep(WAIT_SECONDS)
        
        # Wait before next index (unless it's the last one)
        if i < len(pending) - 1:
            next_name = pending[i+1][2]
            eta = datetime.fromtimestamp(datetime.now().timestamp() + WAIT_SECONDS)
            print(f"\n    Waiting {WAIT_SECONDS}s (~{WAIT_SECONDS/60:.0f} min) before next index ({next_name})...")
            print(f"    Next request at approx: {eta.strftime('%H:%M:%S')}")
            for remaining in range(WAIT_SECONDS, 0, -300):
                elapsed_min = (WAIT_SECONDS - remaining) / 60
                total_min = WAIT_SECONDS / 60
                print(f"    ... {elapsed_min:.0f}/{total_min:.0f} min elapsed", end='\r')
                time.sleep(300)
            print()

    print("\n" + "=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print_progress()


if __name__ == "__main__":
    main()
