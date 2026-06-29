from poirot.backend.agents.capabilities.models.chat_adapters import FakeChatAdapter


def test_fake_chat_adapter_streams_words() -> None:
    adapter = FakeChatAdapter(response="hello world")

    assert list(adapter.stream("ignored")) == ["hello", " ", "world"]
    assert adapter.invoke("ignored") == "hello world"
