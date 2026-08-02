"""
config/secrets.py — 统一的敏感配置加载入口。

优先级（高 → 低）：
  1. 进程已有的环境变量（`set TUSHARE_TOKEN=xxx` 仍然有效，且优先级最高）
  2. `ETF-Allocator/.env` 文件

设计要点：
  - `.env` 查找从「调用方脚本所在目录」起向上最多 4 层，找到项目根 `ETF-Allocator/.env`
    为止，因此无论从仓库哪个子目录运行脚本都能命中同一个文件。
  - `load_dotenv(override=False)`：环境变量已存在时不覆盖，保证 CI / 临时 `set`
    的值优先于 `.env`，行为与改造前完全一致。
  - `.env` 已被根 `.gitignore` 忽略（"Sensitive" 段），不会进版本库。

用法：
    from config.secrets import get_tushare_token
    TOKEN = get_tushare_token()   # 缺失时直接 sys.exit 并给出中文提示
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _find_env_file() -> Path | None:
    """
    定位 `ETF-Allocator/.env`。

    查找顺序：
      1. 从调用方（import 本模块的脚本）的 __file__ 所在目录起，逐级向上最多 4 层；
      2. 若调用方 __file__ 不可得，退化为从 cwd 起向上找。

    返回首个命中的 `.env` 路径；都找不到则返回 None（交由 load_dotenv 静默跳过）。
    """
    import inspect

    start_dirs: list[Path] = []
    # 倒序跳过本文件这一帧，取真正调用方的源码路径
    for frame in inspect.stack()[1:]:
        frame_file = frame.filename
        if frame_file and frame_file != __file__ and frame_file != "<frozen importlib._bootstrap>":
            start_dirs.append(Path(frame_file).resolve().parent)
            break
    start_dirs.append(Path.cwd())

    for start in start_dirs:
        for depth in range(5):  # 向上最多 4 层（含起始层）
            candidate = start.parents[depth - 1] if depth > 0 else start
            env_path = candidate / ".env"
            if env_path.is_file():
                return env_path
    return None


def get_tushare_token() -> str:
    """
    读取 Tushare Pro token。

    来源：环境变量 `TUSHARE_TOKEN`（优先）或 `.env` 中的同名键。
    缺失时打印提示并 sys.exit(1)，与历史脚本行为完全一致。
    """
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        sys.exit(
            "错误：未设置 TUSHARE_TOKEN。请到 Tushare Pro 个人主页获取 token，"
            "写入 ETF-Allocator/.env（参考 .env.example）或用 "
            "`set TUSHARE_TOKEN=xxx` 设置环境变量后重试。"
        )
    return token


# 模块导入时加载一次即可；找不到 .env 是合法情况（用纯环境变量）。
# 必须放在 _find_env_file 定义之后（依赖该函数定位 .env）。
load_dotenv(_find_env_file(), override=False)
