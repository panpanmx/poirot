from __future__ import annotations

from poirot.backend.agents.capabilities.models.chat_adapters import (
    DeepSeekChatAdapter,
    FakeChatAdapter,
    OpenAIChatAdapter,
)
from poirot.backend.agents.config.provider_config import ProviderConfig


def create_chat_adapter(config: ProviderConfig):
    if config.provider == "fake":
        return FakeChatAdapter()
    if config.provider == "deepseek":
        return DeepSeekChatAdapter(config)
    if config.provider == "openai":
        return OpenAIChatAdapter(config)
    if config.provider == "qwen":
        return OpenAIChatAdapter(config)
    raise ValueError(f"Unsupported provider: {config.provider}")
