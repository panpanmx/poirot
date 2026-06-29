import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from poirot.backend.agents.config.loader import load_config
from poirot.backend.agents.journal.run_journal import RunJournal
from poirot.backend.agents.middlewares.base_middleware import (
    BaseMiddleware,
    MiddlewarePatch,
    MiddlewareViolationError,
)
from poirot.backend.agents.middlewares.middleware_manager import MiddlewareManager
from poirot.backend.agents.runtime.run_context import RunContext


class MetadataMiddleware(BaseMiddleware):
    name = "metadata"
    hook_points = ("before_agent",)
    read_fields = ("user_input",)
    write_fields = ("metadata",)

    def before_agent(self, state, context):
        return MiddlewarePatch(
            updates={"metadata": {"title": state["user_input"][:20]}},
            events=[("middleware.applied", {"middleware": self.name})],
        )


class IllegalMiddleware(BaseMiddleware):
    name = "illegal"
    hook_points = ("before_agent",)
    write_fields = ("metadata",)

    def before_agent(self, state, context):
        return MiddlewarePatch(updates={"final_report": "not allowed"})


def test_middleware_manager_merges_patch_and_writes_events() -> None:
    temp_dir = _workspace_temp_dir()
    context = _context(temp_dir)
    manager = MiddlewareManager([MetadataMiddleware()])

    merged = manager.run_hook("before_agent", {"user_input": "Long research topic"}, context)

    assert merged["metadata"]["title"] == "Long research topic"
    event = json.loads((temp_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert event["event_type"] == "middleware.applied"

    shutil.rmtree(temp_dir)


def test_middleware_manager_rejects_unauthorized_fields() -> None:
    temp_dir = _workspace_temp_dir()
    context = _context(temp_dir)
    manager = MiddlewareManager([IllegalMiddleware()])

    with pytest.raises(MiddlewareViolationError, match="not allowed to write field"):
        manager.run_hook("before_agent", {"user_input": "topic"}, context)

    event = json.loads((temp_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert event["event_type"] == "middleware.failed"

    shutil.rmtree(temp_dir)


def _context(temp_dir: Path) -> RunContext:
    config = load_config(mode="general", cli_overrides={"logs_root": str(temp_dir)})
    return RunContext(
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
        session_id=None,
        trace_id=None,
        config=config,
        budget={},
        output_dir=temp_dir,
        enabled_middlewares=(),
        journal=RunJournal("run-1", temp_dir / "events.jsonl"),
    )


def _workspace_temp_dir() -> Path:
    path = Path(".pytest-workspace-tmp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path
