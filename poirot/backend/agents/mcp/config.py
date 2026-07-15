"""MCP 配置层 — YAML 加载 + ${ENV} 插值 + .env 开关。

INVARIANT:
- POIROT_MCP_ENABLED=false（缺省）→ 不加载 MCP，build_mcp_manager 返 None
- POIROT_MCP_CONFIG_PATH 缺省 .poirot/mcp_servers.yaml，相对项目根
- YAML 内 ${VAR} 从宿主 env 插值
- 文件不存在 / 解析失败 → 返空 McpConfig，不抛，logger 降级
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = ".poirot/mcp_servers.yaml"
_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


@dataclass
class McpServerConfig:
    """单个 MCP server 配置。

    transport=stdio → command/args/env
    transport=sse|http → url/headers
    enabled=false → 跳过不连接
    include/exclude → 工具过滤（include 优先）
    """
    name: str
    transport: Literal["stdio", "sse", "http"]
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout: int = 300
    connect_timeout: int = 60
    include_tools: list[str] = field(default_factory=list)
    exclude_tools: list[str] = field(default_factory=list)


@dataclass
class McpConfig:
    """MCP 管理模块顶层配置。

    servers: {name: McpServerConfig}
    fallback_chains: {tool_name: [server:tool, ...]} — 主→备链，熔断器 open 时 fallback
    core_tools: 启动时必加载工具名（避免全量占上下文）
    tool_metadata: {tool_name: {typical_output_tokens, source}} — 供外化层调阈值
    """
    servers: dict[str, McpServerConfig] = field(default_factory=dict)
    fallback_chains: dict[str, list[str]] = field(default_factory=dict)
    core_tools: list[str] = field(default_factory=list)
    tool_metadata: dict[str, dict] = field(default_factory=dict)


def _interpolate_env(value: str) -> str:
    """${VAR} → os.environ[VAR]，未设则原样保留。"""
    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        return os.environ.get(var, match.group(0))
    return _ENV_PATTERN.sub(_replace, value)


def _interpolate_recursive(obj: object) -> object:
    """递归插值 str / list / dict。"""
    if isinstance(obj, str):
        return _interpolate_env(obj)
    if isinstance(obj, list):
        return [_interpolate_recursive(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _interpolate_recursive(v) for k, v in obj.items()}
    return obj


def _parse_server(name: str, raw: dict) -> McpServerConfig:
    """dict → McpServerConfig，字段校验宽松。YAML 空值（env:）解析为 None，defensive 处理。"""
    transport = raw.get("transport", "stdio")
    if transport not in ("stdio", "sse", "http"):
        logger.warning("server %s transport=%s invalid, fallback stdio", name, transport)
        transport = "stdio"
    tools_raw = raw.get("tools") or {}
    return McpServerConfig(
        name=name,
        transport=transport,
        command=raw.get("command"),
        args=list(raw.get("args") or []),
        env=dict(raw.get("env") or {}),
        url=raw.get("url"),
        headers=dict(raw.get("headers") or {}),
        enabled=bool(raw.get("enabled", True)),
        timeout=int(raw.get("timeout", 300)),
        connect_timeout=int(raw.get("connect_timeout", 60)),
        include_tools=list(tools_raw.get("include") or []),
        exclude_tools=list(tools_raw.get("exclude") or []),
    )


def load_mcp_config(config_path: str | None = None) -> McpConfig:
    """从 YAML 加载 McpConfig。

    config_path 缺省走 .env POIROT_MCP_CONFIG_PATH，再缺省 .poirot/mcp_servers.yaml。
    文件不存在 / 解析失败 → 空 McpConfig，不抛。
    """
    if config_path is None:
        config_path = os.environ.get("POIROT_MCP_CONFIG_PATH", _DEFAULT_CONFIG_PATH)
    path = Path(config_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        logger.warning("MCP config not found: %s, skip loading", path)
        return McpConfig()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        logger.error("MCP config parse failed: %s", exc)
        return McpConfig()
    if not isinstance(raw, dict):
        logger.error("MCP config root not dict: %s", type(raw).__name__)
        return McpConfig()
    raw = _interpolate_recursive(raw)
    servers_raw = raw.get("servers") or {}
    servers = {name: _parse_server(name, spec) for name, spec in servers_raw.items() if isinstance(spec, dict)}
    fallback_chains = {k: list(v) for k, v in (raw.get("fallback_chains") or {}).items() if isinstance(v, list)}
    core_tools = list(raw.get("core_tools") or [])
    tool_metadata = {k: dict(v) for k, v in (raw.get("tool_metadata") or {}).items() if isinstance(v, dict)}
    logger.info(
        "MCP config loaded: %d servers, %d fallback_chains, %d core_tools",
        len(servers), len(fallback_chains), len(core_tools),
    )
    return McpConfig(
        servers=servers,
        fallback_chains=fallback_chains,
        core_tools=core_tools,
        tool_metadata=tool_metadata,
    )
