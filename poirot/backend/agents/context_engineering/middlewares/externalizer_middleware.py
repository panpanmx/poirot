"""ExternalizerMiddleware — wrap_tool_call 接入单结果外化能力。

持 Externalizer Protocol 实例。先调 handler 取工具结果，再构造
CapabilityContext 调 impl.externalize/aexternalize。impl 返回 request_override
（ToolMessage 或 Command，后者可携带 governance 写入）则替换返回，否则原样返回。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from poirot.backend.agents.context_engineering.protocols import Externalizer
from poirot.backend.agents.context_engineering.types import CapabilityContext
from poirot.backend.agents.context_engineering.utilities import token_counter
from poirot.backend.agents.state.types import ThreadState


class ExternalizerMiddleware(AgentMiddleware):
    """wrap_tool_call 接入 Externalizer 能力。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, impl: Externalizer, config: Any = None) -> None:
        self._impl = impl
        self._config = config

    def _ctx(self, request: ToolCallRequest, result: ToolMessage | Command) -> CapabilityContext:
        runtime = getattr(request, "runtime", None)
        state = getattr(runtime, "state", None) or {}
        return CapabilityContext(
            state=state,
            governance=state.get("governance"),
            config=self._config,
            token_counter=token_counter,
            runtime=runtime,
            messages=state.get("messages") or [],
            tool_call_request=request,
            tool_result=result,
        )

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        result = handler(request)
        cap = self._impl.externalize(self._ctx(request, result))
        return cap.request_override if cap.request_override is not None else result

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        result = await handler(request)
        cap = await self._impl.aexternalize(self._ctx(request, result))
        return cap.request_override if cap.request_override is not None else result
