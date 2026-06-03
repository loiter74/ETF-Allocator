"""
auto_import_pb.py — 自动导入 4 个行业指数的 PB 数据。

Tushare 免费版 index_dailybasic 限频 1次/小时。
本脚本：每次处理 1 个缺失指数，等 65 分钟后处理下一个。
总共 4 个指数，约 4.5 小时。

双击 auto_import_pb.bat 启动，保持窗口开着即可。
"""
import sqlite3, time, tushare as ts, sys
from datetime import datetime
from pathlib import Path

TOKEN = 'REDACTED_TUSHARE_TOKEN'
DB = Path(__file__).resolve().parent.parent / 'data' / 'db' / 'etf_data.db'

INDICES = [
    ('399997.SZ', '399997', 'Zhongzheng Baijiu'),
    ('399986.SZ', '399986', 'Zhongzheng Bank'),
    ('000922.SH', '000922', 'Zhongzheng Dividend'),
    ('000688.SH', '000688', 'Kechuang50'),
]

WAIT_SEC = 3900  # 65 min

ts.set_token(TOKEN)
pro = ts.pro_api()


def has_pb(idx_code):
    conn = sqlite3.connect(str(DB))
    row = conn.execute(
        "SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL",
        [idx_code],
    ).fetchone()
    conn.close()
    return row[0] > 0


def import_one(ts_code, idx_code, name):
    conn = sqlite3.connect(str(DB))
    try:
        df = pro.index_dailybasic(
            ts_code=ts_code,
            start_date='20200101',
            end_date='20260601',
            fields='ts_code,trade_date,pe,pb',
        )
        if df is None or len(df) == 0:
            print(f"  [{name}] No data returned")
            conn.close()
            return False
        count = 0
        for _, r in df.iterrows():
            conn.execute(
                """INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date)
                   VALUES (?,?,?,?,NULL)
                   ON CONFLICT(index_code,trade_date) DO UPDATE SET
                   pb=COALESCE(excluded.pb,index_valuation.pb),
                   pe=COALESCE(excluded.pe,index_valuation.pe)""",
                (
                    idx_code,
                    str(r.trade_date),
                    float(r.pe) if r.pe else None,
                    float(r.pb) if r.pb else None,
                    str(r.trade_date),
                ),
            )
            count += 1
        conn.commit()
        now = datetime.now().strftime("%H:%M:%S")
        print(f"  [{name}] {count} rows OK  [{now}]")
        conn.close()
        return True
    except Exception as e:
        print(f"  [{name}] ERROR: {str(e)[:120]}")
        conn.close()
        return False


def print_status():
    conn = sqlite3.connect(str(DB))
    for ts_code, idx_code, name in INDICES:
        tot = conn.execute(
            "SELECT COUNT(*) FROM index_valuation WHERE index_code=?", [idx_code]
        ).fetchone()[0]
        pb = conn.execute(
            "SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL",
            [idx_code],
        ).fetchone()[0]
        tag = "DONE" if pb > 0 else "TODO"
        print(f"  [{tag}] {name:22s} PB={pb:>5d}/{tot}")
    conn.close()


def countdown(seconds):
    """Print a countdown that updates every minute."""
    while seconds > 0:
        mins_left = seconds // 60
        eta = datetime.fromtimestamp(datetime.now().timestamp() + seconds)
        print(f"\r  Waiting {mins_left}min... next at {eta.strftime('%H:%M')}    ", end="", flush=True)
        chunk = min(60, seconds)
        time.sleep(chunk)
        seconds -= chunk
    print("\r  Done waiting.                                      ")


# ── Main ──
print(f"\nStart: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Rate limit: 1 req/hour. Wait={WAIT_SEC // 60}min between requests.\n")

attempts = 0
max_attempts = 10

while attempts < max_attempts:
    pending = [t for t in INDICES if not has_pb(t[1])]

    if not pending:
        print("\n=== ALL PB DATA IMPORTED! ===")
        break

    ts_code, idx_code, name = pending[0]
    done = len(INDICES) - len(pending)
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{done+1}/4] {name} ({ts_code})  [{now}]")

    if import_one(ts_code, idx_code, name):
        print(f"  OK! {len(pending)-1} remaining.")
    else:
        print(f"  Failed (rate limited?). Will retry.")

    # Check again
    pending = [t for t in INDICES if not has_pb(t[1])]
    if not pending:
        print("\n=== ALL PB DATA IMPORTED! ===")
        break

    print()
    countdown(WAIT_SEC)
    attempts += 1

print("\n--- Final Status ---")
print_status()
print(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
