from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from poirot.backend.agents.agent_tools.available import SANDBOX_TOOL_NAMES
from poirot.backend.agents.artifacts.server import ArtifactServer
from poirot.backend.agents.sandbox.contracts import SandboxProvider
from poirot.backend.agents.sandbox.integration.context import (
    get_sandbox_id,
    set_sandbox_id,
)
from poirot.backend.agents.state.types import Artifact

logger = logging.getLogger(__name__)

_VIRTUAL_PREFIX = "/mnt/poirot/user-data/"


class SandboxMiddleware(AgentMiddleware):
    """Sandbox 生命周期中间件（只 async，Grill #9）。

    INVARIANT:
    - lazy_init 硬编码 True：无 before_agent，sandbox 工具被调用时 acquire
    - awrap_tool_call：sandbox 工具首次调用时 acquire + set_sandbox_id + Command 持久化
    - present_files 调用后：把 virtual path 写入 state.artifacts + 向 ArtifactServer 注册
    - aafter_agent release：release 不销毁（LocalSandboxProvider no-op）
    - Sandbox 在中间件列表外层；ToolCall 在内层 catch SandboxError（Grill #9）
    - 非 sandbox 工具（web_search 等）不触发 acquire
    """

    def __init__(
        self,
        provider: SandboxProvider,
        artifact_server: ArtifactServer | None = None,
        sandbox_root: str | None = None,
    ) -> None:
        self._provider = provider
        self._artifact_server = artifact_server
        self._sandbox_root = sandbox_root

    @staticmethod
    def _emit_sandbox_acquired(sandbox_id: str) -> None:
        """Push sandbox_acquired custom event to stream (real-time, no values-mode wait)."""
        try:
            from langgraph.config import get_stream_writer
            writer = get_stream_writer()
            writer({
                "type": "sandbox_update",
                "content": sandbox_id,
            })
        except Exception:
            logger.debug("Failed to emit sandbox_update custom event", exc_info=True)

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
            self._emit_sandbox_acquired(sandbox_id)

        result = await handler(request)

        # present_files: register artifacts
        if tool_name == "present_files" and self._artifact_server is not None:
            urls = self._register_artifacts(request, sandbox_id)
            if urls and isinstance(result, ToolMessage):
                url_text = "\n".join(f"  {u}" for u in urls)
                content = result.content if isinstance(result.content, str) else str(result.content)
                result = ToolMessage(
                    content=f"{content}\n\nDownload:\n{url_text}",
                    tool_call_id=result.tool_call_id,
                    name=result.name,
                )

        if first_acquire and isinstance(result, ToolMessage):
            return Command(
                update={
                    "sandbox": {"sandbox_id": sandbox_id},
                    "messages": [result],
                }
            )
        return result

    def _register_artifacts(self, request: ToolCallRequest, sandbox_id: str) -> list[str]:
        """Extract virtual paths from present_files args, register to server. Return URLs."""
        args = request.tool_call.get("args", {})
        if isinstance(args, dict):
            paths = args.get("paths", [])
        elif isinstance(args, str):
            paths = []
        else:
            paths = args if isinstance(args, list) else []

        urls: list[str] = []
        for vp in paths:
            if not isinstance(vp, str) or not vp.startswith(_VIRTUAL_PREFIX):
                logger.warning(
                    f"present_files: skipping '{vp}' — must be under {_VIRTUAL_PREFIX}"
                )
                continue
            filename = vp[len(_VIRTUAL_PREFIX):].lstrip("/")
            host_path = f"{self._sandbox_root}/{sandbox_id}/{filename}" if self._sandbox_root else None
            if host_path:
                url = self._artifact_server.register(sandbox_id, filename, host_path)
                urls.append(url)
                logger.info(f"Artifact registered: {url}")
        return urls

    async def aafter_agent(
        self, state: dict[str, Any], runtime: Runtime
    ) -> None:
        sandbox_state = state.get("sandbox")
        if sandbox_state and sandbox_state.get("sandbox_id"):
            self._provider.release(sandbox_state["sandbox_id"])

