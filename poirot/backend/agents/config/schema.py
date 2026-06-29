from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RunMode = Literal["fast", "general", "expert"]


@dataclass(frozen=True)
class RuntimeConfig:
    mode: RunMode
    default_mode: RunMode = "general"
    timezone: str = "Asia/Shanghai"
    max_loop_steps: int = 4
    timeout_seconds: int = 120
    output_root: str = ".poirot"
    logs_root: str = ".poirot/logs"
    plan_enabled: bool = True
    reflection_enabled: bool = False


@dataclass(frozen=True)
class ModelConfig:
    researcher_model: str
    reporter_model: str


@dataclass(frozen=True)
class ToolConfig:
    web_search_mcp: str = "fake"
    tool_search_default: bool = True


@dataclass(frozen=True)
class MiddlewareConfig:
    enabled: tuple[str, ...] = field(default_factory=tuple)
    summarization: bool = False
    todo: bool = False
    title: bool = False


@dataclass(frozen=True)
class ReportingConfig:
    save_artifact: bool = True
    artifact_format: str = "markdown"


@dataclass(frozen=True)
class ObservabilityConfig:
    event_log_enabled: bool = True
    log_level: str = "INFO"


@dataclass(frozen=True)
class AppConfig:
    name: str
    environment: str
    runtime: RuntimeConfig
    models: ModelConfig
    tools: ToolConfig
    middleware: MiddlewareConfig
    reporting: ReportingConfig
    observability: ObservabilityConfig
