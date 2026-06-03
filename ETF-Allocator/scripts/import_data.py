"""
scripts/import_data.py — 从 AkShare 拉取历史数据并写入 SQLite。

数据源：
- ETF 价格: fund_etf_hist_em（后复权日线）
- 沪深300 PE/PB: stock_index_pe_lg / stock_index_pb_lg（5000+ 行历史）
- 行业指数 PE/PB/股息率: stock_zh_index_value_csindex（仅近 20 天）
- 上证50 PE/PB: stock_index_pe_lg / stock_index_pb_lg（作为全A替代）
"""
import sys
import sqlite3
from pathlib import Path
from datetime import date

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import akshare as ak

from config.settings import ASSETS, TRADING_DAYS_PER_YEAR
from src.store.schema import create_tables, insert_etf_price, insert_index_valuation, insert_etf_info


DB_PATH = PROJECT_ROOT / "data" / "db" / "etf_data.db"

# ── ETF 价格获取 ──
def import_etf_prices(conn):
    """拉取所有 ETF 的后复权历史价格。"""
    for name, cfg in ASSETS.items():
        code = cfg["code"]
        print(f"  拉取 {name}({code}) 价格...", end=" ")
        try:
            df = ak.fund_etf_hist_em(
                symbol=code, period="daily",
                start_date="20100101", end_date="20991231",
                adjust="qfq",
            )
            if df is None or len(df) == 0:
                print("无数据")
                continue
            df = df.rename(columns={"日期": "trade_date", "收盘": "close_adj", "成交量": "volume"})
            df = df[df["close_adj"] > 0]
            for _, row in df.iterrows():
                insert_etf_price(
                    conn,
                    code=code,
                    trade_date=str(row["trade_date"]),
                    close_adj=float(row["close_adj"]),
                    volume=float(row["volume"]) if pd.notna(row.get("volume")) else None,
                )
            print(f"{len(df)} 条")
        except Exception as e:
            print(f"失败: {e}")


# ── 指数估值获取 ──
# 沪深300 用 stock_index_pe_lg/pb_lg（全历史）
def import_hs300_valuation(conn):
    """沪深300 估值——用 stock_index_pe_lg + stock_index_pb_lg（全量历史）。"""
    print("  沪深300 PE/PB 历史...", end=" ")
    try:
        pe_df = ak.stock_index_pe_lg(symbol="沪深300")
        pb_df = ak.stock_index_pb_lg(symbol="沪深300")
        # 合并: 日期, pe, pb
        pe_df = pe_df.rename(columns={"日期": "trade_date", "静态市盈率": "pe"})
        pb_df = pb_df.rename(columns={"日期": "trade_date", "市净率": "pb"})
        merged = pe_df[["trade_date", "pe"]].merge(
            pb_df[["trade_date", "pb"]], on="trade_date", how="outer"
        )
        merged["dividend_yield"] = None  # PE/PB API 不含股息率
        merged["publish_date"] = merged["trade_date"]
        merged = merged.dropna(subset=["pe", "pb"], how="all")

        for _, row in merged.iterrows():
            insert_index_valuation(
                conn, index_code="000300",
                trade_date=str(row["trade_date"]),
                pe=float(row["pe"]) if pd.notna(row.get("pe")) else None,
                pb=float(row["pb"]) if pd.notna(row.get("pb")) else None,
                dividend_yield=None,
                publish_date=str(row["publish_date"]),
            )
        print(f"{len(merged)} 条")
    except Exception as e:
        print(f"失败: {e}")

# 全A 用 上证50 PE/PB（替代，因为全A无直接数据源）
def import_all_market_valuation(conn):
    """全A 估值——用 上证50 作为替代（stock_index_pe_lg 支持的指数有限）。"""
    print("  全A(上证50替代) PE/PB 历史...", end=" ")
    try:
        pe_df = ak.stock_index_pe_lg(symbol="上证50")
        pb_df = ak.stock_index_pb_lg(symbol="上证50")
        pe_df = pe_df.rename(columns={"日期": "trade_date", "静态市盈率": "pe"})
        pb_df = pb_df.rename(columns={"日期": "trade_date", "市净率": "pb"})
        merged = pe_df[["trade_date", "pe"]].merge(
            pb_df[["trade_date", "pb"]], on="trade_date", how="outer"
        )
        merged["dividend_yield"] = None
        merged["publish_date"] = merged["trade_date"]
        merged = merged.dropna(subset=["pe", "pb"], how="all")
        for _, row in merged.iterrows():
            insert_index_valuation(
                conn, index_code="000985",
                trade_date=str(row["trade_date"]),
                pe=float(row["pe"]) if pd.notna(row.get("pe")) else None,
                pb=float(row["pb"]) if pd.notna(row.get("pb")) else None,
                dividend_yield=None,
                publish_date=str(row["publish_date"]),
            )
        print(f"{len(merged)} 条")
    except Exception as e:
        print(f"失败: {e}")

