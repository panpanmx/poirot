from __future__ import annotations

from langchain_core.tools import BaseTool

from poirot.backend.agents.agent_tools.builtin import get_builtin_tools
from poirot.backend.agents.agent_tools.mcp_loader import load_mcp_tools


def dedupe_by_name(tools: list[BaseTool]) -> list[BaseTool]:
    seen: set[str] = set()
    result: list[BaseTool] = []
    for tool in tools:
        if tool.name not in seen:
            seen.add(tool.name)
            result.append(tool)
    return result


def select_search_tool(tools: list[BaseTool]) -> BaseTool | None:
    for tool in tools:
        if "search" in tool.name.lower():
            return tool
    return None


def get_available_tools(include_mcp: bool = True) -> list[BaseTool]:
    tools: list[BaseTool] = []
    if include_mcp:
        tools.extend(load_mcp_tools())
    tools.extend(get_builtin_tools())
    return dedupe_by_name(tools)
