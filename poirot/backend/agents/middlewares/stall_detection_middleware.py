"""StallDetectionMiddleware — detect agent dead-ends and pause for help.

after_model: record todo state, check pending stuck flag → pause graph.
wrap_tool_call: record tool failures (including exceptions), set pending
stuck flag if stuck. Does NOT pause from wrap_tool_call to avoid breaking
parallel tool_calls pairing — pause happens in after_model after all
ToolMessages are in place.

Pause = return Command(goto=END) from after_model. DanglingToolCallMiddleware
patches any remaining gaps on resume.
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import HumanMessage, ToolMessage
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
        self._pending_stuck: dict[str, bool] = {}
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

    def _check_and_flag_stuck(
        self, runtime: Runtime, tool_name: str, tool_input: Any, error: str,
    ) -> None:
        """Record failure and set pending_stuck flag if stuck. Does NOT pause graph."""
        tracker = self._get_tracker(runtime)
        tracker.record_tool_failure(tool_name, tool_input, error)
        if tracker.stuck:
            run_id = _get_runtime_value(runtime, "run_id", None) or "default"
            self._pending_stuck[run_id] = True

    def _check_stuck_and_pause(
        self, state: ThreadState, runtime: Runtime,
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
                "run_id": run_id, "reason": reason,
                "failures": len(tracker.get_failures()),
            })

        tracker.reset()
        return Command(goto=END, update={"messages": [HumanMessage(
            content=f"[STALL DETECTED] {reason}. Pausing for user help.",
            name="stall_detection",
            additional_kwargs={"hide_from_ui": True},
        )]})

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
        run_id = _get_runtime_value(runtime, "run_id", None) or "default"
        if self._pending_stuck.get(run_id):
            self._pending_stuck[run_id] = False
            result = self._check_stuck_and_pause(state, runtime)
            if result is not None:
                update = dict(result.update)
                update["jump_to"] = "__end__"
                return update
        return None

    @hook_config(can_jump_to=["__end__"])
    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        return self.after_model(state, runtime)

    @override
    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        tool_input = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}

        try:
            result = handler(request)
        except Exception as exc:
            runtime = getattr(request, "runtime", None)
            if runtime is not None:
                self._check_and_flag_stuck(runtime, tool_name, tool_input, str(exc))
            raise

        if isinstance(result, ToolMessage) and getattr(result, "status", None) == "error":
            runtime = getattr(request, "runtime", None)
            if runtime is not None:
                self._check_and_flag_stuck(runtime, tool_name, tool_input, str(result.content))
        return result

    @override
    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        tool_input = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}

        try:
            result = await handler(request)
        except Exception as exc:
            runtime = getattr(request, "runtime", None)
            if runtime is not None:
                self._check_and_flag_stuck(runtime, tool_name, tool_input, str(exc))
            raise

        if isinstance(result, ToolMessage) and getattr(result, "status", None) == "error":
            runtime = getattr(request, "runtime", None)
            if runtime is not None:
                self._check_and_flag_stuck(runtime, tool_name, tool_input, str(result.content))
        return result
