"""
scripts/tushare_import.py — 一键数据补全脚本。

数据源：
1. 腾讯财经 API — ETF 后复权价格（无限频）
2. AkShare — LOF 累计净值、中证指数近期估值（无限频）
3. Tushare — 指数 PB/历史股息率（index_dailybasic，限频）

用法：
    python scripts/tushare_import.py              # 全部补全
    python scripts/tushare_import.py --prices      # 只补价格
    python scripts/tushare_import.py --valuation   # 只补估值（PB/DY）
    python scripts/tushare_import.py --info        # 只补指数元信息
    python scripts/tushare_import.py --wait        # 等待限频重置后补估值
"""
import os
import time
import sqlite3
import argparse
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import requests
import tushare as ts

from config.settings import ASSETS

# ── 配置 ──
TOKEN = 'REDACTED_TUSHARE_TOKEN'
DB_PATH = PROJECT_ROOT / 'data' / 'db' / 'etf_data.db'

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# 指数代码映射
INDEX_CODE_MAP = {
    '000300': '000300.SH',
    '000985': '000985.SH',
    '399997': '399997.SZ',
    '399986': '399986.SZ',
    '000922': '000922.SH',
    '000688': '000688.SH',
}

INDEX_INFO = {
    '000300': {'name': '沪深300', 'base_date': '2004-12-31', 'publish_date': '2005-04-08'},
    '000985': {'name': '全A(上证50替代)', 'base_date': '2003-12-31', 'publish_date': '2004-01-02'},
    '399997': {'name': '中证白酒', 'base_date': '2008-12-31', 'publish_date': '2015-01-21'},
    '399986': {'name': '中证银行', 'base_date': '2004-12-31', 'publish_date': '2013-07-15'},
    '000922': {'name': '中证红利', 'base_date': '2004-12-31', 'publish_date': '2005-01-04'},
    '000688': {'name': '科创50', 'base_date': '2019-12-31', 'publish_date': '2020-07-23'},
}

# 按评分影响优先级排序：银行ETF用PB(权重0.5) → 其余PB用于非评分用途
VALUATION_PRIORITY = ['399986', '399997', '000922', '000688', '000300', '000985']

# 成分股加权PB/DY计算参数（index_dailybasic不支持行业指数时使用）
PB_FROM_CONSTITUENTS = {
    '399986': '399986.SZ',   # 中证银行
    '399997': '399997.SZ',   # 中证白酒
    '000688': '000688.SH',   # 科创50
}

# 成分股加权DY计算参数（000922需要用较早日期获取权重）
DY_FROM_CONSTITUENTS = {
    '399986': ('399986.SZ', '20260101'),   # 中证银行
    '399997': ('399997.SZ', '20260101'),   # 中证白酒
    '000922': ('000922.SH', '20180101'),   # 中证红利（需较早日期）
    '000688': ('000688.SH', '20260101'),   # 科创50
}

_session = None
ts.set_token(TOKEN)
pro = ts.pro_api()


