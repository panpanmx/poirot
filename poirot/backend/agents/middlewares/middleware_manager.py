from __future__ import annotations

from typing import Any

from poirot.backend.agents.middlewares.base_middleware import (
    BaseMiddleware,
    MiddlewarePatch,
    MiddlewareViolationError,
)
from poirot.backend.agents.state.reducers import merge_thread_state


class MiddlewareManager:
    def __init__(self, middlewares: list[BaseMiddleware]) -> None:
        self.middlewares = sorted(
            [middleware for middleware in middlewares if middleware.enabled],
            key=lambda middleware: middleware.priority,
        )

    def run_hook(self, hook_name: str, state: dict[str, Any], context: Any) -> dict[str, Any]:
        current = dict(state)
        for middleware in self.middlewares:
            if hook_name not in middleware.hook_points:
                continue
            try:
                patch = getattr(middleware, hook_name)(current, context)
                self._validate_patch(middleware, patch)
                current = merge_thread_state(current, patch.updates)
                for event_type, payload in patch.events:
                    context.journal.append(event_type, payload)
            except Exception as exc:
                context.journal.append(
                    "middleware.failed",
                    {"middleware": middleware.name, "error": str(exc)},
                )
                raise
        return current

    def _validate_patch(self, middleware: BaseMiddleware, patch: MiddlewarePatch) -> None:
        allowed = set(middleware.write_fields)
        for field in patch.updates:
            if field not in allowed:
                raise MiddlewareViolationError(
                    f"{middleware.name} not allowed to write field: {field}"
                )
