"""Memory bootstrap lifecycle — get/reset/shutdown/set + 反射加载 + journal 注入。

承接 `design_docs/53-memory-l4-middleware-bootstrap.md` §4 Step 2。

lifecycle 4 函数（参照 deer-flow SandboxProvider 模式）：
- get_memory_provider(): 懒加载 + 双检锁 + 反射 config.use
- reset_memory_provider(): 清缓存不关（测试用）
- shutdown_memory_provider(): 关 + 清（hasattr duck-type 委托 store/retriever）
- set_memory_provider(p): 注入（测试用）

_load_memory_provider: 调 build_default_provider(L3 完整版) + journal 注入。
_wrap_store: 装饰器模式，5B 增量索引触发（Batch 3 加）。

INVARIANT：
- 懒加载双检锁：get_memory_provider 线程安全
- shutdown duck-type：hasattr(provider, "shutdown") 委托 store/retriever
- config.use="" 返 None（记忆禁用）
- import 防火墙：bootstrap.py 不 import app
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from poirot.backend.agents.memory.config import get_memory_config

logger = logging.getLogger(__name__)

_provider_lock = threading.Lock()
_memory_provider: Any = None


def get_memory_provider() -> Any:
    """懒加载 + 双检锁 + 反射 config.use。None 时返 None（记忆禁用）。

    第一次检查无锁（快速路径），第二次检查有锁（防并发）。
    """
    global _memory_provider
    if _memory_provider is not None:
        return _memory_provider
    with _provider_lock:
        if _memory_provider is not None:
            return _memory_provider
        config = get_memory_config()
        if not config.use:
            return None  # 记忆禁用
        provider = _load_memory_provider(config)
        _memory_provider = provider
        return provider


def reset_memory_provider() -> None:
    """清缓存不关（测试用）。"""
    global _memory_provider
    with _provider_lock:
        _memory_provider = None


def shutdown_memory_provider() -> None:
    """关 + 清（hasattr duck-type 委托 store/retriever）。"""
    global _memory_provider
    with _provider_lock:
        if _memory_provider is not None:
            if hasattr(_memory_provider, "shutdown"):
                _memory_provider.shutdown()
            _memory_provider = None


def set_memory_provider(provider: Any) -> None:
    """注入（测试用）。"""
    global _memory_provider
    with _provider_lock:
        _memory_provider = provider


def _load_memory_provider(config: Any) -> Any:
    """反射加载 + build_default_provider + journal 注入。

    L3 完整版：build_default_provider(store/retriever 从 config 实例化)。
    journal 注入：_make_journal_callback（RunJournal 可用时 lambda，不可用时 None）。
    _wrap_store（5B 增量索引）在 Batch 3 加。
    """
    from poirot.backend.agents.memory.strategies.default.strategy import (
        build_default_provider,
    )

    journal = _make_journal_callback()
    provider = build_default_provider(journal=journal)
    # _wrap_store(provider.store(), provider.retriever())  # Batch 3 加
    return provider


def _make_journal_callback() -> Any:
    """Layer 4 注入 RunJournal（L2 manager emit memory.* 事件）。

    RunJournal 可用时返 lambda（调 journal.append(event, payload)）；
    不可用时返 None（不发事件）。
    """
    try:
        from poirot.backend.agents.journal import get_run_journal

        journal = get_run_journal()
        if journal is None:
            return None
        return lambda event, payload: journal.append(event, payload)
    except Exception as exc:
        logger.debug("RunJournal unavailable, memory journal events disabled: %s", exc)
        return None
