from __future__ import annotations

import os
from dataclasses import dataclass


class ProviderConfigError(ValueError):
    """Raised when model provider config is missing or invalid."""


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None
    priority: int
    default: bool
    enabled: bool

    def require_api_key(self) -> str:
        if not self.api_key:
            raise ProviderConfigError(f"api_key is empty for provider: {self.provider}")
        return self.api_key


MODEL_PROVIDERS = [
    {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": "https://api.deepseek.com",
        "priority": 10,
        "default": True,
        "enabled": True,
    },
    {
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "base_url": None,
        "priority": 20,
        "default": False,
        "enabled": True,
    },
    {
        "provider": "qwen",
        "model": "qwen-plus",
        "api_key": os.environ.get("QWEN_API_KEY", ""),
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "priority": 30,
        "default": False,
        "enabled": True,
    },
    {
        "provider": "fake",
        "model": "fake-chat",
        "api_key": "",
        "base_url": None,
        "priority": 999,
        "default": False,
        "enabled": True,
    },
]


def select_provider_config(
    provider: str | None = None,
    model: str | None = None,
) -> ProviderConfig:
    candidates = [_to_config(raw) for raw in MODEL_PROVIDERS if raw.get("enabled", True)]
    if provider:
        selected = _find_provider(candidates, provider)
    else:
        defaults = [candidate for candidate in candidates if candidate.default]
        selected = sorted(defaults or candidates, key=lambda item: item.priority)[0]
    if model:
        return ProviderConfig(
            provider=selected.provider,
            model=model,
            api_key=selected.api_key,
            base_url=selected.base_url,
            priority=selected.priority,
            default=selected.default,
            enabled=selected.enabled,
        )
    return selected


def get_provider_config(provider: str) -> ProviderConfig:
    return select_provider_config(provider=provider)


def _find_provider(candidates: list[ProviderConfig], provider: str) -> ProviderConfig:
    for candidate in candidates:
        if candidate.provider == provider:
            return candidate
    raise ProviderConfigError(f"provider not configured: {provider}")


def _to_config(raw: dict[str, object]) -> ProviderConfig:
    return ProviderConfig(
        provider=str(raw["provider"]),
        model=str(raw["model"]),
        api_key=str(raw.get("api_key") or ""),
        base_url=raw.get("base_url") if isinstance(raw.get("base_url"), str) else None,
        priority=int(raw["priority"]),
        default=bool(raw.get("default", False)),
        enabled=bool(raw.get("enabled", True)),
    )
