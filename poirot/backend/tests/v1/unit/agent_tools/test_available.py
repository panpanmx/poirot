from langchain_core.tools import BaseTool, tool

from poirot.backend.agents.agent_tools.available import (
    CORE_TOOL_NAMES,
    _tool_group,
    get_available_tools,
)


class _StubTool(BaseTool):
    """可指定 name 的测试桩工具。"""
    name: str = "stub"
    description: str = "stub tool"

    def _run(self) -> str:
        return "stub"


def _make_tool(name: str) -> BaseTool:
    t = _StubTool()
    t.name = name
    return t


def test_tool_group_core() -> None:
    assert _tool_group("web_search") == "core"
    assert _tool_group("browse_page") == "core"


def test_tool_group_deferred() -> None:
    assert _tool_group("deep_search") == "deferred"
    assert _tool_group("get_page_links") == "deferred"
    assert _tool_group("unknown_tool") == "deferred"


def test_core_tool_names_contains_basics() -> None:
    assert "web_search" in CORE_TOOL_NAMES
    assert "browse_page" in CORE_TOOL_NAMES


def test_get_available_tools_groups_none_returns_all(monkeypatch) -> None:
    fake_tools = [_make_tool("web_search"), _make_tool("deep_search")]
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.get_builtin_tools",
        lambda: [_make_tool("web_search")],
    )
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.load_mcp_tools",
        lambda: [_make_tool("deep_search")],
    )
    result = get_available_tools(groups=None, include_mcp=True)
    assert {t.name for t in result} == {"web_search", "deep_search"}


def test_get_available_tools_groups_core_filters(monkeypatch) -> None:
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.get_builtin_tools",
        lambda: [_make_tool("web_search")],
    )
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.load_mcp_tools",
        lambda: [_make_tool("deep_search"), _make_tool("browse_page")],
    )
    result = get_available_tools(groups=["core"], include_mcp=True)
    assert {t.name for t in result} == {"web_search", "browse_page"}


def test_get_available_tools_groups_core_and_deferred_returns_all(monkeypatch) -> None:
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.get_builtin_tools",
        lambda: [_make_tool("web_search")],
    )
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.load_mcp_tools",
        lambda: [_make_tool("deep_search"), _make_tool("browse_page")],
    )
    result = get_available_tools(groups=["core", "deferred"], include_mcp=True)
    assert {t.name for t in result} == {"web_search", "deep_search", "browse_page"}


def test_get_available_tools_exclude_mcp(monkeypatch) -> None:
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.get_builtin_tools",
        lambda: [_make_tool("web_search")],
    )
    monkeypatch.setattr(
        "poirot.backend.agents.agent_tools.available.load_mcp_tools",
        lambda: [_make_tool("deep_search")],
    )
    result = get_available_tools(groups=None, include_mcp=False)
    assert {t.name for t in result} == {"web_search"}
