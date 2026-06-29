from __future__ import annotations

from poirot.backend.agents.middlewares.base_middleware import BaseMiddleware, MiddlewarePatch


class RunJournalMiddleware(BaseMiddleware):
    name = "run_journal"
    priority = 100
    hook_points = (
        "before_agent",
        "after_agent",
        "before_model",
        "after_model",
        "before_tool",
        "after_tool",
    )
    write_fields: tuple[str, ...] = ()

    def before_agent(self, state, context):
        return MiddlewarePatch(events=[("agent.started", {"run_id": context.run_id})])

    def after_agent(self, state, context):
        return MiddlewarePatch(events=[("agent.finished", {"run_id": context.run_id})])

    def before_model(self, state, context):
        return MiddlewarePatch(events=[("llm.request", {"run_id": context.run_id})])

    def after_model(self, state, context):
        return MiddlewarePatch(events=[("llm.response", {"run_id": context.run_id})])

    def before_tool(self, state, context):
        return MiddlewarePatch(events=[("tool.called", {"run_id": context.run_id})])

    def after_tool(self, state, context):
        return MiddlewarePatch(events=[("tool.finished", {"run_id": context.run_id})])
