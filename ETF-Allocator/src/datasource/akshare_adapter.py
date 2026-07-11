"""
datasource/akshare_adapter.py — AkShare 数据获取适配器。

封装的接口：
- fetch_index_valuation: 拉取指数 PE/PB/股息率
- fetch_etf_price: 拉取 ETF 后复权价格
- fetch_index_info: 拉取指数基日/发布日元信息

所有接口返回 pandas DataFrame，调用方自行入库。
"""
from datetime import timedelta
from typing import Optional, Dict, Any
import pandas as pd

from src.store.normalization import normalize_dividend_yield


KNOWN_INDEX_INFO = {
    "000300": {"name": "沪深300", "base_date": "2004-12-31", "publish_date": "2005-04-08"},
    "000688": {"name": "科创50", "base_date": "2019-12-31", "publish_date": "2020-07-23"},
    "000922": {"name": "中证红利", "base_date": "2004-12-31", "publish_date": "2005-01-04"},
    "000985": {"name": "中证全指", "base_date": "2004-12-31", "publish_date": "2005-08-31"},
    "399986": {"name": "中证银行", "base_date": "2004-12-31", "publish_date": "2013-07-15"},
    "399997": {"name": "中证白酒", "base_date": "2008-12-31", "publish_date": "2015-01-21"},
}


def fetch_index_valuation(index_code: str) -> pd.DataFrame:
    """
    拉取指数估值数据（PE、PB、股息率），附带 publish_date。

    参数:
        index_code: 指数代码，如 '000300'（沪深300）、'399997'（中证白酒）

    返回:
        DataFrame，列包含 trade_date, pe, pb, dividend_yield, publish_date
        如果接口不支持或拉取失败，返回空 DataFrame。

    注：AkShare 不直接提供 publish_date。由于估值数据通常在盘后公布，
    保守起见将 publish_date 设为 trade_date（次日可用），
    在 point-in-time 回测中不会泄漏未来信息。
    """
    try:
        import akshare as ak

        # Prefer the historical FundDB endpoint when available. Newer AkShare
        # releases expose the official CSIndex endpoint instead.
        funddb = getattr(ak, "index_value_hist_funddb", None)
        if funddb is not None:
            df = funddb(symbol=index_code, indicator="市盈率")
        else:
            df = ak.stock_zh_index_value_csindex(symbol=index_code)

        if df is None or len(df) == 0:
            return pd.DataFrame()

        # 标准化列名
        df = df.rename(columns={
            "日期": "trade_date",
            "市盈率": "pe",
            "市盈率1": "pe",
            "股息率1": "dividend_yield",
        })

        # 尝试补充 PB 和股息率
        try:
            if funddb is None:
                raise LookupError("FundDB PB endpoint unavailable")
            df_pb = funddb(
                symbol=index_code,
                indicator="市净率",
            )
            if df_pb is not None and len(df_pb) > 0:
                df_pb = df_pb.rename(columns={"日期": "trade_date", "市净率": "pb"})
                df = df.merge(df_pb[["trade_date", "pb"]], on="trade_date", how="left")
        except Exception:
            df["pb"] = None

        try:
            if "dividend_yield" in df.columns:
                raise LookupError("dividend yield already provided by CSIndex")
            if funddb is None:
                raise LookupError("FundDB dividend endpoint unavailable")
            df_dy = funddb(
                symbol=index_code,
                indicator="股息率",
            )
            if df_dy is not None and len(df_dy) > 0:
                df_dy = df_dy.rename(
                    columns={"日期": "trade_date", "股息率": "dividend_yield"}
                )
                df = df.merge(
                    df_dy[["trade_date", "dividend_yield"]],
                    on="trade_date",
                    how="left",
                )
        except LookupError:
            if "dividend_yield" not in df.columns:
                df["dividend_yield"] = None
        except Exception:
            df["dividend_yield"] = None

        # FundDB does not expose row-level publication timestamps. Treat the
        # valuation as visible on the following calendar day, never on T close.
        trade_dates = pd.to_datetime(df["trade_date"])
        df["trade_date"] = trade_dates.dt.date.astype(str)
        df["publish_date"] = (trade_dates + timedelta(days=1)).dt.date.astype(str)
        if "dividend_yield" in df.columns:
            df["dividend_yield"] = df["dividend_yield"].map(normalize_dividend_yield)

        return df

    except ImportError:
        print("[WARN] akshare not installed")
        return pd.DataFrame()
    except Exception as e:
        print(f"[WARN] fetch_index_valuation({index_code}) failed: {e}")
        return pd.DataFrame()


def fetch_etf_price(etf_code: str) -> pd.DataFrame:
    """
    拉取 ETF/LOF 历史价格（后复权）。

    ETF 用 fund_etf_hist_em（后复权 K 线）。
    LOF 用 fund_open_fund_info_em（累计净值），累计净值等价于后复权价。

    参数:
        etf_code: 代码，如 '510300'（ETF）或 '161725'（LOF）

    返回:
        DataFrame，列包含 trade_date, close_adj, volume
    """
    try:
        import akshare as ak

        # LOF（16xxxx）用累计净值接口
        if etf_code.startswith("16"):
            return _fetch_lof_price(ak, etf_code)

        # ETF 用后复权 K 线
        df = ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date="20000101",
            end_date="20991231",
            adjust="hfq",
        )

        if df is None or len(df) == 0:
            return pd.DataFrame()

        df = df.rename(columns={
            "日期": "trade_date",
            "收盘": "close_adj",
            "成交量": "volume",
        })

        df = df[df["close_adj"] > 0]

        return df[["trade_date", "close_adj", "volume"]]

    except ImportError:
        print("[WARN] akshare not installed")
        return pd.DataFrame()
    except Exception as e:
        print(f"[WARN] fetch_etf_price({etf_code}) failed: {e}")
        return pd.DataFrame()


def _fetch_lof_price(ak, lof_code: str) -> pd.DataFrame:
    """用累计净值作为后复权价（分红已再投资）。"""
    df = ak.fund_open_fund_info_em(symbol=lof_code, indicator="累计净值走势")

    if df is None or len(df) == 0:
        return pd.DataFrame()

    df = df.rename(columns={
        "净值日期": "trade_date",
        "累计净值": "close_adj",
    })

    df = df[df["close_adj"] > 0]
    df["volume"] = None  # 累计净值接口无成交量

    return df[["trade_date", "close_adj", "volume"]]


def fetch_index_info(index_code: str) -> Optional[Dict[str, Any]]:
    """
    拉取指数元信息（基日、发布日）。

    返回:
        dict 包含 base_date 和 publish_date，或 None
    """
    known = KNOWN_INDEX_INFO.get(index_code)
    if known is None:
        return None
    return {"index_code": index_code, **known, "source": "project-verified-metadata"}
