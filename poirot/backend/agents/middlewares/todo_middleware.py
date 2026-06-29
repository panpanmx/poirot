from __future__ import annotations

from poirot.backend.agents.middlewares.base_middleware import BaseMiddleware, MiddlewarePatch


class TodoMiddleware(BaseMiddleware):
    name = "todo"
    priority = 30
    hook_points = ("before_agent", "after_model")
    read_fields = ("plan", "metadata")
    write_fields = ("metadata",)

    def before_agent(self, state, context):
        if not context.config.runtime.plan_enabled:
            return MiddlewarePatch()
        return MiddlewarePatch(updates={"metadata": {"todo_enabled": True}})
