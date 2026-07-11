"""Audit or migrate SQLite date columns to canonical ISO text.

Dry-run is the default. Use ``--apply`` to create a timestamped backup and
rewrite affected tables in one transaction.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.store.normalization import normalize_dividend_yield, normalize_iso_date

DEFAULT_DB = PROJECT_ROOT / "data" / "db" / "etf_data.db"


def _rows(conn: sqlite3.Connection, table: str) -> list[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(f"SELECT rowid, * FROM {table}")]


def audit(conn: sqlite3.Connection) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "tables": {}, "invalid": [], "canonical_duplicates": {},
        "suspect_etf_price_rows": 0,
    }
    date_columns = {
        "index_info": ("base_date", "publish_date"),
        "etf_info": ("list_date",),
        "index_valuation": ("trade_date", "publish_date"),
        "etf_price": ("trade_date",),
        "etf_factor": ("calc_date",),
    }
    key_columns = {
        "index_info": ("index_code",),
        "etf_info": ("code",),
        "index_valuation": ("index_code", "trade_date"),
        "etf_price": ("code", "trade_date"),
        "etf_factor": ("code", "calc_date", "factor_name"),
    }
    for table, columns in date_columns.items():
        rows = _rows(conn, table)
        non_text = 0
        canonical_keys: Dict[Tuple[Any, ...], int] = {}
        for row in rows:
            normalized = dict(row)
            for col in columns:
                value = row.get(col)
                if value is None and col == "list_date":
                    continue
                if not isinstance(value, str) or len(value) != 10:
                    non_text += 1
                try:
                    normalized[col] = normalize_iso_date(value, allow_none=(col == "list_date"))
                except ValueError as exc:
                    result["invalid"].append({"table": table, "rowid": row["rowid"], "column": col, "error": str(exc)})
            key = tuple(normalized.get(col) for col in key_columns[table])
            canonical_keys[key] = canonical_keys.get(key, 0) + 1
        duplicates = sum(count - 1 for count in canonical_keys.values() if count > 1)
        result["tables"][table] = {"rows": len(rows), "non_canonical_dates": non_text}
        result["canonical_duplicates"][table] = duplicates
    result["suspect_etf_price_rows"] = conn.execute(
        "SELECT COUNT(*) FROM etf_price WHERE code NOT LIKE '16%' AND volume IS NULL"
    ).fetchone()[0]
    return result


def _merge_rows(rows: Iterable[Dict[str, Any]], key_columns: Tuple[str, ...]) -> list[Dict[str, Any]]:
    merged: "OrderedDict[Tuple[Any, ...], Dict[str, Any]]" = OrderedDict()
    for row in rows:
        row.pop("rowid", None)
        key = tuple(row[col] for col in key_columns)
        if key not in merged:
            merged[key] = row
            continue
        current = merged[key]
        for col, value in row.items():
            if value is not None:
                current[col] = value
    return list(merged.values())


def migrate(conn: sqlite3.Connection) -> Dict[str, int]:
    data: Dict[str, list[Dict[str, Any]]] = {}

    info = _rows(conn, "index_info")
    for row in info:
        row["base_date"] = normalize_iso_date(row["base_date"])
        row["publish_date"] = normalize_iso_date(row["publish_date"])
    data["index_info"] = _merge_rows(info, ("index_code",))

    etfs = _rows(conn, "etf_info")
    for row in etfs:
        row["list_date"] = normalize_iso_date(row["list_date"], allow_none=True)
    data["etf_info"] = _merge_rows(etfs, ("code",))

    vals = _rows(conn, "index_valuation")
    for row in vals:
        row["trade_date"] = normalize_iso_date(row["trade_date"])
        row["publish_date"] = normalize_iso_date(row["publish_date"])
        row["dividend_yield"] = normalize_dividend_yield(row["dividend_yield"])
    data["index_valuation"] = _merge_rows(vals, ("index_code", "trade_date"))

    prices = [
        row for row in _rows(conn, "etf_price")
        if row["code"].startswith("16") or row["volume"] is not None
    ]
    for row in prices:
        row["trade_date"] = normalize_iso_date(row["trade_date"])
    data["etf_price"] = _merge_rows(prices, ("code", "trade_date"))

    factors = _rows(conn, "etf_factor")
    for row in factors:
        row["calc_date"] = normalize_iso_date(row["calc_date"])
    data["etf_factor"] = _merge_rows(factors, ("code", "calc_date", "factor_name"))

    conn.execute("BEGIN IMMEDIATE")
    try:
        for table in ("index_valuation", "etf_price", "etf_factor", "etf_info", "index_info"):
            conn.execute(f"DELETE FROM {table}")

        statements = {
            "index_info": "INSERT INTO index_info(index_code,name,base_date,publish_date) VALUES(:index_code,:name,:base_date,:publish_date)",
            "etf_info": "INSERT INTO etf_info(code,name,asset_class,factor_group,tracking_index,list_date) VALUES(:code,:name,:asset_class,:factor_group,:tracking_index,:list_date)",
            "index_valuation": "INSERT INTO index_valuation(index_code,trade_date,pe,pb,dividend_yield,publish_date) VALUES(:index_code,:trade_date,:pe,:pb,:dividend_yield,:publish_date)",
            "etf_price": "INSERT INTO etf_price(code,trade_date,close_adj,volume) VALUES(:code,:trade_date,:close_adj,:volume)",
            "etf_factor": "INSERT INTO etf_factor(code,calc_date,factor_name,raw_value,opportunity_score) VALUES(:code,:calc_date,:factor_name,:raw_value,:opportunity_score)",
        }
        for table, rows in data.items():
            conn.executemany(statements[table], rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {table: len(rows) for table, rows in data.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    before = audit(conn)
    print("Date contract audit:", before)
    if not args.apply:
        conn.close()
        return 1 if before["invalid"] else 0
    if before["invalid"]:
        conn.close()
        print("Migration aborted: invalid dates found.")
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = args.db.with_suffix(args.db.suffix + f".bak-{stamp}")
    shutil.copy2(args.db, backup)
    print(f"Backup: {backup}")
    try:
        counts = migrate(conn)
        after = audit(conn)
    finally:
        conn.close()
    if after["invalid"] or any(v["non_canonical_dates"] for v in after["tables"].values()):
        raise RuntimeError(f"post-migration audit failed: {after}")
    print("Migrated rows:", counts)
    print("Post-migration audit:", after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
