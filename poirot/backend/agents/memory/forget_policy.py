"""ForgetPolicy Protocol — 遗忘策略契约。

承接 `Hezao-MemDesign-Docs/poirot/00-long-term-memory-foundation.md` §7.4
+ `48-memory-l1-base-layer.md` §4 Step 5.2。

默认实现：CompositeForgetPolicy（strategies/default/forget.py，Layer 2）。
组合：TTL 过期 + strength 阈值 + 矛盾覆盖。
可替换：TTLOnly / StrengthOnly / ConflictOnly。

INVARIANT: Protocol 纯契约零实现，可 mock 可替换。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from poirot.backend.agents.memory.schema import MemoryTrace


@runtime_checkable
class ForgetPolicy(Protocol):
    """遗忘策略协议（00 §7.4）。

    默认实现 CompositeForgetPolicy（strategies/default/forget.py，Layer 2）。
    组合：TTL 过期 + strength 阈值 + 矛盾覆盖。
    """

    def should_forget(self, trace: MemoryTrace, now: float) -> bool:
        """是否应遗忘该记忆。"""
        ...

    def resolve_conflict(self, old: MemoryTrace, new: MemoryTrace) -> MemoryTrace:
        """矛盾解决：新记忆覆盖旧记忆（返回 new，标记 old 为遗忘）。"""
        ...
