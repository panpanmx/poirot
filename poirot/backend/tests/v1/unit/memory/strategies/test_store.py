from __future__ import annotations

from pathlib import Path

import pytest

from poirot.backend.agents.memory.schema import (
    Association,
    MemoryTrace,
    MemoryType,
    OperationLog,
)
from poirot.backend.agents.memory.strategies.default.store import MarkdownFileStore


def _make_trace(
    *,
    id: str = "a1b2c3d4e5f67890",
    content: str = "用户下周去东京出差",
    type: MemoryType = MemoryType.EPISODIC,
    associations: tuple = (),
    operation_log: tuple = (),
    metadata: dict | None = None,
    embedding: tuple | None = None,
    importance: float = 0.5,
    source: str | None = "thread:abc",
) -> MemoryTrace:
    return MemoryTrace(
        id=id,
        content=content,
        type=type,
        importance=importance,
        associations=associations,
        operation_log=operation_log,
        metadata=metadata or {},
        embedding=embedding,
        source=source,
    )


class TestAdd:
    def test_add_writes_to_file_and_index(self, tmp_path: Path) -> None:
        store = MarkdownFileStore(tmp_path)
        trace = _make_trace()
        store.add(trace)
        # 内存索引
        assert store.get(trace.id) is trace or store.get(trace.id).id == trace.id
        # traces.md 写入
        content = (tmp_path / "traces.md").read_text(encoding="utf-8")
        assert f"<!-- trace: {trace.id} -->" in content

    def test_add_duplicate_raises_conflict(self, tmp_path: Path) -> None:
        from poirot.backend.agents.memory.exceptions import MemoryConflictError

        store = MarkdownFileStore(tmp_path)
        trace = _make_trace()
        store.add(trace)
        with pytest.raises(MemoryConflictError):
            store.add(trace)


class TestGet:
    def test_get_existing_returns_trace(self, tmp_path: Path) -> None:
        store = MarkdownFileStore(tmp_path)
        trace = _make_trace()
        store.add(trace)
        result = store.get(trace.id)
        assert result is not None
        assert result.id == trace.id

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        store = MarkdownFileStore(tmp_path)
        assert store.get("nonexistent") is None


class TestStartupLoad:
    def test_load_existing_traces(self, tmp_path: Path) -> None:
        """启动加载：traces.md 存在时解析所有 trace 建索引。"""
        # 第一次 store 写入 2 条
        store1 = MarkdownFileStore(tmp_path)
        store1.add(_make_trace(id="aaaa1111aaaa1111", content="content one"))
        store1.add(_make_trace(id="bbbb2222bbbb2222", content="content two", type=MemoryType.SEMANTIC))
        # 第二次 store 从同一目录加载
        store2 = MarkdownFileStore(tmp_path)
        assert len(store2._traces) == 2

    def test_load_creates_empty_file_when_missing(self, tmp_path: Path) -> None:
        """启动加载：traces.md 不存在时创建空文件。"""
        assert not (tmp_path / "traces.md").exists()
        MarkdownFileStore(tmp_path)
        assert (tmp_path / "traces.md").exists()
        content = (tmp_path / "traces.md").read_text(encoding="utf-8")
        assert "# Memory Traces" in content


class TestSerializeParseRoundtrip:
    def test_basic_roundtrip(self, tmp_path: Path) -> None:
        """序列化 + 解析往返一致（基础字段）。"""
        store = MarkdownFileStore(tmp_path)
        original = _make_trace(content="hello world", importance=0.8)
        store.add(original)
        # 重新加载解析
        store2 = MarkdownFileStore(tmp_path)
        parsed = store2.get(original.id)
        assert parsed is not None
        assert parsed.id == original.id
        assert parsed.content == original.content
        assert parsed.type == original.type
        assert parsed.importance == original.importance
        assert parsed.strength == original.strength

    def test_associations_roundtrip(self, tmp_path: Path) -> None:
        """associations tuple 序列化往返。"""
        store = MarkdownFileStore(tmp_path)
        original = _make_trace(
            associations=(
                Association(target_id="t2", strength=0.9, type="causal"),
                Association(target_id="t3", strength=0.3),
            )
        )
        store.add(original)
        store2 = MarkdownFileStore(tmp_path)
        parsed = store2.get(original.id)
        assert parsed is not None
        assert len(parsed.associations) == 2
        assert parsed.associations[0].target_id == "t2"
        assert parsed.associations[0].strength == 0.9
        assert parsed.associations[0].type == "causal"
        assert parsed.associations[1].target_id == "t3"

    def test_operation_log_roundtrip(self, tmp_path: Path) -> None:
        """operation_log tuple 序列化往返。"""
        store = MarkdownFileStore(tmp_path)
        original = _make_trace(
            operation_log=(
                OperationLog(
                    timestamp=1000.0, operation="encode", actor="turn-1",
                    diff={"content": [None, "hello"]},
                ),
            )
        )
        store.add(original)
        store2 = MarkdownFileStore(tmp_path)
        parsed = store2.get(original.id)
        assert parsed is not None
        assert len(parsed.operation_log) == 1
        assert parsed.operation_log[0].operation == "encode"
        assert parsed.operation_log[0].actor == "turn-1"

    def test_metadata_roundtrip(self, tmp_path: Path) -> None:
        """metadata dict 序列化往返。"""
        store = MarkdownFileStore(tmp_path)
        original = _make_trace(metadata={"tag": "travel", "project": "poirot"})
        store.add(original)
        store2 = MarkdownFileStore(tmp_path)
        parsed = store2.get(original.id)
        assert parsed is not None
        assert parsed.metadata == {"tag": "travel", "project": "poirot"}

    def test_embedding_roundtrip(self, tmp_path: Path) -> None:
        """embedding tuple 序列化往返。"""
        store = MarkdownFileStore(tmp_path)
        original = _make_trace(embedding=(0.1, 0.2, 0.3))
        store.add(original)
        store2 = MarkdownFileStore(tmp_path)
        parsed = store2.get(original.id)
        assert parsed is not None
        assert parsed.embedding == (0.1, 0.2, 0.3)

    def test_embedding_none_roundtrip(self, tmp_path: Path) -> None:
        """embedding None 序列化往返。"""
        store = MarkdownFileStore(tmp_path)
        original = _make_trace(embedding=None)
        store.add(original)
        store2 = MarkdownFileStore(tmp_path)
        parsed = store2.get(original.id)
        assert parsed is not None
        assert parsed.embedding is None


class TestStoragePath:
    def test_relative_path_anchors_to_cwd(self, tmp_path: Path, monkeypatch) -> None:
        """相对路径锚定 cwd fallback。"""
        monkeypatch.chdir(tmp_path)
        store = MarkdownFileStore("memdir")
        assert store._root == (tmp_path / "memdir").resolve()
        assert (tmp_path / "memdir" / "traces.md").exists()
