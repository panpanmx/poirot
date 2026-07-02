from __future__ import annotations

from langchain_core.tools import BaseTool

from poirot.backend.agents.agent_tools.builtin.ddg_search import web_search_tool


def get_builtin_tools() -> list[BaseTool]:
    """内置工具（优先于 MCP）。

    ddg_search（DuckDuckGo 直调）优先于 freeweb-mcp 的 web_search——无 Node 中间层，失败率低。
    dedupe_by_name 会优先保留 builtin（available.py 中 builtin 先加入列表）。
    """
    return [web_search_tool]

