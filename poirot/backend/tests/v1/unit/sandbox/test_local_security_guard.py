from __future__ import annotations

import pytest

from poirot.backend.agents.sandbox.contracts import SecurityGuard
from poirot.backend.agents.sandbox.exceptions import (
    SandboxError,
    SandboxPermissionError,
)
from poirot.backend.agents.sandbox.guards.local_security_guard import (
    LocalSecurityGuard,
)
from poirot.backend.agents.sandbox.types import PathMapping


@pytest.fixture
def guard() -> LocalSecurityGuard:
    mappings = [
        PathMapping("/mnt/poirot/user-data/workspace", "/tmp/ws"),
        PathMapping("/mnt/poirot/skills", "/tmp/skills", read_only=True),
    ]
    return LocalSecurityGuard(mappings)


class TestValidatePath:
    def test_whitelist_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_path("/mnt/poirot/user-data/workspace/file.txt")

    def test_whitelist_root_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_path("/mnt/poirot/user-data/workspace")

    def test_outside_whitelist_rejected(self, guard: LocalSecurityGuard) -> None:
        with pytest.raises(SandboxPermissionError, match="not in whitelist"):
            guard.validate_path("/etc/passwd")

    def test_traversal_rejected(self, guard: LocalSecurityGuard) -> None:
        with pytest.raises(SandboxPermissionError, match="traversal"):
            guard.validate_path("/mnt/poirot/user-data/workspace/../../../etc/passwd")

    def test_readonly_write_rejected(self, guard: LocalSecurityGuard) -> None:
        with pytest.raises(SandboxPermissionError, match="read-only"):
            guard.validate_path("/mnt/poirot/skills/x", write=True)

    def test_readonly_read_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_path("/mnt/poirot/skills/x", write=False)

    def test_error_is_sandbox_error(self, guard: LocalSecurityGuard) -> None:
        with pytest.raises(SandboxError):
            guard.validate_path("/etc/passwd")


class TestValidateCommand:
    def test_whitelist_path_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_command("ls /mnt/poirot/user-data/workspace")

    def test_outside_whitelist_rejected(self, guard: LocalSecurityGuard) -> None:
        with pytest.raises(SandboxPermissionError, match="not in whitelist"):
            guard.validate_command("cat /etc/passwd")

    def test_system_path_bin_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_command("ls /bin/bash")

    def test_system_path_usr_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_command("python /usr/bin/python3")

    def test_tmp_rejected(self, guard: LocalSecurityGuard) -> None:
        with pytest.raises(SandboxPermissionError):
            guard.validate_command("cat /tmp/secret")

    def test_no_absolute_path_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_command("echo hello world")

    def test_relative_path_pass(self, guard: LocalSecurityGuard) -> None:
        guard.validate_command("cat relative/file.txt")

    def test_shlex_failure_no_raise(self, guard: LocalSecurityGuard) -> None:
        guard.validate_command("echo 'unterminated quote")


class TestNoMaskOutput:
    def test_no_mask_output_method(self, guard: LocalSecurityGuard) -> None:
        assert not hasattr(guard, "mask_output")


class TestProtocolConformance:
    def test_is_security_guard(self, guard: LocalSecurityGuard) -> None:
        assert isinstance(guard, SecurityGuard)
