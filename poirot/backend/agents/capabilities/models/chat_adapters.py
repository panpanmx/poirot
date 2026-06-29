from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol

from poirot.backend.agents.config.provider_config import ProviderConfig


class ChatModelAdapter(Protocol):
    def invoke(self, prompt: str) -> str:
        ...

    def stream(self, prompt: str) -> Iterator[str]:
        ...


@dataclass(frozen=True)
class FakeChatAdapter:
    response: str | None = None

    def invoke(self, prompt: str) -> str:
        return self.response if self.response is not None else f"Fake response for: {prompt}"

    def stream(self, prompt: str) -> Iterator[str]:
        text = self.invoke(prompt)
        words = text.split(" ")
        for index, word in enumerate(words):
            if index:
                yield " "
            yield word


@dataclass(frozen=True)
class DeepSeekChatAdapter:
    config: ProviderConfig

    def _model(self):
        self.config.require_api_key()
        try:
            from langchain_deepseek import ChatDeepSeek
        except ImportError as exc:
            missing = exc.name or "unknown dependency"
            raise RuntimeError(
                f"Cannot load deepseek provider because dependency is missing: {missing}. "
                'Run `pip install -e ".[dev]"` from the project root.'
            ) from exc
        return ChatDeepSeek(model=self.config.model, api_key=self.config.api_key)

    def invoke(self, prompt: str) -> str:
        return _content_to_text(self._model().invoke(prompt))

    def stream(self, prompt: str) -> Iterator[str]:
        for chunk in self._model().stream(prompt):
            text = _content_to_text(chunk)
            if text:
                yield text


@dataclass(frozen=True)
class OpenAIChatAdapter:
    config: ProviderConfig

    def _model(self):
        self.config.require_api_key()
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            missing = exc.name or "unknown dependency"
            raise RuntimeError(
                f"Cannot load {self.config.provider} provider because dependency is missing: {missing}. "
                'Run `pip install -e ".[dev]"` from the project root.'
            ) from exc
        kwargs = {"model": self.config.model, "api_key": self.config.api_key}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return ChatOpenAI(**kwargs)

    def invoke(self, prompt: str) -> str:
        return _content_to_text(self._model().invoke(prompt))

    def stream(self, prompt: str) -> Iterator[str]:
        for chunk in self._model().stream(prompt):
            text = _content_to_text(chunk)
            if text:
                yield text


def _content_to_text(message: object) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)
