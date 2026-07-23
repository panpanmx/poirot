from __future__ import annotations

from langchain_core.tools import BaseTool

from poirot.backend.agents.agent_tools.builtin.ask_help import ask_help_tool
from poirot.backend.agents.agent_tools.builtin.ddg_search import web_search_tool
from poirot.backend.agents.agent_tools.builtin.read_snapshot import read_snapshot


def get_builtin_tools() -> list[BaseTool]:
    """内置工具（优先于 MCP）。dedupe_by_name 优先保留 builtin。

    sandbox 工具（bash/read_file/write_file/list_dir/str_replace）不在此加载——
    由 Stage 4 bootstrap 按需注入：config.sandbox 配了 provider 时调
    make_sandbox_tools(provider) 构造，注入 registry.tools。
    """
    return [web_search_tool, read_snapshot, ask_help_tool]

