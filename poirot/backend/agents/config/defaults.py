from __future__ import annotations

from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "name": "poirot",
    "environment": "local",
    "runtime": {
        "expert_mode": False,
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

# expert 模式叠加层：load_config(expert_mode=True) 时 deep_merge 到 DEFAULT_CONFIG。
# 替代原 fast/general/expert 三 profile（mode 枚举废弃，改 expert_mode: bool 参数化）。
EXPERT_PROFILE: dict[str, Any] = {
    "runtime": {
        "expert_mode": True,
        "max_loop_steps": 8,
        "plan_enabled": True,
        "reflection_enabled": True,
    },
    "tools": {"tool_search_default": True},
    "middleware": {"enabled": ("todo", "summarization"), "todo": True, "summarization": True},
    "reporting": {"save_artifact": True},
}
