from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class MiddlewareViolationError(ValueError):
    """Raised when middleware returns a patch outside declared permissions."""


@dataclass(frozen=True)
class MiddlewarePatch:
    updates: dict[str, Any] = field(default_factory=dict)
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BaseMiddleware:
    name = "base"
    enabled = True
    priority = 100
    hook_points: tuple[str, ...] = ()
    read_fields: tuple[str, ...] = ()
    write_fields: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()

    def before_agent(self, state: dict[str, Any], context: Any) -> MiddlewarePatch:
        return MiddlewarePatch()

    def after_agent(self, state: dict[str, Any], context: Any) -> MiddlewarePatch:
        return MiddlewarePatch()

    def before_model(self, state: dict[str, Any], context: Any) -> MiddlewarePatch:
        return MiddlewarePatch()

    def after_model(self, state: dict[str, Any], context: Any) -> MiddlewarePatch:
        return MiddlewarePatch()

    def before_tool(self, state: dict[str, Any], context: Any) -> MiddlewarePatch:
        return MiddlewarePatch()

    def after_tool(self, state: dict[str, Any], context: Any) -> MiddlewarePatch:
        return MiddlewarePatch()
