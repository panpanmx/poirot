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


# ---------------------------------------------------------------------------
# 智能路由（deepseek 兜底）
# ---------------------------------------------------------------------------

# 角色路由链：按顺序偏好，链尾恒含 deepseek（兜底）。
MODEL_ROUTES: dict[str, list[str]] = {
    "researcher": ["openai", "qwen", "deepseek"],
    "reporter": ["qwen", "deepseek"],
    "reflection": ["deepseek"],
}

# 无需 api_key 的 provider（如测试用 fake）。
_NO_KEY_PROVIDERS: frozenset[str] = frozenset({"fake"})


def discover_available_providers() -> list[ProviderConfig]:
    """返回 enabled 且 api_key 非空的 provider（fake 等免 key 的除外）。按 priority 升序。"""
    available = [
        _to_config(raw)
        for raw in MODEL_PROVIDERS
        if raw.get("enabled", True)
        and (raw.get("api_key") or raw.get("provider") in _NO_KEY_PROVIDERS)
    ]
    return sorted(available, key=lambda p: p.priority)


def route_chain_for(role: str, providers: list[ProviderConfig]) -> list[ProviderConfig]:
    """按 MODEL_ROUTES[role] 顺序筛 provider；保证 deepseek 在链尾（若可用）。

    - role 未配置 → 默认 ["deepseek"]
    - 链空或尾非 deepseek 且 deepseek 可用 → 追加 deepseek 兜底
    - 无任何可用 → 抛 ProviderConfigError
    """
    route = MODEL_ROUTES.get(role, ["deepseek"])
    by_name = {p.provider: p for p in providers}
    chain = [by_name[name] for name in route if name in by_name]
    if "deepseek" in by_name and (not chain or chain[-1].provider != "deepseek"):
        chain.append(by_name["deepseek"])
    if not chain:
        raise ProviderConfigError(f"no available provider for role: {role}")
    return chain


def build_chat_model(config: ProviderConfig):
    """根据 ProviderConfig 构造 BaseChatModel。provider_config 层公共构造器。"""
    if config.provider not in _NO_KEY_PROVIDERS:
        config.require_api_key()
    if config.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(model=config.model, api_key=config.api_key)
    if config.provider in ("openai", "qwen"):
        from langchain_openai import ChatOpenAI
        kwargs: dict = {"model": config.model, "api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatOpenAI(**kwargs)
    if config.provider == "fake":
        from langchain_core.language_models.fake_chat_models import FakeListChatModel
        return FakeListChatModel(responses=["fake response from fake provider"])
    raise ProviderConfigError(f"unsupported provider: {config.provider}")
