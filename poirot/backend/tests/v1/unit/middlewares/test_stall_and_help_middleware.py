"""Tests for StallDetectionMiddleware and HelpRequestMiddleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

from poirot.backend.agents.middlewares.help_request_middleware import HelpRequestMiddleware
from poirot.backend.agents.middlewares.stall_detection_middleware import (
    StallDetectionMiddleware,
)


def _make_runtime(journal: MagicMock | None = None, run_id: str = "run-1") -> SimpleNamespace:
    return SimpleNamespace(context={"journal": journal or MagicMock(), "run_id": run_id})


class TestHelpRequestMiddleware:
    def test_intercepts_ask_help_and_returns_command_goto_end(self) -> None:
        mw = HelpRequestMiddleware()
        journal = MagicMock()
        request = SimpleNamespace(
            runtime=_make_runtime(journal),
            tool_call={"name": "ask_help", "id": "tc1", "args": {
                "question": "Which DB?", "help_type": "approach_choice",
                "options": ["PostgreSQL", "SQLite"],
            }},
        )
        result = mw.wrap_tool_call(request, lambda r: None)
        assert isinstance(result, Command)
        assert result.goto == "__end__"
        msgs = result.update.get("messages", [])
        assert any("Which DB?" in str(m.content) for m in msgs)
        journal.append.assert_any_call("help.requested", {
            "run_id": "run-1", "help_type": "approach_choice", "question": "Which DB?",
        })

    def test_non_ask_help_calls_handler_normally(self) -> None:
        mw = HelpRequestMiddleware()
        request = SimpleNamespace(
            runtime=_make_runtime(),
            tool_call={"name": "bash", "id": "tc1", "args": {"command": "ls"}},
        )
        expected = ToolMessage(content="ok", tool_call_id="tc1", name="bash")
        result = mw.wrap_tool_call(request, lambda r: expected)
        assert result is expected


class TestStallDetectionMiddleware:
    def test_no_stuck_returns_handler_result(self) -> None:
        mw = StallDetectionMiddleware()
        request = SimpleNamespace(
            runtime=_make_runtime(),
            tool_call={"name": "bash", "id": "tc1", "args": {"command": "ls"}},
        )
        ok = ToolMessage(content="ok", tool_call_id="tc1", name="bash")
        result = mw.wrap_tool_call(request, lambda r: ok)
        assert result is ok

    def test_stuck_after_tool_failure_pauses_graph(self) -> None:
        mw = StallDetectionMiddleware()
        journal = MagicMock()
        runtime = _make_runtime(journal)
        err1 = ToolMessage(content="permission denied", tool_call_id="t1", name="bash", status="error")
        err2 = ToolMessage(content="not found", tool_call_id="t2", name="bash", status="error")

        req1 = SimpleNamespace(runtime=runtime, state={},
            tool_call={"name": "bash", "id": "t1", "args": {"command": "apt install postgresql"}})
        mw.wrap_tool_call(req1, lambda r: err1)

        req2 = SimpleNamespace(runtime=runtime, state={},
            tool_call={"name": "bash", "id": "t2", "args": {"command": "find / -name postgres"}})
        result = mw.wrap_tool_call(req2, lambda r: err2)
        assert isinstance(result, Command)
        assert result.goto == "__end__"

    def test_help_count_limit_forces_finalize(self) -> None:
        mw = StallDetectionMiddleware(max_help_requests=1)
        journal = MagicMock()
        runtime = _make_runtime(journal)

        def _fire_failure(cmd: str, tc_id: str) -> Any:
            err = ToolMessage(content="permission denied", tool_call_id=tc_id, name="bash", status="error")
            req = SimpleNamespace(runtime=runtime, state={},
                tool_call={"name": "bash", "id": tc_id, "args": {"command": cmd}})
            return mw.wrap_tool_call(req, lambda r: err)

        _fire_failure("apt install pg1", "t1")
        result = _fire_failure("apt install pg2", "t2")
        assert isinstance(result, Command)

        _fire_failure("apt install pg3", "t3")
        result = _fire_failure("apt install pg4", "t4")
        assert isinstance(result, Command)
        assert result.goto == "__end__"
        msgs = result.update.get("messages", [])
        assert any("HELP EXHAUSTED" in str(m.content) for m in msgs)
