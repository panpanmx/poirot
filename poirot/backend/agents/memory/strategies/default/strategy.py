"""默认 MemoryProvider 主入口（组合 store + retriever + manager）。

承接 `Hezao-MemDesign-Docs/poirot/48-memory-l1-base-layer.md` §4 Step 6.3 骨架
+ `49-memory-l2-default-strategies.md` §4 Step 5。

Layer 1：空骨架，build_default_provider() 返 NotImplementedError 占位。
Layer 2（本实现）：部分组装 — 接收 store + retriever 参数注入，组装 manager + decay + forget。
Layer 3：store.py / retriever.py 实现后，bootstrap.py（Layer 4）实例化并注入。

INVARIANT：
- DefaultMemoryProvider frozen dataclass，三组件构造时注入，运行时不可变
- shutdown duck-type：委托 store/retriever（hasattr 检查）
- store/retriever/journal 由调用方注入（Layer 2 测试 mock，Layer 3 后真实实例）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from poirot.backend.agents.memory.memory_manager import MemoryManager
from poirot.backend.agents.memory.memory_provider import MemoryProvider
from poirot.backend.agents.memory.memory_store import MemoryStore
from poirot.backend.agents.memory.retriever import Retriever
from poirot.backend.agents.memory.strategies.default.decay import EbbinghausDecayPolicy
from poirot.backend.agents.memory.strategies.default.forget import CompositeForgetPolicy
from poirot.backend.agents.memory.strategies.default.manager import DefaultMemoryManager


@dataclass(frozen=True)
class DefaultMemoryProvider:
    """默认 MemoryProvider 实现（组合 store + retriever + manager）。

    frozen dataclass，三组件构造时注入，运行时不可变。
    Lifecycle：构造即就绪，shutdown 走 hasattr duck-type（委托给 store/retriever）。
    """

    _store: MemoryStore
    _retriever: Retriever
    _manager: MemoryManager

    def store(self) -> MemoryStore:
        return self._store

    def retriever(self) -> Retriever:
        return self._retriever

    def manager(self) -> MemoryManager:
        return self._manager

    def shutdown(self) -> None:
        """可选 shutdown：委托给 store / retriever（若有）。

        hasattr duck-type：MarkdownFileStore 无 shutdown（纯文件），SQLiteShadowStore 有。
        """
        if hasattr(self._store, "shutdown"):
            self._store.shutdown()
        if hasattr(self._retriever, "shutdown"):
            self._retriever.shutdown()


def build_default_provider(
    *,
    store: MemoryStore,
    retriever: Retriever,
    decay_policy: EbbinghausDecayPolicy | None = None,
    forget_policy: CompositeForgetPolicy | None = None,
    journal: Callable[[str, dict], None] | None = None,
) -> MemoryProvider:
    """组装默认 MemoryProvider（Layer 2 部分组装，store/retriever 注入式）。

    Args:
        store: 持久化后端（Layer 3 MarkdownFileStore / 测试 mock）
        retriever: 检索后端（Layer 3 HybridRetriever / 测试 mock）
        decay_policy: 衰减策略（None 时默认 EbbinghausDecayPolicy）
        forget_policy: 遗忘策略（None 时默认 CompositeForgetPolicy）
        journal: 事件回调（traceability B，None 时不发事件；Layer 4 注入 RunJournal）

    Returns:
        DefaultMemoryProvider（组合三组件）

    Layer 2：store/retriever/journal 由调用方注入（测试用 mock，Layer 3 后用真实实例）。
    Layer 4 bootstrap.py：get_memory_provider() 调此函数，注入 MarkdownFileStore + HybridRetriever + RunJournal。
    """
    decay = decay_policy or EbbinghausDecayPolicy()
    forget = forget_policy or CompositeForgetPolicy(decay)
    manager = DefaultMemoryManager(
        store=store,
        decay_policy=decay,
        forget_policy=forget,
        journal=journal,  # traceability B 透传
    )
    return DefaultMemoryProvider(
        _store=store,
        _retriever=retriever,
        _manager=manager,
    )