def log(msg):
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.trust_env = False
        _session.proxies = {'http': None, 'https': None}
    return _session


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS index_info (
            index_code TEXT PRIMARY KEY, name TEXT NOT NULL,
            base_date DATE NOT NULL, publish_date DATE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS etf_info (
            code TEXT PRIMARY KEY, name TEXT NOT NULL,
            asset_class TEXT NOT NULL, factor_group TEXT NOT NULL,
            tracking_index TEXT, list_date DATE
        );
        CREATE TABLE IF NOT EXISTS index_valuation (
            index_code TEXT NOT NULL, trade_date DATE NOT NULL,
            pe REAL, pb REAL, dividend_yield REAL, publish_date DATE NOT NULL,
            PRIMARY KEY (index_code, trade_date)
        );
        CREATE TABLE IF NOT EXISTS etf_price (
            code TEXT NOT NULL, trade_date DATE NOT NULL,
            close_adj REAL NOT NULL, volume REAL,
            PRIMARY KEY (code, trade_date)
        );
    """)
    conn.commit()
    return conn


# ============================================================
# 1. 指数元信息
# ============================================================
def import_index_info(conn):
    log("=== 指数元信息 ===")
    existing = conn.execute("SELECT COUNT(*) FROM index_info").fetchone()[0]
    if existing >= len(INDEX_INFO):
        log(f"  已有 {existing} 条")
        return
    for code, info in INDEX_INFO.items():
        conn.execute(
            "INSERT OR IGNORE INTO index_info (index_code, name, base_date, publish_date) VALUES (?,?,?,?)",
            (code, info['name'], info['base_date'], info['publish_date'])
        )
    conn.commit()
    log(f"  写入 {len(INDEX_INFO)} 条")


# ============================================================
# 2. LOF 累计净值 (AkShare)
# ============================================================
def import_lof_akshare(conn, code='161725', name='白酒ETF'):
    cnt = conn.execute("SELECT COUNT(*) FROM etf_price WHERE code=?", [code]).fetchone()[0]
    if cnt > 2000:
        log(f"  {name}: 已有 {cnt} 条")
        return
    log(f"  {name}({code}): 拉取累计净值...")
    try:
        import akshare as ak
        df = ak.fund_open_fund_info_em(symbol=code, indicator='累计净值走势')
        df = df.rename(columns={'净值日期': 'trade_date', '累计净值': 'close_adj'})
        df = df[df['close_adj'] > 0]
        n = 0
        for _, r in df.iterrows():
            conn.execute(
                "INSERT INTO etf_price (code,trade_date,close_adj,volume) VALUES (?,?,?,NULL) "
                "ON CONFLICT(code,trade_date) DO UPDATE SET close_adj=excluded.close_adj",
                (code, str(r['trade_date']), float(r['close_adj']))
            )
            n += 1
        conn.commit()
        log(f"  {name}: {n} 条")
    except Exception as e:
        log(f"  {name}: 失败 - {str(e)[:100]}")


# ============================================================
# 3. ETF 后复权价格 (腾讯 API)
# ============================================================
def _tencent_qfq(symbol, end_date=''):
    s = get_session()
    r = s.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
              params={'param': f'{symbol},day,,{end_date},500,qfq'}, timeout=15)
    return r.json().get('data', {}).get(symbol, {}).get('qfqday', [])


def import_etf_tencent(conn, code, symbol, name, target='2015-01-01'):
    row = conn.execute("SELECT MIN(trade_date),COUNT(*) FROM etf_price WHERE code=?", [code]).fetchone()
    if row[0] and row[0] <= target and row[1] > 1000:
        log(f"  {name}: 已足够({row[0]}起,{row[1]}条)")
        return
    log(f"  {name}({code}): 拉取后复权价格...")
    all_rows, end, prev = [], '', None
    for _ in range(20):
        batch = _tencent_qfq(symbol, end)
        if not batch or batch[0][0] == prev:
            break
        prev = batch[0][0]
        all_rows = batch + all_rows
        if prev <= target:
            break
        end = prev
    seen, unique = set(), []
    for r in reversed(all_rows):
        if r[0] not in seen:
            unique.append(r); seen.add(r[0])
    unique.sort(key=lambda x: x[0])
    n = 0
    for r in unique:
        conn.execute(
            "INSERT INTO etf_price (code,trade_date,close_adj,volume) VALUES (?,?,?,?) "
            "ON CONFLICT(code,trade_date) DO UPDATE SET close_adj=excluded.close_adj,"
            "volume=COALESCE(excluded.volume,etf_price.volume)",
            (code, r[0], float(r[2]), float(r[5]) if r[5] else None)
        )
        n += 1
    conn.commit()
    log(f"  {name}: {n} 条 ({unique[0][0]} ~ {unique[-1][0]})")


# ============================================================
# 4. ETF 价格 (Tushare fund_daily + fund_adj)
# ============================================================
def import_etf_tushare(conn, code, ts_code, name):
    """用 Tushare fund_daily + fund_adj 获取后复权价格。"""
    row = conn.execute("SELECT MIN(trade_date),COUNT(*) FROM etf_price WHERE code=?", [code]).fetchone()
    if row[0] and row[1] > 2000 and row[0] <= '2019-01-01':
        log(f"  {name}: 已足够({row[0]}起,{row[1]}条)")
        return

    log(f"  {name}({ts_code}): Tushare fund_daily...")
    try:
        # 获取复权因子
        adj_df = pro.fund_adj(ts_code=ts_code, start_date='20100101', end_date='20991231')
        if adj_df is None or len(adj_df) == 0:
            log(f"  {name}: 无复权因子")
            return

        adj_map = {}
        for _, r in adj_df.iterrows():
            adj_map[str(r['trade_date'])] = float(r['adj_factor'])

        # 获取日线
        df = pro.fund_daily(ts_code=ts_code, start_date='20100101', end_date='20991231')
        if df is None or len(df) == 0:
            log(f"  {name}: 无日线")
            return

        n = 0
        for _, r in df.iterrows():
            close = float(r['close']) if r.get('close') else None
            if close is None or close <= 0:
                continue
            td = str(r['trade_date'])
            adj = adj_map.get(td, 1.0)
            close_adj = close * adj  # 后复权价 = 收盘价 × 复权因子
            vol = float(r['vol']) if r.get('vol') else None
            conn.execute(
                "INSERT INTO etf_price (code,trade_date,close_adj,volume) VALUES (?,?,?,?) "
                "ON CONFLICT(code,trade_date) DO UPDATE SET close_adj=excluded.close_adj,"
                "volume=COALESCE(excluded.volume,etf_price.volume)",
                (code, td, close_adj, vol)
            )
            n += 1
        conn.commit()
        log(f"  {name}: {n} 条(Tushare复权)")
    except Exception as e:
        log(f"  {name}: 失败 - {str(e)[:120]}")


# ============================================================
# 5. 近期估值 (中证指数官网)
# ============================================================
def import_recent_csindex(conn):
    log("=== 近期估值(中证指数官网) ===")
    try:
        import akshare as ak
    except ImportError:
        log("  akshare 未安装"); return
    for code, info in INDEX_INFO.items():
        try:
            df = ak.stock_zh_index_value_csindex(symbol=code)
            if df is None or len(df) == 0:
                continue
            n = 0
            for _, r in df.iterrows():
                pe = float(r['市盈率1']) if r.get('市盈率1') else None
                dy = float(r['股息率1']) / 100.0 if r.get('股息率1') else None
                conn.execute(
                    "INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date) "
                    "VALUES (?,?,?,NULL,?,?) ON CONFLICT(index_code,trade_date) DO UPDATE SET "
                    "pe=COALESCE(excluded.pe,index_valuation.pe),"
                    "dividend_yield=COALESCE(excluded.dividend_yield,index_valuation.dividend_yield),"
                    "publish_date=excluded.publish_date",
                    (code, str(r['日期']), pe, dy, str(r['日期']))
                )
                n += 1
            conn.commit()
            if n > 0:
                log(f"  {info['name']}: {n} 条")
        except Exception:
            pass


# ============================================================
# 6. 指数 PB / 历史股息率 (Tushare index_dailybasic)
# ============================================================
def import_index_pb_tushare(conn, idx_code, ts_code, idx_name):
    """单个指数的 PB/DY 数据拉取。返回是否需要等待。"""
    total = conn.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=?", [idx_code]).fetchone()[0]
    pb = conn.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL", [idx_code]).fetchone()[0]
    dy = conn.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND dividend_yield IS NOT NULL", [idx_code]).fetchone()[0]

    if total > 0 and pb > total * 0.9 and dy > total * 0.9:
        log(f"  {idx_name}: PB/DY 完整({pb}PB,{dy}DY/{total}总)")
        return False

    log(f"  {idx_name}({ts_code}): 拉取 index_dailybasic...")
    try:
        df = pro.index_dailybasic(ts_code=ts_code, start_date='20100101', end_date='20991231',
                                   fields='ts_code,trade_date,pe,pb,dv_ratio')
        if df is None or len(df) == 0:
            log(f"  {idx_name}: 无数据")
            return False
        n = 0
        for _, r in df.iterrows():
            pe = float(r['pe']) if r.get('pe') is not None else None
            pb_v = float(r['pb']) if r.get('pb') is not None else None
            dy = float(r['dv_ratio']) / 100.0 if r.get('dv_ratio') is not None else None
            conn.execute(
                "INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(index_code,trade_date) DO UPDATE SET "
                "pe=COALESCE(excluded.pe,index_valuation.pe),"
                "pb=COALESCE(excluded.pb,index_valuation.pb),"
                "dividend_yield=COALESCE(excluded.dividend_yield,index_valuation.dividend_yield),"
                "publish_date=excluded.publish_date",
                (idx_code, str(r['trade_date']), pe, pb_v, dy, str(r['trade_date']))
            )
            n += 1
        conn.commit()
        log(f"  {idx_name}: 导入 {n} 条")
        return True
    except Exception as e:
        err = str(e)
        if '频率' in err or 'exceed' in err.lower():
            log(f"  {idx_name}: 频率超限")
            return True
        log(f"  {idx_name}: {err[:100]}")
        return False


def import_all_pb(conn, wait=True):
    """拉取所有指数的 PB/DY，自动处理限频。"""
    log("=== 指数 PB（成分股加权计算） ===")
    for idx_code, ts_idx_code in PB_FROM_CONSTITUENTS.items():
        name = INDEX_INFO[idx_code]['name']
        calc_pb_from_constituents(conn, idx_code, ts_idx_code, name)

    log("=== 指数 DY（成分股加权计算） ===")
    for idx_code, (ts_idx_code, weight_sd) in DY_FROM_CONSTITUENTS.items():
        name = INDEX_INFO[idx_code]['name']
        calc_dy_from_constituents(conn, idx_code, ts_idx_code, name, weight_sd)

    # 对 index_dailybasic 支持的主流指数（沪深300、上证50）也尝试补充
    log("=== 指数 PB/DY（Tushare index_dailybasic） ===")
    for idx_code in ['000300', '000985']:
        ts_code = INDEX_CODE_MAP[idx_code]
        name = INDEX_INFO[idx_code]['name']
        import_index_pb_tushare(conn, idx_code, ts_code, name)
        time.sleep(3)


# ============================================================
# 7. 成分股加权PB（当 index_dailybasic 不支持行业指数时）
# ============================================================
def calc_pb_from_constituents(conn, idx_code, ts_idx_code, idx_name, start='20150101'):
    """从成分股权重和个股PB计算指数级PB。"""
    pb_cnt = conn.execute(
        "SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL",
        [idx_code]
    ).fetchone()[0]
    if pb_cnt > 500:
        log(f"  {idx_name}: 已有 {pb_cnt} 条PB，跳过")
        return

    log(f"  {idx_name}({ts_idx_code}): 从成分股计算加权PB...")

    # 获取成分股权重
    weight_df = None
    for sd in ['20260101', '20250101', '20240101', '20230101']:
        weight_df = pro.index_weight(index_code=ts_idx_code, start_date=sd, end_date='20991231')
        if weight_df is not None and len(weight_df) > 0:
            break
        time.sleep(1)

    if weight_df is None or len(weight_df) == 0:
        log(f"  {idx_name}: 无法获取成分股权重")
        return

    latest = weight_df['trade_date'].max()
    weights = weight_df[weight_df['trade_date'] == latest][['con_code', 'weight']].copy()
    weights['weight'] = weights['weight'] / weights['weight'].sum()
    log(f"  {idx_name}: {len(weights)} 只成分股 ({latest})")

    # 逐只获取PB历史
    pb_data = {}
    for i, (_, row) in enumerate(weights.iterrows()):
        stock = row['con_code']
        try:
            df = pro.daily_basic(ts_code=stock, start_date=start, end_date='20991231',
                                  fields='ts_code,trade_date,pb')
            if df is not None and len(df) > 0:
                pb_data[stock] = df.set_index('trade_date')['pb']
        except Exception:
            pass
        time.sleep(0.3)

    if not pb_data:
        log(f"  {idx_name}: 无PB数据")
        return

    # 加权平均
    pb_df = pd.DataFrame(pb_data)
    w_map = weights.set_index('con_code')['weight'].to_dict()
    w_common = {k: v for k, v in w_map.items() if k in pb_df.columns}
    w_total = sum(w_common.values())
    if w_total > 0:
        for k in w_common:
            w_common[k] /= w_total

    weighted_pb = sum(pb_df[s].fillna(0) * w for s, w in w_common.items())
    threshold = len(w_common) * 0.3
    weighted_pb[pb_df.notna().sum(axis=1) < threshold] = None
    valid_pb = weighted_pb.dropna()

    # 入库
    n = 0
    for td, pv in valid_pb.items():
        conn.execute(
            "INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date) "
            "VALUES (?,?,NULL,?,NULL,?) ON CONFLICT(index_code,trade_date) DO UPDATE SET "
            "pb=COALESCE(excluded.pb,index_valuation.pb)",
            (idx_code, td, float(pv), td)
        )
        n += 1
    conn.commit()
    log(f"  {idx_name}: {n} 条加权PB ({valid_pb.index[0]} ~ {valid_pb.index[-1]})")


# ============================================================
# 8. 成分股加权DY（股息率）
# ============================================================
def calc_dy_from_constituents(conn, idx_code, ts_idx_code, idx_name, weight_sd='20260101', start='20150101'):
    """从成分股的 daily_basic dv_ratio 加权计算指数股息率。"""
    dy_cnt = conn.execute(
        "SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND dividend_yield IS NOT NULL",
        [idx_code]
    ).fetchone()[0]
    if dy_cnt > 500:
        log(f"  {idx_name}: 已有 {dy_cnt} 条DY，跳过")
        return

    log(f"  {idx_name}({ts_idx_code}): 从成分股计算加权DY...")

    # 获取成分股权重
    weight_df = None
    for sd in [weight_sd, '20250101', '20240101', '20220101', '20180101']:
        weight_df = pro.index_weight(index_code=ts_idx_code, start_date=sd, end_date='20991231')
        if weight_df is not None and len(weight_df) > 0:
            break
        time.sleep(1)

    if weight_df is None or len(weight_df) == 0:
        log(f"  {idx_name}: 无法获取成分股权重")
        return

    latest = weight_df['trade_date'].max()
    weights = weight_df[weight_df['trade_date'] == latest][['con_code', 'weight']].copy()
    weights['weight'] = weights['weight'] / weights['weight'].sum()
    log(f"  {idx_name}: {len(weights)} 只成分股 ({latest})")

    # 逐只获取 dv_ratio（股息率）
    dy_data = {}
    for i, (_, row) in enumerate(weights.iterrows()):
        stock = row['con_code']
        try:
            df = pro.daily_basic(ts_code=stock, start_date=start, end_date='20991231',
                                  fields='ts_code,trade_date,dv_ratio')
            if df is not None and len(df) > 0:
                df['dv_ratio'] = df['dv_ratio'] / 100.0
                dy_data[stock] = df.set_index('trade_date')['dv_ratio']
        except Exception:
            pass
        time.sleep(0.3)

    if not dy_data:
        log(f"  {idx_name}: 无股息率数据")
        return

    # 加权平均
    dy_df = pd.DataFrame(dy_data)
    w_map = weights.set_index('con_code')['weight'].to_dict()
    w_common = {k: v for k, v in w_map.items() if k in dy_df.columns}
    w_total = sum(w_common.values())
    if w_total > 0:
        for k in w_common:
            w_common[k] /= w_total

    weighted_dy = sum(dy_df[s].fillna(0) * w for s, w in w_common.items())
    threshold = len(w_common) * 0.3
    weighted_dy[dy_df.notna().sum(axis=1) < threshold] = None
    valid_dy = weighted_dy.dropna()

    # 入库
    n = 0
    for td, dv in valid_dy.items():
        conn.execute(
            "INSERT INTO index_valuation (index_code,trade_date,pe,pb,dividend_yield,publish_date) "
            "VALUES (?,?,NULL,NULL,?,?) ON CONFLICT(index_code,trade_date) DO UPDATE SET "
            "dividend_yield=COALESCE(excluded.dividend_yield, index_valuation.dividend_yield)",
            (idx_code, td, float(dv), td)
        )
        n += 1
    conn.commit()
    log(f"  {idx_name}: {n} 条加权DY ({valid_dy.index[0]} ~ {valid_dy.index[-1]})")
# ============================================================
def print_status(conn):
    print("\n" + "=" * 65)
    print("数据状态")
    print("=" * 65)
    for name, cfg in ASSETS.items():
        code = cfg['code']
        row = conn.execute(
            "SELECT COUNT(*),MIN(trade_date),MAX(trade_date) FROM etf_price WHERE code=?", [code]
        ).fetchone()
        if row[0] > 0:
            s = "OK" if row[1] <= '2019-01-01' or code in ('161725',) else "OK"
            print(f"  [{s}] {name:8s}({code}): {row[0]:5d}条 {row[1]}~{row[2]}")
        else:
            print(f"  [--] {name:8s}({code}): 无数据")
    print()
    for code, info in INDEX_INFO.items():
        t = conn.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=?", [code]).fetchone()[0]
        pb = conn.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pb IS NOT NULL", [code]).fetchone()[0]
        dy = conn.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND dividend_yield IS NOT NULL", [code]).fetchone()[0]
        pe = conn.execute("SELECT COUNT(*) FROM index_valuation WHERE index_code=? AND pe IS NOT NULL", [code]).fetchone()[0]
        pb_s = "OK" if pb > t * 0.5 else "MISS"
        dy_s = "OK" if dy > t * 0.5 else "MISS"
        print(f"  {info['name']:10s}({code}): {t}条 PE:{pe} PB:[{pb_s}]{pb} DY:[{dy_s}]{dy}")
    print("=" * 65)


# ============================================================
# MAIN
# ============================================================
def main():
    p = argparse.ArgumentParser(description='ETF-Allocator 数据补全')
    p.add_argument('--prices', action='store_true')
    p.add_argument('--valuation', action='store_true')
    p.add_argument('--info', action='store_true')
    p.add_argument('--wait', action='store_true', help='估值模式: 等待限频重置')
    args = p.parse_args()
    do_all = not (args.prices or args.valuation or args.info or args.wait)
    conn = get_conn()

    print(f"\n{'='*65}")
    print(f"ETF-Allocator 数据补全 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}\n")

    if do_all or args.info:
        import_index_info(conn)
        print()

    if do_all or args.prices:
        log("=== ETF/LOF 价格 ===")
        import_lof_akshare(conn)
        for code, sym, name, tgt in [
            ('515080','sh515080','红利ETF','2019-01-01'),
            ('512800','sh512800','银行ETF','2015-01-01'),
            ('510300','sh510300','沪深300ETF','2015-01-01'),
            ('588000','sh588000','科创50ETF','2020-01-01'),
            ('511010','sh511010','国债ETF','2015-01-01'),
        ]:
            import_etf_tencent(conn, code, sym, name, tgt)
        print()

    if do_all or args.valuation or args.wait:
        import_recent_csindex(conn)
        print()
        import_all_pb(conn, wait=args.wait)
        print()

    print_status(conn)
    conn.close()


if __name__ == '__main__':
    main()
