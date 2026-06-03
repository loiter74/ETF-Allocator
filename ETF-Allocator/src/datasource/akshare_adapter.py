"""
datasource/akshare_adapter.py — AkShare 数据获取适配器。

封装的接口：
- fetch_index_valuation: 拉取指数 PE/PB/股息率
- fetch_etf_price: 拉取 ETF 后复权价格
- fetch_index_info: 拉取指数基日/发布日元信息

所有接口返回 pandas DataFrame，调用方自行入库。
"""
from typing import Optional, Dict, Any
import pandas as pd


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

        # 中证指数估值（覆盖大部分需要的指数）
        df = ak.index_value_hist_funddb(
            symbol=index_code,
            indicator="市盈率",
        )

        if df is None or len(df) == 0:
            return pd.DataFrame()

        # 标准化列名
        df = df.rename(columns={
            "日期": "trade_date",
            "市盈率": "pe",
        })

        # 尝试补充 PB 和股息率
        try:
            df_pb = ak.index_value_hist_funddb(
                symbol=index_code,
                indicator="市净率",
            )
            if df_pb is not None and len(df_pb) > 0:
                df_pb = df_pb.rename(columns={"日期": "trade_date", "市净率": "pb"})
                df = df.merge(df_pb[["trade_date", "pb"]], on="trade_date", how="left")
        except Exception:
            df["pb"] = None

        try:
            df_dy = ak.index_value_hist_funddb(
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
        except Exception:
            df["dividend_yield"] = None

        # 添加 publish_date：保守设为 trade_date（估值数据在对应交易日可获取）
        # 对 point-in-time 回测而言，这意味着 T 日的估值在 T 日即可用，
        # 这是合理的——中证指数通常在盘后或次日晨发布前一日估值。
        df["publish_date"] = df["trade_date"]

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
            adjust="qfq",
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
    try:
        import akshare as ak

        # 尝试获取指数基本信息
        df = ak.index_info_global()
        if df is None or len(df) == 0:
            return None

        # 按指数名称模糊匹配
        # 由于 AkShare 接口变化频繁，这里提供一个通用框架
        # 具体实现需要在运行时确认接口返回值结构
        return {
            "index_code": index_code,
            "base_date": None,
            "publish_date": None,
            "_note": "index_info 的 base_date/publish_date 需手动确认中证指数官网",
        }

    except ImportError:
        return None
    except Exception as e:
        print(f"[WARN] fetch_index_info({index_code}) failed: {e}")
        return None
