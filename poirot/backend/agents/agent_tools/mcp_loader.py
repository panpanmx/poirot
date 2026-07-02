from __future__ import annotations

import asyncio
import sys
from typing import Any

from langchain_core.tools import BaseTool

from poirot.backend.agents.agent_tools.mcp_metadata import tag_mcp_tool

DEFAULT_MCP_SEARCH_SERVERS: dict[str, Any] = {
    "freeweb": {
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "freeweb-mcp@latest"],
    }
}

_mcp_tools_cache: list[BaseTool] | None = None


async def load_mcp_tools_async() -> list[BaseTool]:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(DEFAULT_MCP_SEARCH_SERVERS)
    tools = await client.get_tools()
    return [tag_mcp_tool(tool) for tool in tools]


def load_mcp_tools() -> list[BaseTool]:
    global _mcp_tools_cache
    if _mcp_tools_cache is not None:
        return _mcp_tools_cache
    try:
        try:
            asyncio.get_running_loop()
            # 已在 async 上下文——新线程跑独立 event loop 加载 MCP
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                _mcp_tools_cache = pool.submit(asyncio.run, load_mcp_tools_async()).result()
        except RuntimeError:
            # 同步上下文——直接 asyncio.run
            _mcp_tools_cache = asyncio.run(load_mcp_tools_async())
    except Exception as exc:
        print(
            f"[Poirot] MCP tool loading failed: {exc}",
            file=sys.stderr,
        )
        _mcp_tools_cache = []
    return _mcp_tools_cache
