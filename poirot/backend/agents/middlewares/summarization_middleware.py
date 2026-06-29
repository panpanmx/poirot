from __future__ import annotations

from poirot.backend.agents.middlewares.base_middleware import BaseMiddleware


class SummarizationMiddleware(BaseMiddleware):
    name = "summarization"
    priority = 10
    hook_points = ("before_model",)
    read_fields = ("messages", "research_question", "plan", "observations")
    write_fields = ("messages",)
