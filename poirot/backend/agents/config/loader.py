from __future__ import annotations

from copy import deepcopy
from typing import Any

from poirot.backend.agents.config.defaults import DEFAULT_CONFIG, MODE_PROFILES
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
    mode: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AppConfig:
    overrides = cli_overrides or {}
    selected_mode = str(overrides.get("mode") or mode or DEFAULT_CONFIG["runtime"]["default_mode"])
    if selected_mode not in MODE_PROFILES:
        raise ConfigError(f"Unsupported mode: {selected_mode}")

    raw = deepcopy(DEFAULT_CONFIG)
    _deep_merge(raw, MODE_PROFILES[selected_mode])
    _apply_cli_overrides(raw, overrides)
    _validate(raw)
    return _build_config(raw)


def _apply_cli_overrides(raw: dict[str, Any], overrides: dict[str, Any]) -> None:
    mode = overrides.get("mode")
    if mode is not None:
        if mode not in MODE_PROFILES:
            raise ConfigError(f"Unsupported mode: {mode}")
        _deep_merge(raw, MODE_PROFILES[str(mode)])

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
    if raw["runtime"]["mode"] not in MODE_PROFILES:
        raise ConfigError(f"Unsupported mode: {raw['runtime']['mode']}")
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
