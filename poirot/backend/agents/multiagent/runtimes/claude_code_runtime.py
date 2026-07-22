"""ClaudeCodeRuntime — CLI 直接调实现（claude --print 子进程 + stdout 解析）。

设计（spec.md ClaudeCodeRuntime Requirement + design.md §2）:
- sync only MVP（INV#5）
- 不走 ACP（无 Claude Code ACP adapter）
- 配置 claude mcp add 用 Poirot MCP tool（SpecialistMcpServer）
- 超时 kill + crash SpecialistCrashError
- specialist 黑盒：claude CLI 自带 model + 自管 ReAct loop（INV#1/INV#2）
"""
from __future__ import annotations

import subprocess
import time

from poirot.backend.agents.multiagent.exceptions import (
    SpecialistCrashError,
    SpecialistStartupError,
    SpecialistTimeoutError,
)
from poirot.backend.agents.multiagent.types import (
    SpecialistRawResult,
    SpecialistRequest,
)


class ClaudeCodeRuntime:
    """CLI 直接调 runtime（claude --print + stdout 解析）。

    sync only MVP（INV#5）。每次 invoke 启动新进程。
    """

    def __init__(self, command: str = "claude") -> None:
        self._command = command

    def invoke(self, request: SpecialistRequest) -> SpecialistRawResult:
        start = time.time()
        cmd = self._build_command(request)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            raise SpecialistTimeoutError(
                timeout_seconds=request.timeout_seconds,
            )
        except FileNotFoundError:
            raise SpecialistStartupError(
                f"claude command not found: {self._command}"
            )

        if result.returncode != 0:
            raise SpecialistCrashError(
                f"claude exited with code {result.returncode}",
                exit_code=result.returncode,
            )

        return SpecialistRawResult(
            raw_output=result.stdout,
            duration_seconds=time.time() - start,
        )

    def _build_command(self, request: SpecialistRequest) -> list[str]:
        """Build claude --print command with goal as argument."""
        return [self._command, "--print", request.goal]

    def _build_mcp_add_command(self, sandbox_id: str) -> list[str]:
        """Build `claude mcp add` command for SpecialistMcpServer."""
        return [
            self._command,
            "mcp",
            "add",
            "poirot_sandbox",
            "--",
            "python",
            "-m",
            "poirot.backend.agents.multiagent.mcp.specialist_mcp_server",
            "--sandbox-id",
            sandbox_id,
        ]

    def configure_mcp(self, sandbox_id: str) -> None:
        """Run `claude mcp add` to register SpecialistMcpServer.

        Called by specialist before invoke (or by bootstrap).
        """
        cmd = self._build_mcp_add_command(sandbox_id)
        subprocess.run(cmd, capture_output=True, timeout=30)
