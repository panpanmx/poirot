import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def test_cli_run_prints_report_and_paths() -> None:
    temp_dir = _workspace_temp_dir()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "poirot.backend.app.cli.main",
            "run",
            "CLI research question",
            "--mode",
            "general",
            "--run-id",
            "run-cli",
            "--logs-root",
            str(temp_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "CLI research question" in completed.stdout
    assert "run_id: run-cli" in completed.stdout
    assert "events_jsonl:" in completed.stdout
    assert "final_report_md:" in completed.stdout
    assert (temp_dir / "run-cli" / "artifacts" / "final_report.md").exists()

    shutil.rmtree(temp_dir)


def _workspace_temp_dir() -> Path:
    path = Path(".pytest-workspace-tmp") / uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    return path
