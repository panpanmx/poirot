"""PoirotStreamClient 单测：custom mode 消费 compaction 事件。"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from poirot.backend.app.services.stream_service import PoirotStreamClient


class _FakeGraph:
    """假 graph：astream 产固定 (mode, chunk) 序列。"""

    def __init__(self, chunks: list) -> None:
        self._chunks = chunks

    async def astream(self, state: Any, config: Any = None, stream_mode: Any = None) -> AsyncIterator:
        for c in self._chunks:
            yield c


async def _drain(gen: AsyncIterator) -> list:
    out: list = []
    async for e in gen:
        out.append(e)
    return out


def test_custom_compaction_start_event() -> None:
    """custom mode compaction_start dict → StreamEvent(type=compaction_start, tool_name=P4)。"""
    graph = _FakeGraph([("custom", {"type": "compaction_start", "tool_name": "P4"})])
    client = PoirotStreamClient(graph, config={})
    events = asyncio.run(_drain(client.stream("Q")))
    starts = [e for e in events if e["type"] == "compaction_start"]
    assert len(starts) == 1
    assert starts[0]["tool_name"] == "P4"
    assert events[-1]["type"] == "done"  # astream 结束 yield done


def test_custom_no_type_skipped() -> None:
    """custom chunk 无 type 字段 → 跳过（不 yield），仅末尾 done。"""
    graph = _FakeGraph([("custom", {"foo": "bar"})])
    client = PoirotStreamClient(graph, config={})
    events = asyncio.run(_drain(client.stream("Q")))
    assert all(e["type"] != "compaction_start" for e in events)
    assert events[-1]["type"] == "done"


def test_custom_compaction_end_with_saved() -> None:
    """custom mode compaction_end 含 tool_result(saved) → StreamEvent 透传。"""
    graph = _FakeGraph([("custom", {"type": "compaction_end", "content": "summarize", "tool_result": "1800"})])
    client = PoirotStreamClient(graph, config={})
    events = asyncio.run(_drain(client.stream("Q")))
    ends = [e for e in events if e["type"] == "compaction_end"]
    assert len(ends) == 1
    assert ends[0]["content"] == "summarize"
    assert ends[0]["tool_result"] == "1800"
