from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModelCapability(Protocol):
    name: str

    def generate(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class FakeModel:
    name: str
    response: str = "fake model response"

    def generate(self, prompt: str) -> str:
        return self.response
