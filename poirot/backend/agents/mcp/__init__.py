"""MCP 管理模块层 — 配置化注册、熔断器、fallback、安全层、审计。

公共 API：config / registry / health / loader / audit / 门面 McpManager。
"""
import os

from poirot.backend.agents.mcp.audit import McpAuditMiddleware
from poirot.backend.agents.mcp.config import (
    McpConfig,
    McpServerConfig,
    load_mcp_config,
)
from poirot.backend.agents.mcp.health import CircuitBreaker
from poirot.backend.agents.mcp.loader import McpLoader
from poirot.backend.agents.mcp.registry import ToolEntry, ToolRegistry

__all__ = [
    "McpConfig",
    "McpServerConfig",
    "load_mcp_config",
    "CircuitBreaker",
    "ToolEntry",
    "ToolRegistry",
    "McpLoader",
    "McpAuditMiddleware",
    "McpManager",
    "build_mcp_manager",
]


class McpManager:
    """MCP 管理门面。聚合 config + registry + loader + audit。

    INVARIANT:
    - bootstrap 构造一次，随 AppRuntime 生命周期
    - load_startup() eager 并行连接，失败不阻塞
    - get_tools(groups) 供 agent 注入
    - get_audit_middleware() 供 middleware 链注入
    - shutdown() 清理连接
    - switch_expert_mode 不重建（只调 get_tools 切 group）
    """

    def __init__(self, config: McpConfig) -> None:
        self._config = config
        self._registry = ToolRegistry(config)
        self._loader = McpLoader(config, self._registry)
        self._audit = McpAuditMiddleware(self._registry, self._loader.sanitizer)

    async def load_startup(self) -> None:
        """eager 并行连接所有 enabled server，失败不阻塞。"""
        await self._loader.load_startup()

    def get_tools(self, groups: list[str]) -> list:
        """按 group 返回工具列表，供 agent 注入。"""
        return self._registry.get_tools_by_group(groups)

    def get_audit_middleware(self) -> McpAuditMiddleware:
        """供 middleware 链注入。"""
        return self._audit

    @property
    def registry(self) -> ToolRegistry:
        """供外化层取 tool_metadata。"""
        return self._registry

    async def shutdown(self) -> None:
        """清理所有连接。"""
        await self._loader.shutdown()


def build_mcp_manager(config_path: str | None = None) -> McpManager | None:
    """从 .env 读开关 + YAML 加载。enabled=false 或无配置返 None。

    读 POIROT_MCP_ENABLED（缺省 false）+ POIROT_MCP_CONFIG_PATH。
    """
    enabled = os.environ.get("POIROT_MCP_ENABLED", "false").lower() == "true"
    if not enabled:
        return None
    config = load_mcp_config(config_path)
    if not config.servers:
        return None
    return McpManager(config)
