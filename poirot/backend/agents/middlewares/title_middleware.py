from __future__ import annotations

from poirot.backend.agents.middlewares.base_middleware import BaseMiddleware, MiddlewarePatch


class TitleMiddleware(BaseMiddleware):
    name = "title"
    priority = 90
    hook_points = ("after_agent",)
    read_fields = ("user_input", "research_question")
    write_fields = ("metadata",)

    def after_agent(self, state, context):
        source = state.get("research_question") or state.get("user_input") or "Untitled"
        return MiddlewarePatch(updates={"metadata": {"title": str(source)[:60]}})
