from __future__ import annotations

from poirot.backend.agents.middlewares.base_middleware import BaseMiddleware, MiddlewarePatch


class SystemContextMiddleware(BaseMiddleware):
    name = "system_context"
    priority = 20
    hook_points = ("before_model",)
    read_fields = ("research_question", "metadata")
    write_fields = ("metadata",)

    def before_model(self, state, context):
        return MiddlewarePatch(
            updates={
                "metadata": {
                    "system_context": {
                        "agent": "Poirot deep research agent",
                        "timezone": context.config.runtime.timezone,
                    }
                }
            }
        )
