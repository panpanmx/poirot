"""bench 运行环境公共层：项目根定位、.env 加载、代理、sys.path。

设计约束（探索确认）：
- compaction.jsonl 路径硬编码为相对 CWD（strategy.py:237），skills.db 锚定项目根
  → bench 一律从项目根 CWD 运行，本模块强制 chdir。
- .env 在项目根，load_dotenv 后 bench 可再覆盖 env（override 顺序保证）。
- GitHub/HuggingFace 下载需走代理（127.0.0.1:7897），跑题时不要设（避免影响 API 直连）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# bench/common/env.py → 项目根 = parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_ENV_FILE = PROJECT_ROOT / ".env"
_PROXY = "http://127.0.0.1:7897"


def ensure_project_root() -> Path:
    """校验项目结构并强制 chdir 到项目根 + 把项目根加入 sys.path。

    返回项目根 Path。不满足则抛 RuntimeError（fail-fast，避免数据写错位置）。
    """
    marker = PROJECT_ROOT / "poirot" / "backend" / "app" / "bootstrap.py"
    if not marker.exists():
        raise RuntimeError(
            f"项目结构异常：找不到 {marker}（bench/ 应位于项目根下）"
        )
    os.chdir(PROJECT_ROOT)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    return PROJECT_ROOT


def load_env() -> Path:
    """加载项目根 .env（override=True：.env 覆盖 shell 残留的旧 key）。

    bench 脚本的 env 以 .env 文件为准——shell session 可能残留过期 key
    （如旧 DEEPSEEK_API_KEY），override=True 确保 .env 里的值总是生效。
    """
    from dotenv import load_dotenv

    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=True)
    return _ENV_FILE


def setup_proxy(proxy: str = _PROXY) -> None:
    """仅下载类脚本调用：设置 HTTP(S) 代理 env。"""
    os.environ.setdefault("HTTP_PROXY", proxy)
    os.environ.setdefault("HTTPS_PROXY", proxy)
    os.environ.setdefault("ALL_PROXY", proxy)
    os.environ.setdefault("http_proxy", proxy)
    os.environ.setdefault("https_proxy", proxy)


def clear_proxy() -> None:
    """跑题前调用：清掉代理，避免影响 LLM API 直连。"""
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        os.environ.pop(key, None)


def env_snapshot(prefixes: tuple[str, ...] = ("POIROT_", "DEEPSEEK_", "QWEN_", "OPENAI_")) -> dict[str, str]:
    """把生效的 POIROT_* 等 env 快照写入 report meta（结果可复现）。"""
    return {k: v for k, v in sorted(os.environ.items()) if any(k.startswith(p) for p in prefixes)}


def data_root() -> Path:
    """bench/data 根目录（数据集与运行中间产物，gitignore）。"""
    p = PROJECT_ROOT / "bench" / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def runs_root(part: str) -> Path:
    """bench/data/runs/{part}——每 part 独立 logs_root，避免互相污染。"""
    p = data_root() / "runs" / part
    p.mkdir(parents=True, exist_ok=True)
    return p
