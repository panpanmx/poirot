"""NoopCapability — 满足任一能力 Protocol 的空实现，返回空 CapabilityResult。

strategy 不需某能力治理时，该能力点挂此实现（registry 名 ``"noop"``）。
"""

from __future__ import annotations

from poirot.backend.agents.context_engineering.registry import register_capability
from poirot.backend.agents.context_engineering.types import CapabilityContext, CapabilityResult


@register_capability("noop")
class NoopCapability:
    """空实现，满足 5 策略 capability Protocol 任一。"""

    def compress(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    async def acompress(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    def externalize(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    async def aexternalize(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    def filter_tools(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    async def afilter_tools(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    def guard(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    async def aguard(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    def inject(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()

    async def ainject(self, ctx: CapabilityContext) -> CapabilityResult:
        return CapabilityResult()
