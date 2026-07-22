"""CodexRuntime — ACP 协议实现（启动 codex-acp 子进程 + stdio JSON-RPC）。

设计（spec.md CodexRuntime Requirement + design.md §2）:
- sync only MVP：invoke wraps async _run_acp_session via asyncio.run（INV#5）
- 每次启动 + 完成关闭（不做 pool）
- 传 goal + context_summary + MCP config（含 SpecialistMcpServer 命令）
- 超时 kill + crash SpecialistCrashError
- acp 包 lazy import（可选依赖，未装时 SpecialistStartupError）
- specialist 黑盒：codex-acp 自带 model + 自管 ReAct loop（INV#1/INV#2）
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from poirot.backend.agents.multiagent.exceptions import (
    SpecialistCrashError,
    SpecialistError,
    SpecialistStartupError,
    SpecialistTimeoutError,
)
from poirot.backend.agents.multiagent.types import (
    SpecialistRawResult,
    SpecialistRequest,
)


class CodexRuntime:
    """ACP 协议 runtime（codex-acp 子进程 + stdio JSON-RPC）。

    sync only MVP（INV#5）。每次 invoke 启动新进程 + 完成关闭。
    """

    def __init__(
        self,
        command: str = "npx",
        args: tuple[str, ...] = ("-y", "@zed-industries/codex-acp"),
    ) -> None:
        self._command = command
        self._args = args

    def invoke(self, request: SpecialistRequest) -> SpecialistRawResult:
        start = time.time()
        try:
            raw_output = asyncio.run(self._run_acp_session(request))
        except asyncio.TimeoutError:
            raise SpecialistTimeoutError(
                timeout_seconds=request.timeout_seconds,
            )
        except SpecialistError:
            raise
        except FileNotFoundError:
            raise SpecialistStartupError(
                f"codex-acp command not found: {self._command} {' '.join(self._args)}"
            )
        except Exception as e:
            raise SpecialistCrashError(str(e))

        return SpecialistRawResult(
            raw_output=raw_output,
            duration_seconds=time.time() - start,
        )

    async def _run_acp_session(self, request: SpecialistRequest) -> str:
        """Run ACP session via acp package (lazy import)."""
        try:
            from acp import PROTOCOL_VERSION, Client, text_block
            from acp.schema import (
                ClientCapabilities,
                Implementation,
                TextContentBlock,
            )
            from acp import spawn_agent_process
        except ImportError as e:
            raise SpecialistStartupError(
                f"acp package not installed: {e}. Run: pip install agent-client-protocol"
            )

        mcp_servers = self._build_mcp_config(request.sandbox_id)
        chunks: list[str] = []

        class _Collector(Client):
            async def session_update(self, session_id: str, update, **kwargs) -> None:
                try:
                    if hasattr(update, "content") and isinstance(
                        update.content, TextContentBlock
                    ):
                        chunks.append(update.content.text)
                except Exception:
                    pass

        client = _Collector()
        agent_env = self._build_env()

        async with spawn_agent_process(
            client, self._command, *self._args, env=agent_env,
        ) as (conn, proc):
            await conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=Implementation(
                    name="poirot", title="Poirot", version="0.1.0",
                ),
            )
            session_kwargs: dict[str, Any] = {
                "cwd": request.artifacts_path or ".",
                "mcp_servers": mcp_servers,
            }
            session = await conn.new_session(**session_kwargs)
            await asyncio.wait_for(
                conn.prompt(
                    session_id=session.session_id,
                    prompt=[text_block(request.goal)],
                ),
                timeout=request.timeout_seconds,
            )

        return "".join(chunks)

    def _build_mcp_config(self, sandbox_id: str | None) -> list[dict[str, Any]]:
        """Build MCP servers config for ACP new_session (includes SpecialistMcpServer)."""
        if sandbox_id is None:
            return []
        return [
            {
                "name": "poirot_sandbox",
                "type": "stdio",
                "command": "python",
                "args": [
                    "-m",
                    "poirot.backend.agents.multiagent.mcp.specialist_mcp_server",
                    "--sandbox-id",
                    sandbox_id,
                ],
            }
        ]

    def _build_env(self) -> dict[str, str] | None:
        """Pass CODEX_AUTH_PATH to subprocess if set."""
        env: dict[str, str] = {}
        auth_path = os.getenv("CODEX_AUTH_PATH")
        if auth_path:
            env["CODEX_AUTH_PATH"] = auth_path
        return env or None
