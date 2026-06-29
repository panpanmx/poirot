from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ToolCapability(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]

    def invoke(self, tool_input: dict[str, Any], context: Any | None = None) -> Any:
        ...


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source_name: str = "fake"
    published_at: str | None = None


@dataclass(frozen=True)
class FakeSearchTool:
    name: str = "web_search_mcp"
    description: str = "Fake web search tool for deterministic tests."
    input_schema: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.input_schema is None:
            object.__setattr__(
                self,
                "input_schema",
                {"query": "string", "max_results": "integer"},
            )

    def invoke(self, tool_input: dict[str, Any], context: Any | None = None) -> list[SearchResult]:
        query = tool_input.get("query", "")
        return [
            SearchResult(
                title=f"Result for {query}",
                url="https://example.test/search-result",
                snippet=f"Fake search result about {query}",
            )
        ]
