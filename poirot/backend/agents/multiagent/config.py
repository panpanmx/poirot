"""MultiAgentConfig — multi-agent orchestration configuration.

设计（spec.md bootstrap Requirement + design.md §2）:
- frozen dataclass，enabled=false 默认（opt-in）
- STARTUP_ONLY_FIELDS 标记启动时确定的字段（不可热切换）
- 从 env vars 加载（POIROT_MULTIAGENT_*）
- OrchestrationState + merge_orchestration 在 state/types.py + state/reducers.py（Batch 3 已实现）
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MultiAgentConfig:
    """Multi-agent orchestration configuration.

    enabled=false 时整个 multiagent 模块不装配（lead agent 行为不变）。
    """

    enabled: bool = False
    specialists_use: tuple[str, ...] = ("codex", "claude", "subagent")
    auto_approve: bool = True
    max_concurrent: int = 1
    timeout_seconds: int = 600
    max_steps: int = 50
    subagent_tool_groups: tuple[str, ...] = ("core",)
    subagent_max_steps: int = 20
    subagent_timeout_seconds: int = 300
    metrics_db_path: str = ".poirot/multiagent.db"
    metrics_health_threshold: float = 0.4
    metrics_min_invoked: int = 5


STARTUP_ONLY_FIELDS = frozenset({
    "enabled",
    "specialists_use",
    "metrics_db_path",
})


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "")
    return val.lower() in ("true", "1", "yes")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    val = os.getenv(name, "")
    if not val:
        return default
    return tuple(s.strip() for s in val.split(",") if s.strip())


def load_multiagent_config() -> MultiAgentConfig:
    """Load multiagent config from env vars (POIROT_MULTIAGENT_*)."""
    return MultiAgentConfig(
        enabled=_env_bool("POIROT_MULTIAGENT_ENABLED", False),
        specialists_use=_env_tuple("POIROT_MULTIAGENT_SPECIALISTS", ("codex", "claude", "subagent")),
        auto_approve=_env_bool("POIROT_MULTIAGENT_AUTO_APPROVE", True),
        max_concurrent=_env_int("POIROT_MULTIAGENT_MAX_CONCURRENT", 1),
        timeout_seconds=_env_int("POIROT_MULTIAGENT_TIMEOUT", 600),
        max_steps=_env_int("POIROT_MULTIAGENT_MAX_STEPS", 50),
        subagent_tool_groups=_env_tuple("POIROT_MULTIAGENT_SUBAGENT_TOOL_GROUPS", ("core",)),
        subagent_max_steps=_env_int("POIROT_MULTIAGENT_SUBAGENT_MAX_STEPS", 20),
        subagent_timeout_seconds=_env_int("POIROT_MULTIAGENT_SUBAGENT_TIMEOUT", 300),
        metrics_db_path=os.getenv("POIROT_MULTIAGENT_DB_PATH", ".poirot/multiagent.db"),
        metrics_health_threshold=_env_float("POIROT_MULTIAGENT_HEALTH_THRESHOLD", 0.4),
        metrics_min_invoked=_env_int("POIROT_MULTIAGENT_MIN_INVOKED", 5),
    )
