from __future__ import annotations

from langchain_core.tools import BaseTool

from poirot.backend.agents.agent_tools.builtin.ddg_search import web_search_tool
from poirot.backend.agents.agent_tools.builtin.read_snapshot import read_snapshot


def get_builtin_tools() -> list[BaseTool]:
    """内置工具（优先于 MCP）。dedupe_by_name 优先保留 builtin。"""
    return [web_search_tool, read_snapshot]

