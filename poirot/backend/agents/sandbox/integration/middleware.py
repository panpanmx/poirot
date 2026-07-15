from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from poirot.backend.agents.agent_tools.available import SANDBOX_TOOL_NAMES
from poirot.backend.agents.sandbox.contracts import SandboxProvider
from poirot.backend.agents.sandbox.integration.context import (
    get_sandbox_id,
    set_sandbox_id,
)


class SandboxMiddleware(AgentMiddleware):
    """Sandbox 生命周期中间件（只 async，Grill #9）。

    INVARIANT:
    - lazy_init 硬编码 True：无 before_agent，sandbox 工具被调用时 acquire
    - awrap_tool_call：sandbox 工具首次调用时 acquire + set_sandbox_id + Command 持久化
    - aafter_agent release：release 不销毁（LocalSandboxProvider no-op）
    - Sandbox 在中间件列表外层；ToolCall 在内层 catch SandboxError（Grill #9）
    - 非 sandbox 工具（web_search 等）不触发 acquire
    """

    def __init__(self, provider: SandboxProvider) -> None:
        self._provider = provider

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")

        if tool_name not in SANDBOX_TOOL_NAMES:
            return await handler(request)

        sandbox_id = get_sandbox_id()
        first_acquire = sandbox_id is None

        if first_acquire:
            config = getattr(request.runtime, "config", None) or {}
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            thread_id = configurable.get("thread_id")
            if thread_id is None:
                raise SandboxRuntimeError(
                    "thread_id missing in runtime config (sandbox acquire requires thread_id)"
                )
            sandbox_id = self._provider.acquire(thread_id)
            set_sandbox_id(sandbox_id)

        result = await handler(request)

        if first_acquire and isinstance(result, ToolMessage):
            return Command(
                update={
                    "sandbox": {"sandbox_id": sandbox_id},
                    "messages": [result],
                }
            )
        return result

    async def aafter_agent(
        self, state: dict[str, Any], runtime: Runtime
    ) -> None:
        sandbox_state = state.get("sandbox")
        if sandbox_state and sandbox_state.get("sandbox_id"):
            self._provider.release(sandbox_state["sandbox_id"])
