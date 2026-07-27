"""Tests for StallTracker stall detection signals."""

from __future__ import annotations

from poirot.backend.agents.observability.stall_tracker import (
    StallTracker,
    classify_capability,
    classify_error_class,
)


class TestClassify:
    def test_postgres_capability(self) -> None:
        assert classify_capability("bash", {"command": "apt install postgresql"}, "denied") == "postgres"

    def test_root_capability(self) -> None:
        assert classify_capability("bash", {"command": "apt-get update"}, "permission denied") == "root"

    def test_docker_capability(self) -> None:
        assert classify_capability("bash", {"command": "docker ps"}, "not found") == "docker"

    def test_network_error_class(self) -> None:
        assert classify_error_class("504 Gateway Time-out") == "network"

    def test_sandbox_error_class(self) -> None:
        assert classify_error_class("write failed: [WinError 10061] connection refused") == "sandbox"

    def test_sandbox_capability_for_winerror(self) -> None:
        assert classify_capability("write_file", {"path": "/x"}, "write failed: [WinError 10061]") == "sandbox"

    def test_permission_error_class(self) -> None:
        assert classify_error_class("Permission denied") == "permission"

    def test_not_found_error_class(self) -> None:
        assert classify_error_class("command not found") == "not_found"


class TestCapabilityExhaustion:
    def test_two_different_commands_same_capability_triggers_stuck(self) -> None:
        tracker = StallTracker()
        tracker.record_tool_failure("bash", {"command": "apt install postgresql"}, "permission denied")
        assert not tracker.stuck
        tracker.record_tool_failure("bash", {"command": "find / -name postgres"}, "not found")
        assert tracker.stuck
        assert "capability exhausted" in tracker.get_stuck_reason()

    def test_same_command_twice_does_not_trigger(self) -> None:
        tracker = StallTracker()
        tracker.record_tool_failure("bash", {"command": "apt install postgresql"}, "denied")
        tracker.record_tool_failure("bash", {"command": "apt install postgresql"}, "denied")
        assert not tracker.stuck


class TestErrorPatternRepetition:
    def test_three_same_error_class_triggers_stuck(self) -> None:
        tracker = StallTracker()
        tracker.record_tool_failure("bash", {"command": "cmd1"}, "permission denied")
        tracker.record_tool_failure("bash", {"command": "cmd2"}, "403 forbidden")
        assert not tracker.stuck
        tracker.record_tool_failure("bash", {"command": "cmd3"}, "EACCES")
        assert tracker.stuck
        assert "error pattern" in tracker.get_stuck_reason()


class TestTodoStagnation:
    def test_five_rounds_same_todo_triggers_stuck(self) -> None:
        tracker = StallTracker()
        todos = [{"content": "install postgres", "status": "in_progress"}]
        for _ in range(4):
            tracker.record_todo_state(todos)
            assert not tracker.stuck
        tracker.record_todo_state(todos)
        assert tracker.stuck
        assert "todo stagnated" in tracker.get_stuck_reason()

    def test_changing_todo_resets_counter(self) -> None:
        tracker = StallTracker()
        tracker.record_todo_state([{"content": "task A", "status": "in_progress"}])
        tracker.record_todo_state([{"content": "task A", "status": "in_progress"}])
        tracker.record_todo_state([{"content": "task B", "status": "in_progress"}])
        assert not tracker.stuck
        assert tracker._todo_stagnation_count == 1


class TestReset:
    def test_reset_clears_all_signals(self) -> None:
        tracker = StallTracker()
        tracker.record_tool_failure("bash", {"command": "apt install postgresql"}, "permission denied")
        tracker.record_tool_failure("bash", {"command": "find / -name postgres"}, "not found")
        assert tracker.stuck
        tracker.reset()
        assert not tracker.stuck
        assert len(tracker.get_failures()) == 0
