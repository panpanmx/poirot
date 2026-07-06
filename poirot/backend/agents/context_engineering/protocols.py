"""5 策略 capability Protocol + MemorySink 接口位。

每能力 Protocol 定义 sync + ``a`` 前缀 async 方法对。middleware class 持有
Protocol 实例，hook 内构造 CapabilityContext 调用。实现可替换，middleware 不变。

能力与 hook 映射：
- Compressor        → before_model（历史压缩）
- Externalizer      → wrap_tool_call（单结果外化）
- ToolSchemaFilter  → wrap_model_call（工具 schema 懒加载）
- BudgetGuard       → after_model（单 run 软预算警告）
- MemoryInjector    → before_agent（memory 注入）
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from poirot.backend.agents.context_engineering.types import CapabilityContext, CapabilityResult


@runtime_checkable
class Compressor(Protocol):
    def compress(self, ctx: CapabilityContext) -> CapabilityResult: ...
    async def acompress(self, ctx: CapabilityContext) -> CapabilityResult: ...


@runtime_checkable
class Externalizer(Protocol):
    def externalize(self, ctx: CapabilityContext) -> CapabilityResult: ...
    async def aexternalize(self, ctx: CapabilityContext) -> CapabilityResult: ...


@runtime_checkable
class ToolSchemaFilter(Protocol):
    def filter_tools(self, ctx: CapabilityContext) -> CapabilityResult: ...
    async def afilter_tools(self, ctx: CapabilityContext) -> CapabilityResult: ...


@runtime_checkable
class BudgetGuard(Protocol):
    """单 run 软预算警告（after_model）。硬底线剥 tool_calls 属公共 BudgetHardStop，不在此。"""

    def guard(self, ctx: CapabilityContext) -> CapabilityResult: ...
    async def aguard(self, ctx: CapabilityContext) -> CapabilityResult: ...


@runtime_checkable
class MemoryInjector(Protocol):
    def inject(self, ctx: CapabilityContext) -> CapabilityResult: ...
    async def ainject(self, ctx: CapabilityContext) -> CapabilityResult: ...


@runtime_checkable
class MemorySink(Protocol):
    """短期治理层与长期记忆层的边界接口。

    Compressor 压缩丢弃消息前调 flush，将消息移交长期记忆层。
    """

    def flush(self, messages_to_drop: list) -> None: ...
    async def aflush(self, messages_to_drop: list) -> None: ...
