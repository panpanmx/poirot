import json
import shutil
from pathlib import Path
from uuid import uuid4

from poirot.backend.agents.journal.run_journal import RunJournal


def test_run_journal_writes_event_jsonl() -> None:
    temp_dir = _workspace_temp_dir()
    journal = RunJournal(run_id="run-1", events_path=temp_dir / "events.jsonl")

    journal.append("run.started", {"mode": "general"})

    rows = (temp_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(rows[0])["event_type"] == "run.started"

    shutil.rmtree(temp_dir)


def _workspace_temp_dir() -> Path:
    path = Path(".pytest-workspace-tmp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path
