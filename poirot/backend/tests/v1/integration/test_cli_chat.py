import subprocess
import sys


def test_cli_chat_can_exit_immediately() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "poirot.backend.app.cli.main",
            "chat",
            "--provider",
            "fake",
        ],
        input="/exit\n",
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert "The little grey cells are working..." in completed.stdout
    assert "provider: fake" in completed.stdout


def test_cli_without_subcommand_starts_chat() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "poirot.backend.app.cli.main",
            "--provider",
            "fake",
        ],
        input="/exit\n",
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert "The little grey cells are working..." in completed.stdout
    assert "provider: fake" in completed.stdout
