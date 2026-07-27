"""StallDetectionMiddleware — detect agent dead-ends and pause for help.

after_model: record todo state, check stuck → pause graph.
wrap_tool_call: record tool failures, check stuck → pause graph.

Pause = return Command(goto=END) with a synthetic ToolMessage so the
message history stays well-formed (dangling calls patched on resume by
DanglingToolCallMiddleware).
"""

from __future__ import annotations

import time
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.types import Command

from poirot.backend.agents.middlewares.run_journal_middleware import _get_runtime_value
from poirot.backend.agents.observability.interrupt_protection import (
    is_interrupt_protected,
)
from poirot.backend.agents.observability.stall_tracker import StallTracker
from poirot.backend.agents.state.types import ThreadState


class StallDetectionMiddleware(AgentMiddleware):
    """Pause the graph when StallTracker detects a dead-end."""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, max_help_requests: int = 3) -> None:
        self._trackers: dict[str, StallTracker] = {}
        self._help_counts: dict[str, int] = {}
        self._max_help = max_help_requests

    def _get_tracker(self, runtime: Runtime) -> StallTracker:
        run_id = _get_runtime_value(runtime, "run_id", None) or "default"
        if run_id not in self._trackers:
            self._trackers[run_id] = StallTracker()
        return self._trackers[run_id]

    def _help_count(self, runtime: Runtime) -> int:
        run_id = _get_runtime_value(runtime, "run_id", None) or "default"
        return self._help_counts.get(run_id, 0)

    def _increment_help(self, runtime: Runtime) -> None:
        run_id = _get_runtime_value(runtime, "run_id", None) or "default"
        self._help_counts[run_id] = self._help_counts.get(run_id, 0) + 1

    def _check_stuck_and_pause(
        self, state: ThreadState, runtime: Runtime, tool_call_id: str | None = None,
    ) -> Command | None:
        tracker = self._get_tracker(runtime)
        if not tracker.stuck:
            return None

        if is_interrupt_protected():
            return None

        if self._help_count(runtime) >= self._max_help:
            return self._force_finalize(state, runtime, tracker)

        self._increment_help(runtime)
        journal = _get_runtime_value(runtime, "journal", None)
        run_id = _get_runtime_value(runtime, "run_id", None)
        reason = tracker.get_stuck_reason() or "unknown"
        if journal is not None:
            journal.append("help.requested", {
                "run_id": run_id, "reason": reason, "failures": len(tracker.get_failures()),
            })

        update: dict[str, Any] = {"messages": [HumanMessage(
            content=f"[STALL DETECTED] {reason}. Pausing for user help.",
            name="stall_detection",
            additional_kwargs={"hide_from_ui": True},
        )]}
        if tool_call_id:
            update["messages"].insert(0, ToolMessage(
                content=f"Tool paused: stall detected ({reason})",
                tool_call_id=tool_call_id, name="stall_detection",
            ))
        tracker.reset()
        return Command(goto=END, update=update)

    def _force_finalize(
        self, state: ThreadState, runtime: Runtime, tracker: StallTracker,
    ) -> Command:
        journal = _get_runtime_value(runtime, "journal", None)
        run_id = _get_runtime_value(runtime, "run_id", None)
        if journal is not None:
            journal.append("help.exhausted", {"run_id": run_id})
        return Command(goto=END, update={"messages": [HumanMessage(
            content="[HELP EXHAUSTED] Maximum help requests reached. Forcing finalization.",
            name="stall_detection", additional_kwargs={"hide_from_ui": True},
        )]})

    @hook_config(can_jump_to=["__end__"])
    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        tracker = self._get_tracker(runtime)
        todos = state.get("todos") or []
        if todos:
            tracker.record_todo_state(todos)
        result = self._check_stuck_and_pause(state, runtime)
        if result is not None:
            return result.update
        return None

    @hook_config(can_jump_to=["__end__"])
    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        return self.after_model(state, runtime)

    @override
    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        result = handler(request)
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        tool_input = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}
        tool_call_id = tool_call.get("id", "") if isinstance(tool_call, dict) else ""

        if isinstance(result, ToolMessage) and getattr(result, "status", None) == "error":
            runtime = getattr(request, "runtime", None)
            if runtime is not None:
                tracker = self._get_tracker(runtime)
                tracker.record_tool_failure(tool_name, tool_input, str(result.content))
                pause = self._check_stuck_and_pause(
                    getattr(request, "state", None) or {}, runtime, tool_call_id,
                )
                if pause is not None:
                    return pause
        return result

    @override
    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        result = await handler(request)
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        tool_input = tool_call.get("args", {}) if isinstance(tool_call, dict) else ""
        tool_call_id = tool_call.get("id", "") if isinstance(tool_call, dict) else ""

        if isinstance(result, ToolMessage) and getattr(result, "status", None) == "error":
            runtime = getattr(request, "runtime", None)
            if runtime is not None:
                tracker = self._get_tracker(runtime)
                tracker.record_tool_failure(tool_name, tool_input, str(result.content))
                pause = self._check_stuck_and_pause(
                    getattr(request, "state", None) or {}, runtime, tool_call_id,
                )
                if pause is not None:
                    return pause
        return result
