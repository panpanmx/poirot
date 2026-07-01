"""EvidenceMiddleware — 拦截证据类工具调用，沉淀 Source/Observation/AgentError 进 ThreadState。

激活 observations/sources/errors 死字段。仅 wrap_tool_call hook，不改 ReAct 内核。
工具结果双写：messages（模型可见）+ observations/sources（旁路存档）。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from poirot.backend.agents.state.types import AgentError, Observation, Source, ThreadState

# 证据类工具白名单（D9：MVP 手维护）。非白名单工具直接 passthrough。
_EVIDENCE_TOOLS: frozenset[str] = frozenset({
    "web_search",
    "deep_search",
    "browse_page",
    "get_page_links",
    "github_search",
    "github_repo_files",
})

_OBS_CONTENT_MAX = 800
_URL_RE = re.compile(r"https?://[^\s\)\]\}\>\"']+")


def _make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tool_text(tool_msg: ToolMessage) -> str:
    """Normalize ToolMessage content (str | list[dict]) to plain text."""
    content = tool_msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content)


def _extract_sources(tool_name: str, tool_msg: ToolMessage) -> list[Source]:
    """从 ToolMessage 文本启发式抽取 URL → Source（去重按 url）。"""
    text = _tool_text(tool_msg)
    seen: set[str] = set()
    sources: list[Source] = []
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:")
        if url in seen:
            continue
        seen.add(url)
        sources.append(Source(
            source_id=_make_id("src"),
            url=url,
            title="",
            source_type="web",
            retrieved_at=_now_iso(),
            summary="",
        ))
    return sources


def _make_observation(
    tool_name: str,
    tool_msg: ToolMessage,
    sources: list[Source],
    step_id: str | None,
) -> Observation:
    """裁剪正文 ~800 字 → Observation，source_refs 关联本次 Source。"""
    text = _tool_text(tool_msg)
    content = text[:_OBS_CONTENT_MAX]
    return Observation(
        observation_id=_make_id("obs"),
        step_id=step_id,
        content=content,
        source_refs=tuple(s.source_id for s in sources),
        created_at=_now_iso(),
    )


class EvidenceMiddleware(AgentMiddleware):
    """拦截证据类工具调用，把结果结构化沉淀进 observations/sources/errors。

    非证据工具直接 passthrough。证据工具返回 Command(update=...) 双写。
    """

    state_schema = ThreadState  # type: ignore[assignment]

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call.get("name", "")
        if tool_name not in _EVIDENCE_TOOLS:
            return handler(request)

        try:
            result = handler(request)
        except Exception as exc:
            err = AgentError(
                error_id=_make_id("err"),
                stage="tool",
                message=f"{tool_name}: {exc}",
                related_refs=(request.tool_call.get("id", ""),),
                created_at=_now_iso(),
            )
            failure_msg = ToolMessage(
                content=f"⚠️ 工具 {tool_name} 调用失败：{exc}",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )
            return Command(update={"errors": [err], "messages": [failure_msg]})

        if not isinstance(result, ToolMessage):
            return result

        sources = _extract_sources(tool_name, result)
        state = request.state
        step_id = state.get("current_step_id") if isinstance(state, dict) else None
        obs = _make_observation(tool_name, result, sources, step_id)
        return Command(update={
            "observations": [obs],
            "sources": sources,
            "messages": [result],
        })

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call.get("name", "")
        if tool_name not in _EVIDENCE_TOOLS:
            return await handler(request)

        try:
            result = await handler(request)
        except Exception as exc:
            err = AgentError(
                error_id=_make_id("err"),
                stage="tool",
                message=f"{tool_name}: {exc}",
                related_refs=(request.tool_call.get("id", ""),),
                created_at=_now_iso(),
            )
            failure_msg = ToolMessage(
                content=f"⚠️ 工具 {tool_name} 调用失败：{exc}",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )
            return Command(update={"errors": [err], "messages": [failure_msg]})

        if not isinstance(result, ToolMessage):
            return result

        sources = _extract_sources(tool_name, result)
        state = request.state
        step_id = state.get("current_step_id") if isinstance(state, dict) else None
        obs = _make_observation(tool_name, result, sources, step_id)
        return Command(update={
            "observations": [obs],
            "sources": sources,
            "messages": [result],
        })
