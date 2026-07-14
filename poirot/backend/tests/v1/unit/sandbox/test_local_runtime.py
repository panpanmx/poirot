from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from poirot.backend.agents.sandbox.exceptions import (
    SandboxCommandError,
    SandboxError,
    SandboxFileNotFoundError,
    SandboxPermissionError,
)
from poirot.backend.agents.sandbox.runtimes.local_runtime import LocalRuntime
from poirot.backend.agents.sandbox.types import GrepMatch


@pytest.fixture
def runtime() -> LocalRuntime:
    return LocalRuntime()


class TestExecCommand:
    def test_success(self, runtime: LocalRuntime) -> None:
        assert runtime.exec_command("echo hello").strip() == "hello"

    def test_failure_raises(self, runtime: LocalRuntime) -> None:
        with pytest.raises(SandboxCommandError) as exc_info:
            runtime.exec_command("exit 1")
        assert exc_info.value.details["exit_code"] == 1

    def test_failure_is_sandbox_error(self, runtime: LocalRuntime) -> None:
        with pytest.raises(SandboxError):
            runtime.exec_command("exit 1")

    def test_command_truncated_in_error(self, runtime: LocalRuntime) -> None:
        long_cmd = "x" * 150
        with pytest.raises(SandboxCommandError) as exc_info:
            runtime.exec_command(f"{long_cmd}; exit 1")
        assert "..." in exc_info.value.details["command"]


class TestReadFile:
    def test_success(self, runtime: LocalRuntime, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("content", encoding="utf-8")
        assert runtime.read_file(str(f)) == "content"

    def test_not_found(self, runtime: LocalRuntime) -> None:
        with pytest.raises(SandboxFileNotFoundError):
            runtime.read_file("/nonexistent/path/file.txt")

    def test_not_found_is_sandbox_error(self, runtime: LocalRuntime) -> None:
        with pytest.raises(SandboxError):
            runtime.read_file("/nonexistent/file")


class TestWriteFile:
    def test_write(self, runtime: LocalRuntime, tmp_path) -> None:
        f = tmp_path / "out.txt"
        runtime.write_file(str(f), "data")
        assert f.read_text() == "data"

    def test_creates_parent_dirs(self, runtime: LocalRuntime, tmp_path) -> None:
        f = tmp_path / "sub" / "dir" / "out.txt"
        runtime.write_file(str(f), "data")
        assert f.read_text() == "data"

    def test_append(self, runtime: LocalRuntime, tmp_path) -> None:
        f = tmp_path / "out.txt"
        runtime.write_file(str(f), "a")
        runtime.write_file(str(f), "b", append=True)
        assert f.read_text() == "ab"


class TestListDir:
    def test_returns_relative_paths(self, runtime: LocalRuntime, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        entries = runtime.list_dir(str(tmp_path))
        assert "a.txt" in entries
        assert "b.txt" in entries

    def test_max_depth(self, runtime: LocalRuntime, tmp_path) -> None:
        (tmp_path / "d1").mkdir()
        (tmp_path / "d1" / "d2").mkdir()
        (tmp_path / "d1" / "d2" / "deep.txt").write_text("x")
        entries = runtime.list_dir(str(tmp_path), max_depth=1)
        assert all(len(Path(e).parts) <= 1 for e in entries)


class TestGlob:
    def test_match(self, runtime: LocalRuntime, tmp_path) -> None:
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        matches, truncated = runtime.glob(str(tmp_path), "*.py")
        assert "a.py" in matches
        assert "b.txt" not in matches
        assert truncated is False

    def test_truncated(self, runtime: LocalRuntime, tmp_path) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("x")
        matches, truncated = runtime.glob(str(tmp_path), "*.txt", max_results=2)
        assert len(matches) == 2
        assert truncated is True


class TestGrep:
    def test_match(self, runtime: LocalRuntime, tmp_path) -> None:
        (tmp_path / "a.py").write_text("print('hello')\nprint('world')\n")
        matches, truncated = runtime.grep(str(tmp_path), "hello")
        assert len(matches) == 1
        assert "hello" in matches[0].line

    def test_ignore_patterns(self, runtime: LocalRuntime, tmp_path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("hello")
        (tmp_path / "main.py").write_text("hello")
        matches, _ = runtime.grep(str(tmp_path), "hello")
        paths = [m.path for m in matches]
        assert any(".git" not in p for p in paths)
        assert not any(".git" in p for p in paths)

    def test_max_results(self, runtime: LocalRuntime, tmp_path) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text("match\n")
        matches, truncated = runtime.grep(str(tmp_path), "match", max_results=2)
        assert len(matches) == 2
        assert truncated is True

    def test_returns_grep_match(self, runtime: LocalRuntime, tmp_path) -> None:
        (tmp_path / "a.py").write_text("pattern here\n")
        matches, _ = runtime.grep(str(tmp_path), "pattern")
        assert len(matches) == 1
        assert isinstance(matches[0], GrepMatch)
        assert matches[0].line_number == 1


class TestDownloadUpdate:
    def test_download(self, runtime: LocalRuntime, tmp_path) -> None:
        f = tmp_path / "bin.dat"
        f.write_bytes(b"\x00\x01\x02")
        assert runtime.download_file(str(f)) == b"\x00\x01\x02"

    def test_download_not_found(self, runtime: LocalRuntime) -> None:
        with pytest.raises(SandboxFileNotFoundError):
            runtime.download_file("/nonexistent")

    def test_update(self, runtime: LocalRuntime, tmp_path) -> None:
        f = tmp_path / "out.bin"
        runtime.update_file(str(f), b"\xff\xfe")
        assert f.read_bytes() == b"\xff\xfe"

    def test_update_creates_parents(self, runtime: LocalRuntime, tmp_path) -> None:
        f = tmp_path / "sub" / "out.bin"
        runtime.update_file(str(f), b"data")
        assert f.read_bytes() == b"data"


class TestClose:
    def test_close_noop(self, runtime: LocalRuntime) -> None:
        runtime.close()
