from __future__ import annotations

from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "name": "poirot",
    "environment": "local",
    "runtime": {
        "mode": "general",
        "default_mode": "general",
        "timezone": "Asia/Shanghai",
        "max_loop_steps": 4,
        "timeout_seconds": 120,
        "output_root": ".poirot",
        "logs_root": ".poirot/logs",
        "plan_enabled": True,
        "reflection_enabled": False,
    },
    "models": {
        "researcher_model": "fake-researcher",
        "reporter_model": "fake-reporter",
    },
    "tools": {
        "web_search_mcp": "fake",
        "tool_search_default": True,
    },
    "middleware": {
        "enabled": (),
        "summarization": False,
        "todo": False,
        "title": False,
    },
    "reporting": {
        "save_artifact": True,
        "artifact_format": "markdown",
    },
    "observability": {
        "event_log_enabled": True,
        "log_level": "INFO",
    },
}

MODE_PROFILES: dict[str, dict[str, Any]] = {
    "fast": {
        "runtime": {
            "mode": "fast",
            "max_loop_steps": 1,
            "plan_enabled": False,
            "reflection_enabled": False,
        },
        "tools": {"tool_search_default": False},
        "middleware": {"enabled": (), "todo": False},
        "reporting": {"save_artifact": False},
    },
    "general": {
        "runtime": {
            "mode": "general",
            "max_loop_steps": 4,
            "plan_enabled": True,
            "reflection_enabled": False,
        },
        "tools": {"tool_search_default": True},
        "middleware": {"enabled": ("todo",), "todo": True},
        "reporting": {"save_artifact": True},
    },
    "expert": {
        "runtime": {
            "mode": "expert",
            "max_loop_steps": 8,
            "plan_enabled": True,
            "reflection_enabled": True,
        },
        "tools": {"tool_search_default": True},
        "middleware": {"enabled": ("todo", "summarization"), "todo": True, "summarization": True},
        "reporting": {"save_artifact": True},
    },
}
