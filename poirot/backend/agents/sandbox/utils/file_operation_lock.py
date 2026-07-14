from __future__ import annotations

import threading
import weakref

_LockKey = tuple[str, str]  # (sandbox_id, virtual_path)
_FILE_OPERATION_LOCKS: weakref.WeakValueDictionary[_LockKey, threading.Lock] = (
    weakref.WeakValueDictionary()
)
_FILE_OPERATION_LOCKS_GUARD = threading.Lock()


def get_file_operation_lock_key(sandbox_id: str, virtual_path: str) -> _LockKey:
    """构造锁 key。用虚拟路径（Grill #6：工具层拿到的是虚拟路径）。"""
    return (sandbox_id, virtual_path)


def get_file_operation_lock(sandbox_id: str, virtual_path: str) -> threading.Lock:
    """获取 (sandbox_id, virtual_path) 对应的锁。不存在则创建。

    WeakValueDictionary: 锁无引用时自动 GC，防长跑进程内存泄漏。
    key 用虚拟路径（Grill #6）。
    """
    lock_key = get_file_operation_lock_key(sandbox_id, virtual_path)
    with _FILE_OPERATION_LOCKS_GUARD:
        lock = _FILE_OPERATION_LOCKS.get(lock_key)
        if lock is None:
            lock = threading.Lock()
            _FILE_OPERATION_LOCKS[lock_key] = lock
        return lock
