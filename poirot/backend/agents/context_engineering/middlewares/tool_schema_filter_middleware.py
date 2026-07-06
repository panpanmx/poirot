"""ToolSchemaFilterMiddleware — wrap_model_call 接入工具 schema 懒加载能力。

持 ToolSchemaFilter Protocol 实例。先构造 CapabilityContext 调
impl.filter_tools/afilter_tools 处理 request（如移除 deferred schema），
impl 返回 request_override 则用其调 handler，否则原 request 调 handler。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware, ModelCallResult, ModelRequest, ModelResponse

from poirot.backend.agents.context_engineering.protocols import ToolSchemaFilter
from poirot.backend.agents.context_engineering.types import CapabilityContext
from poirot.backend.agents.context_engineering.utilities import token_counter
from poirot.backend.agents.state.types import ThreadState


class ToolSchemaFilterMiddleware(AgentMiddleware):
    """wrap_model_call 接入 ToolSchemaFilter 能力。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, impl: ToolSchemaFilter, config: Any = None) -> None:
        self._impl = impl
        self._config = config

    def _ctx(self, request: ModelRequest) -> CapabilityContext:
        runtime = getattr(request, "runtime", None)
        state = getattr(runtime, "state", None) or {}
        return CapabilityContext(
            state=state,
            governance=state.get("governance"),
            config=self._config,
            token_counter=token_counter,
            runtime=runtime,
            messages=getattr(request, "messages", None) or [],
            tools=getattr(request, "tools", None),
            model_request=request,
        )

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        cap = self._impl.filter_tools(self._ctx(request))
        req = cap.request_override if cap.request_override is not None else request
        return handler(req)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        cap = await self._impl.afilter_tools(self._ctx(request))
        req = cap.request_override if cap.request_override is not None else request
        return await handler(req)
