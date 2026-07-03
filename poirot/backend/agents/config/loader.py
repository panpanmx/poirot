from __future__ import annotations

from copy import deepcopy
from typing import Any

from poirot.backend.agents.config.defaults import DEFAULT_CONFIG, EXPERT_PROFILE
from poirot.backend.agents.config.schema import (
    AppConfig,
    MiddlewareConfig,
    ModelConfig,
    ObservabilityConfig,
    ReportingConfig,
    RuntimeConfig,
    ToolConfig,
)


class ConfigError(ValueError):
    """Raised when config cannot be loaded or validated."""


def load_config(
    expert_mode: bool = False,
    cli_overrides: dict[str, Any] | None = None,
) -> AppConfig:
    overrides = cli_overrides or {}
    # expert_mode: cli_overrides 优先，其次参数，最后默认 False
    selected_expert = bool(overrides.get("expert_mode", expert_mode))

    raw = deepcopy(DEFAULT_CONFIG)
    if selected_expert:
        _deep_merge(raw, EXPERT_PROFILE)
    _apply_cli_overrides(raw, overrides)
    _validate(raw)
    return _build_config(raw)


def _apply_cli_overrides(raw: dict[str, Any], overrides: dict[str, Any]) -> None:
    if "expert_mode" in overrides:
        em = overrides["expert_mode"]
        if not isinstance(em, bool):
            raise ConfigError("expert_mode must be a boolean")
        raw["runtime"]["expert_mode"] = em
        if em is True:
            _deep_merge(raw, EXPERT_PROFILE)
        # False 时保持 DEFAULT（不 merge EXPERT_PROFILE）

    flat_targets = {
        "logs_root": ("runtime", "logs_root"),
        "output_root": ("runtime", "output_root"),
        "researcher_model": ("models", "researcher_model"),
        "reporter_model": ("models", "reporter_model"),
        "save_artifact": ("reporting", "save_artifact"),
    }
    for key, path in flat_targets.items():
        if key not in overrides:
            continue
        section, field = path
        raw[section][field] = overrides[key]


def _validate(raw: dict[str, Any]) -> None:
    models = raw["models"]
    if not models.get("researcher_model"):
        raise ConfigError("researcher_model is required")
    if not models.get("reporter_model"):
        raise ConfigError("reporter_model is required")
    if not isinstance(raw["runtime"].get("expert_mode"), bool):
        raise ConfigError("expert_mode must be a boolean")
    if raw["runtime"]["max_loop_steps"] < 1:
        raise ConfigError("max_loop_steps must be greater than zero")
    if not raw["runtime"].get("logs_root"):
        raise ConfigError("logs_root is required")


def _build_config(raw: dict[str, Any]) -> AppConfig:
    return AppConfig(
        name=raw["name"],
        environment=raw["environment"],
        runtime=RuntimeConfig(**raw["runtime"]),
        models=ModelConfig(**raw["models"]),
        tools=ToolConfig(**raw["tools"]),
        middleware=MiddlewareConfig(**raw["middleware"]),
        reporting=ReportingConfig(**raw["reporting"]),
        observability=ObservabilityConfig(**raw["observability"]),
    )


def _deep_merge(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
