"""ToolCallMiddleware — AgentMiddleware no-op 占位（V1: passthrough）。

与 EvidenceMiddleware 职责正交：EvidenceMiddleware 负责证据沉淀，
ToolCallMiddleware 保留为独立工具调用观察扩展位。当前不干预。
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langgraph.runtime import Runtime


class ToolCallMiddleware(AgentMiddleware):
    @override
    def before_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        return None