# 行业指数用 stock_zh_index_value_csindex（近20天，含股息率）
# 也尝试用 stock_index_pe_lg 对可用指数
LG_PE_INDICES = {
    "399997": "中证白酒", "399986": "中证银行",
    "000922": "中证红利", "000688": "科创50",
}

def import_sector_valuation(conn):
    """行业指数估值——优先 stock_index_pe_lg/pb_lg，失败则 csindex。"""
    for idx_code, idx_name in LG_PE_INDICES.items():
        print(f"  {idx_name}({idx_code}) 估值...", end=" ")
        try:
            # 试 stock_index_pe_lg
            pe_df = ak.stock_index_pe_lg(symbol=idx_name)
            print(f"PE历史{len(pe_df)}行", end=" ")
        except Exception:
            pe_df = None
            print("lg PE 不可用", end=" ")

        try:
            pb_df = ak.stock_index_pb_lg(symbol=idx_name)
            print(f"PB历史{len(pb_df)}行", end=" ")
        except Exception:
            pb_df = None

        # 合并
        rows = []
        if pe_df is not None:
            for _, r in pe_df.iterrows():
                rows.append({
                    "trade_date": str(r["日期"]),
                    "pe": float(r["静态市盈率"]) if pd.notna(r.get("静态市盈率")) else None,
                    "pb": None,
                    "dividend_yield": None,
                })
        if pb_df is not None:
            pb_map = {}
            for _, r in pb_df.iterrows():
                pb_map[str(r["日期"])] = float(r["市净率"]) if pd.notna(r.get("市净率")) else None
            for row in rows:
                row["pb"] = pb_map.get(row["trade_date"])
            for dt, pb_val in pb_map.items():
                if not any(r["trade_date"] == dt for r in rows):
                    rows.append({"trade_date": dt, "pe": None, "pb": pb_val, "dividend_yield": None})

        if not rows:
            # Fallback: csindex
            try:
                cs = ak.stock_zh_index_value_csindex(symbol=idx_code)
                for _, r in cs.iterrows():
                    rows.append({
                        "trade_date": str(r["日期"]),
                        "pe": float(r["市盈率1"]) if pd.notna(r.get("市盈率1")) else None,
                        "pb": None,
                        "dividend_yield": float(r["股息率1"]) if pd.notna(r.get("股息率1")) else None,
                    })
            except Exception:
                pass

        for row in rows:
            row["publish_date"] = row["trade_date"]
            insert_index_valuation(
                conn, index_code=idx_code,
                trade_date=row["trade_date"],
                pe=row["pe"], pb=row["pb"],
                dividend_yield=row["dividend_yield"],
                publish_date=row["publish_date"],
            )
        print(f"→ 入库 {len(rows)} 条")

def seed_etf_info(conn):
    """写入 ETF 元信息。"""
    existing = conn.execute("SELECT COUNT(*) FROM etf_info").fetchone()[0]
    if existing > 0:
        return
    for name, cfg in ASSETS.items():
        insert_etf_info(
            conn, code=cfg["code"], name=name,
            asset_class=cfg["asset_class"],
            factor_group=cfg["factor_group"],
            tracking_index=cfg.get("tracking_index"),
            list_date=None,
        )
    print("ETF 元信息已写入。")

# ── MAIN ──
if __name__ == "__main__":
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    create_tables(conn)
    seed_etf_info(conn)

    print("=" * 50)
    print("导入 ETF 价格...")
    import_etf_prices(conn)
    print()
    print("导入 沪深300 估值...")
    import_hs300_valuation(conn)
    print()
    print("导入 全A(上证50替代) 估值...")
    import_all_market_valuation(conn)
    print()
    print("导入 行业指数估值...")
    import_sector_valuation(conn)
    print()
    conn.commit()
    conn.close()
    print("=" * 50)
    print("数据导入完毕！")
