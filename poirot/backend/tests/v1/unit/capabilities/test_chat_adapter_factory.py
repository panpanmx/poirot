import pytest

from poirot.backend.agents.capabilities.models.chat_adapter_factory import (
    create_chat_adapter,
)
from poirot.backend.agents.config.provider_config import ProviderConfig


def test_factory_returns_fake_adapter_for_fake_provider() -> None:
    adapter = create_chat_adapter(
        ProviderConfig(
            provider="fake",
            model="fake-chat",
            api_key="",
            base_url=None,
            priority=1,
            default=False,
            enabled=True,
        )
    )

    assert adapter.invoke("hello") == "Fake response for: hello"


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        create_chat_adapter(
            ProviderConfig(
                provider="unknown",
                model="x",
                api_key="key",
                base_url=None,
                priority=1,
                default=False,
                enabled=True,
            )
        )
