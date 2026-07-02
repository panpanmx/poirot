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


# MCP 工具中移除 search_and_browse——ddg 的 web_search（builtin）取代之，降失败率。
# browse_page / deep_search / get_page_links 等 MCP 工具保留。
_MCP_SEARCH_REPLACED = {"search_and_browse"}


def get_available_tools(include_mcp: bool = True) -> list[BaseTool]:
    tools: list[BaseTool] = []
    # builtin 优先加入——dedupe_by_name 保留先入者，故 ddg_search 的 web_search 覆盖 MCP 的
    tools.extend(get_builtin_tools())
    if include_mcp:
        mcp_tools = load_mcp_tools()
        # 过滤被 builtin 取代的 MCP 工具
        mcp_tools = [t for t in mcp_tools if t.name not in _MCP_SEARCH_REPLACED]
        tools.extend(mcp_tools)
    return dedupe_by_name(tools)
