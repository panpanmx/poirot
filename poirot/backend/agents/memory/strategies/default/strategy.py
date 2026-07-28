"""默认 MemoryProvider 主入口（组合 store + retriever + manager）。

Layer 1：空骨架，build_default_provider() 返 NotImplementedError 占位（避免误用）。
Layer 2/3：填充 decay + forget + manager + store + retriever 组装。
"""

from __future__ import annotations

from poirot.backend.agents.memory.memory_provider import MemoryProvider


def build_default_provider(*args: object, **kwargs: object) -> MemoryProvider:
    """组装默认 MemoryProvider。

    Layer 1：NotImplementedError 占位（避免误用）。
    Layer 2/3：实例化 MarkdownFileStore + HybridRetriever + DefaultMemoryManager +
              EbbinghausDecayPolicy + CompositeForgetPolicy，组装 DefaultMemoryProvider。
    """
    raise NotImplementedError(
        "build_default_provider is a Layer 2/3 placeholder. "
        "Implement in strategies/default/strategy.py after Layer 2/3."
    )
