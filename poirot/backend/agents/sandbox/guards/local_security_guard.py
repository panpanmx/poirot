from __future__ import annotations

import shlex
from pathlib import PurePosixPath

from poirot.backend.agents.sandbox.exceptions import SandboxPermissionError
from poirot.backend.agents.sandbox.types import PathMapping

_SYSTEM_PATH_PREFIXES = ("/bin/", "/usr/", "/lib/")


class LocalSecurityGuard:
    """LocalSecurityGuard — 严格白名单 + 路径穿越拒绝 + bash 命令扫描。

    方案 C 三组件之一。Local 严格白名单；Docker/E2B 用 PermissiveGuard。

    INVARIANT:
    - validate_path 拒 .. 段（路径穿越）
    - validate_path 白名单前缀检查（/mnt/poirot/user-data 读写，/mnt/skills 只读）
    - validate_command 扫描 bash 命令绝对路径，仅允许白名单前缀 + 系统路径
    - 系统路径放行 /bin/ /usr/ /lib/，不放行 /tmp/（Grill #6）
    - 只做 validate，不做 mask_output（Grill #4）
    - 验证失败抛 SandboxPermissionError
    """

    def __init__(self, path_mappings: list[PathMapping]) -> None:
        self._mappings = path_mappings

    def _reject_path_traversal(self, path: str) -> None:
        parts = PurePosixPath(path).parts
        if ".." in parts:
            raise SandboxPermissionError(
                f"path traversal detected: {path}", path=path, operation="validate"
            )

    def _find_mapping(self, path: str) -> PathMapping | None:
        """找 path 匹配的 PathMapping（最长前缀优先）。"""
        for mapping in sorted(
            self._mappings, key=lambda m: len(m.container_path), reverse=True
        ):
            container = mapping.container_path.rstrip("/")
            if path == container or path.startswith(container + "/"):
                return mapping
        return None

    def validate_path(self, path: str, *, write: bool = False) -> None:
        self._reject_path_traversal(path)
        mapping = self._find_mapping(path)
        if mapping is None:
            raise SandboxPermissionError(
                f"path not in whitelist: {path}", path=path, operation="validate"
            )
        if write and mapping.read_only:
            raise SandboxPermissionError(
                f"write to read-only path: {path}", path=path, operation="write"
            )

    def validate_command(self, command: str) -> None:
        """扫描 bash 命令中绝对路径，仅允许白名单前缀 + 系统路径。"""
        try:
            tokens = shlex.split(command)
        except ValueError:
            return
        for token in tokens:
            if token.startswith("/"):
                if any(token.startswith(p) for p in _SYSTEM_PATH_PREFIXES):
                    continue
                mapping = self._find_mapping(token)
                if mapping is None:
                    raise SandboxPermissionError(
                        f"command references path not in whitelist: {token}",
                        path=token,
                        operation="validate_command",
                    )
