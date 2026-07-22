"""ClaudeCodeRuntime 单测 — CLI 命令构造 + MCP 配置 + 超时 + crash + subprocess mock。"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from poirot.backend.agents.multiagent.exceptions import (
    SpecialistCrashError,
    SpecialistStartupError,
    SpecialistTimeoutError,
)
from poirot.backend.agents.multiagent.runtimes.claude_code_runtime import (
    ClaudeCodeRuntime,
)
from poirot.backend.agents.multiagent.types import SpecialistRequest


def _make_request(**kwargs) -> SpecialistRequest:
    defaults = dict(
        goal="review this code",
        success_criteria="review comments provided",
        context_summary="python project",
        sandbox_id="sb456def",
        artifacts_path="/workspace",
        timeout_seconds=60,
    )
    defaults.update(kwargs)
    return SpecialistRequest(**defaults)


def test_build_command():
    rt = ClaudeCodeRuntime()
    cmd = rt._build_command(_make_request(goal="hello world"))
    assert cmd == ["claude", "--print", "hello world"]


def test_build_mcp_add_command():
    rt = ClaudeCodeRuntime()
    cmd = rt._build_mcp_add_command("sb123")
    assert cmd[0] == "claude"
    assert "mcp" in cmd
    assert "add" in cmd
    assert "poirot_sandbox" in cmd
    assert "--sandbox-id" in cmd
    assert "sb123" in cmd


def test_invoke_success():
    rt = ClaudeCodeRuntime()
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "review output"

    with patch("subprocess.run", return_value=mock_result):
        result = rt.invoke(_make_request())

    assert result.raw_output == "review output"
    assert result.duration_seconds >= 0


def test_invoke_timeout():
    rt = ClaudeCodeRuntime()

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=5)):
        with pytest.raises(SpecialistTimeoutError):
            rt.invoke(_make_request(timeout_seconds=5))


def test_invoke_nonzero_exit():
    rt = ClaudeCodeRuntime()
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error"

    with patch("subprocess.run", return_value=mock_result):
        with pytest.raises(SpecialistCrashError) as exc_info:
            rt.invoke(_make_request())

    assert exc_info.value.details.get("exit_code") == 1


def test_invoke_command_not_found():
    rt = ClaudeCodeRuntime()

    with patch("subprocess.run", side_effect=FileNotFoundError("claude not found")):
        with pytest.raises(SpecialistStartupError, match="claude command not found"):
            rt.invoke(_make_request())


def test_custom_command():
    rt = ClaudeCodeRuntime(command="/usr/local/bin/claude")
    assert rt._command == "/usr/local/bin/claude"


def test_configure_mcp_runs_subprocess():
    rt = ClaudeCodeRuntime()
    mock_result = MagicMock()
    mock_result.returncode = 0

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        rt.configure_mcp("sb789")

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "mcp" in cmd
    assert "add" in cmd
