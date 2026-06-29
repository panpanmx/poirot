import json
import shutil
from pathlib import Path
from uuid import uuid4

from poirot.backend.app.bootstrap import bootstrap_runtime


def test_minimum_agent_loop_generates_final_report_and_artifact() -> None:
    temp_dir = _workspace_temp_dir()
    runtime = bootstrap_runtime(mode="general", cli_overrides={"logs_root": str(temp_dir)})

    result = runtime.run_question(
        question="Research Poirot architecture",
        thread_id="thread-1",
        user_id="user-1",
        run_id="run-1",
    )

    assert "Research Poirot architecture" in result.final_report
    assert "Fake search result" in result.final_report
    assert (temp_dir / "run-1" / "record.json").exists()
    assert (temp_dir / "run-1" / "events.jsonl").exists()
    assert (temp_dir / "run-1" / "artifacts" / "final_report.md").exists()

    events = [
        json.loads(row)["event_type"]
        for row in (temp_dir / "run-1" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "run.started" in events
    assert "tool.finished" in events
    assert "report.generated" in events
    assert "run.finished" in events

    shutil.rmtree(temp_dir)


def _workspace_temp_dir() -> Path:
    path = Path(".pytest-workspace-tmp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path
