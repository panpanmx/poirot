from __future__ import annotations

from poirot.backend.agents.middlewares.base_middleware import BaseMiddleware


class ToolCallMiddleware(BaseMiddleware):
    name = "tool_call"
    priority = 40
    hook_points = ("before_tool", "after_tool")
    read_fields = ("current_step_id",)
    write_fields = ("observations", "sources", "errors")
