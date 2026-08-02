"""config/secrets.py — 统一的 Tushare token 入口。

Token 写在 `ETF-Allocator/.env`（已 gitignore，不入库；参考 .env.example）。
模块导入时用 python-dotenv 自动从调用方目录起向上查找并加载 .env。

用法：
    from config.secrets import get_tushare_token
    TOKEN = get_tushare_token()   # 缺失时 sys.exit 报中文错
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)


def get_tushare_token() -> str:
    """读取 TUSHARE_TOKEN；缺失则 sys.exit(1) 并给出中文提示。"""
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        sys.exit(
            "错误：未设置 TUSHARE_TOKEN。请到 Tushare Pro 个人主页获取 token，"
            "写入 ETF-Allocator/.env（参考 .env.example）后重试。"
        )
    return token
