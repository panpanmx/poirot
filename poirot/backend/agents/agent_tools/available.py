from __future__ import annotations

import logging

from langchain_core.tools import BaseTool

from poirot.backend.agents.agent_tools.builtin import get_builtin_tools
from poirot.backend.agents.agent_tools.mcp_loader import load_mcp_tools

logger = logging.getLogger(__name__)

# 工具 group 映射（MVP 名称映射，未来可迁 config tools[].group 字段）。
# core: 基础工具，default + expert 都加载（省上下文）
# deferred: 深度工具，仅 expert 加载
CORE_TOOL_NAMES: set[str] = {"web_search", "browse_page", "read_snapshot"}
SANDBOX_TOOL_NAMES: set[str] = {"bash", "read_file", "write_file", "list_dir", "str_replace"}


def _tool_group(name: str) -> str:
    """工具名 → group。core 白名单内归 core，sandbox 白名单内归 sandbox，其余归 deferred。"""
    if name in CORE_TOOL_NAMES:
        return "core"
    if name in SANDBOX_TOOL_NAMES:
        return "sandbox"
    return "deferred"


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


def get_available_tools(
    groups: list[str] | None = None,
    include_mcp: bool = True,
) -> list[BaseTool]:
    """加载工具，可选按 group 过滤。

    Args:
        groups: group 白名单。None 加载全部；["core"] 只加载核心工具；
                ["core","deferred"] 加载全部（deferred = 非 core 的全部）。
        include_mcp: 是否加载 MCP 工具。
    """
    tools: list[BaseTool] = []
    # builtin 优先加入——dedupe_by_name 保留先入者，故 ddg_search 的 web_search 覆盖 MCP 的
    tools.extend(get_builtin_tools())
    if include_mcp:
        mcp_tools = load_mcp_tools()
        # 过滤被 builtin 取代的 MCP 工具
        mcp_tools = [t for t in mcp_tools if t.name not in _MCP_SEARCH_REPLACED]
        tools.extend(mcp_tools)
    all_tools = dedupe_by_name(tools)

    if groups is None:
        return all_tools

    groups_set = set(groups)
    filtered = [t for t in all_tools if _tool_group(t.name) in groups_set]
    skipped = [t.name for t in all_tools if _tool_group(t.name) not in groups_set]
    if skipped:
        logger.info("tools filtered out by groups=%s: %s", groups, skipped)
    return filtered
