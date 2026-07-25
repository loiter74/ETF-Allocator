"""
scripts/import_pb.py — 用 Tushare 拉取行业指数 PE+PB 数据。

需先设置环境变量 TUSHARE_TOKEN（Tushare Pro 个人主页可获取）。
运行: set TUSHARE_TOKEN=xxx && python scripts/import_pb.py
"""
import os
import tushare as ts, time, sqlite3, sys
from pathlib import Path

TOKEN = os.environ.get('TUSHARE_TOKEN')
if not TOKEN:
    sys.exit('错误：未设置 TUSHARE_TOKEN 环境变量。请到 Tushare Pro 个人主页获取后重试。')
DB = Path(__file__).resolve().parent.parent / 'data' / 'db' / 'etf_data.db'

ts.set_token(TOKEN)
pro = ts.pro_api()
conn = sqlite3.connect(str(DB))

indices = [
    ('399997.SZ', '中证白酒'),
    ('399986.SZ', '中证银行'),
    ('000922.SH', '中证红利'),
    ('000688.SH', '科创50'),
]

for code, name in indices:
    try:
        df = pro.index_dailybasic(
            ts_code=code, start_date='20200101', end_date='20260531',
            fields='ts_code,trade_date,pe,pb'
        )
        if df is None or len(df) == 0:
            print(f'{name}: 无数据'); continue

        count = 0
        for _, r in df.iterrows():
            conn.execute('''INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date)
                VALUES (?,?,?,?,NULL,?) ON CONFLICT(index_code,trade_date) DO UPDATE SET
                pb=COALESCE(excluded.pb,index_valuation.pb),
                pe=COALESCE(excluded.pe,index_valuation.pe)''',
                (code[:6], str(r.trade_date),
                 float(r.pe) if r.pe else None,
                 float(r.pb) if r.pb else None,
                 str(r.trade_date)))
            count += 1
        conn.commit()
        print(f'{name}: {count} 条 PE+PB 入库 (等待 65s...)')
    except Exception as e:
        err = str(e)
        if '频率' in err or '超过' in err:
            print(f'{name}: 速率限制，等待 65s 后重试...')
            time.sleep(65)
            # retry once
            try:
                df = pro.index_dailybasic(ts_code=code, start_date='20200101', end_date='20260531',
                    fields='ts_code,trade_date,pe,pb')
                if df is not None and len(df) > 0:
                    count = 0
                    for _, r in df.iterrows():
                        conn.execute('''INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date)
                            VALUES (?,?,?,?,NULL,?) ON CONFLICT(index_code,trade_date) DO UPDATE SET
                            pb=COALESCE(excluded.pb,index_valuation.pb),
                            pe=COALESCE(excluded.pe,index_valuation.pe)''',
                            (code[:6], str(r.trade_date),
                             float(r.pe) if r.pe else None,
                             float(r.pb) if r.pb else None,
                             str(r.trade_date)))
                        count += 1
                    conn.commit()
                    print(f'  → {name}: {count} 条')
            except Exception as e2:
                print(f'  → {name}: 重试失败 - {str(e2)[:50]}')
        else:
            print(f'{name}: 错误 - {err[:60]}')
    time.sleep(65)

conn.close()
print('\nDone. Verify:')
ver = sqlite3.connect(str(DB))
for code in ['399997','399986','000922','000688']:
    r = ver.execute('SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL', [code]).fetchone()
    print(f'  {code} PB: {r[0]} rows')
ver.close()
