"""PoirotStreamClient — 流式研究服务（仿 deer-flow DeerFlowClient.stream）。

用 graph.astream(stream_mode=["values", "messages"]) 消费 LangGraph 原生流：
- messages mode：token 级 delta（AIMessageChunk content + reasoning_content + tool_calls / ToolMessage）
- values mode：完整状态快照（用于去重 + 检测 done）

产出标准化 StreamEvent 供 CLI 渲染。不在 LeaderAgent 内——LeaderAgent 只管 run()，
流式消费归本 service。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, TypedDict

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage


class StreamEvent(TypedDict):
    """流式事件标准化结构，供 CLI 消费渲染。"""

    type: str  # "thinking" | "answer" | "tool_start" | "tool_end" | "done" | "error"
    content: str
    tool_name: str | None
    tool_args: dict | None
    tool_result: str | None
    msg_id: str | None


def _extract_text(content: Any) -> str:
    """从 message content 提取纯文本（兼容 str / list[dict]）。"""
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
    return str(content) if content else ""


def _extract_reasoning(chunk: AIMessageChunk) -> str:
    """提取 reasoning_content delta（deepseek 等 thinking token）。"""
    additional = getattr(chunk, "additional_kwargs", {}) or {}
    return additional.get("reasoning_content", "") or ""


def _truncate(text: str, limit: int = 200) -> str:
    return text[:limit] + "..." if len(text) > limit else text


class PoirotStreamClient:
    """流式研究服务——消费 graph.astream，产出 StreamEvent。

    仿 deer-flow DeerFlowClient.stream()：
    - stream_mode=["values", "messages"] 双模式
    - messages mode 拿 token delta（thinking/answer/tool）
    - values mode 去重 + 检测完成
    - seen_ids / streamed_ids 跨模式去重
    """

    def __init__(self, graph: Any, config: dict) -> None:
        self._graph = graph
        self._config = config

    async def stream(self, question: str) -> AsyncIterator[StreamEvent]:
        """流式产出 StreamEvent。

        Args:
            question: 用户研究问题

        Yields:
            StreamEvent: thinking / answer / tool_start / tool_end / done / error
        """
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content=question)],
            "user_input": question,
            "research_question": question,
        }

        seen_ids: set[str] = set()
        streamed_ids: set[str] = set()
        first_values_frame = True

        async for item in self._graph.astream(
            state,
            config=self._config,
            stream_mode=["values", "messages", "custom"],
        ):
            # 多 mode 时 astream 产 (mode, chunk) tuple
            if isinstance(item, tuple) and len(item) == 2:
                mode, chunk = item
                mode = str(mode)
            else:
                mode, chunk = "values", item

            # custom mode: middleware/strategy 用 get_stream_writer() 发的 custom event
            # （如 DefaultStrategy compaction_start/progress/end）
            if mode == "custom":
                if isinstance(chunk, dict) and "type" in chunk:
                    yield StreamEvent(
                        type=chunk["type"],
                        content=chunk.get("content", ""),
                        tool_name=chunk.get("tool_name"),
                        tool_args=chunk.get("tool_args"),
                        tool_result=chunk.get("tool_result"),
                        msg_id=chunk.get("msg_id"),
                    )
                continue

            if mode == "messages":
                # messages mode: (message_chunk, metadata) tuple
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    msg_chunk, _metadata = chunk
                else:
                    msg_chunk, chunk

                # 过滤内部 LLM 调用（summarizer/reporter/reflection）——tag=internal_llm
                # 防止压缩/报告/反思的 model.invoke 输出泄漏到 CLI 当作 answer 渲染
                if isinstance(_metadata, dict):
                    _tags = _metadata.get("tags") or []
                    if "internal_llm" in _tags:
                        continue

                msg_id = getattr(msg_chunk, "id", None)

                # AIMessageChunk → thinking + answer + tool_calls
                if isinstance(msg_chunk, AIMessageChunk) or isinstance(msg_chunk, AIMessage):
                    # thinking: reasoning_content delta
                    reasoning = _extract_reasoning(msg_chunk)
                    if reasoning:
                        if msg_id:
                            streamed_ids.add(msg_id)
                        yield StreamEvent(
                            type="thinking", content=reasoning,
                            tool_name=None, tool_args=None, tool_result=None, msg_id=msg_id,
                        )

                    # answer: content delta
                    text = _extract_text(msg_chunk.content)
                    if text:
                        if msg_id:
                            streamed_ids.add(msg_id)
                        yield StreamEvent(
                            type="answer", content=text,
                            tool_name=None, tool_args=None, tool_result=None, msg_id=msg_id,
                        )

                    # tool_calls → tool_start
                    tool_calls = getattr(msg_chunk, "tool_calls", None) or []
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            tc_name = tc.get("name", "")
                            tc_args = tc.get("args", {})
                            tc_id = tc.get("id", "")
                            yield StreamEvent(
                                type="tool_start", content="",
                                tool_name=tc_name,
                                tool_args=tc_args if isinstance(tc_args, dict) else None,
                                tool_result=None, msg_id=tc_id,
                            )

                # ToolMessage → tool_end
                elif isinstance(msg_chunk, ToolMessage):
                    if msg_id:
                        streamed_ids.add(msg_id)
                    result_text = _extract_text(msg_chunk.content)
                    yield StreamEvent(
                        type="tool_end", content="",
                        tool_name=getattr(msg_chunk, "name", "") or "",
                        tool_args=None,
                        tool_result=_truncate(result_text),
                        msg_id=msg_id,
                    )

                continue

            # mode == "values": 完整状态快照——去重 + done 检测
            if mode == "values" and isinstance(chunk, dict):
                messages = chunk.get("messages", [])
                # 第一帧 values 含 checkpoint 恢复的旧 messages，预填 seen_ids 跳过，防重复输出
                if first_values_frame:
                    for msg in messages:
                        msg_id = getattr(msg, "id", None)
                        if msg_id:
                            seen_ids.add(msg_id)
                            streamed_ids.add(msg_id)
                    first_values_frame = False
                    continue
                for msg in messages:
                    msg_id = getattr(msg, "id", None)
                    if msg_id and msg_id in seen_ids:
                        continue
                    if msg_id:
                        seen_ids.add(msg_id)

                    # 已通过 messages mode 流式输出了，跳过
                    if msg_id and msg_id in streamed_ids:
                        continue

                    # 未通过 messages mode 输出的消息（如非 streaming 模型）
                    if isinstance(msg, AIMessage):
                        text = _extract_text(msg.content)
                        if text:
                            yield StreamEvent(
                                type="answer", content=text,
                                tool_name=None, tool_args=None, tool_result=None, msg_id=msg_id,
                            )
                        tool_calls = getattr(msg, "tool_calls", None) or []
                        for tc in tool_calls:
                            if isinstance(tc, dict):
                                yield StreamEvent(
                                    type="tool_start", content="",
                                    tool_name=tc.get("name", ""),
                                    tool_args=tc.get("args") if isinstance(tc.get("args"), dict) else None,
                                    tool_result=None, msg_id=tc.get("id", ""),
                                )
                    elif isinstance(msg, ToolMessage):
                        result_text = _extract_text(msg.content)
                        yield StreamEvent(
                            type="tool_end", content="",
                            tool_name=getattr(msg, "name", "") or "",
                            tool_args=None,
                            tool_result=_truncate(result_text),
                            msg_id=msg_id,
                        )

                # 检测 done：values 最后一帧含完整状态
                # LangGraph astream values mode 最后一帧是完整 final state
                # 无精确 "done" 信号——靠 astream 结束后 yield done
                continue

        # astream 结束 → done
        yield StreamEvent(
            type="done", content="",
            tool_name=None, tool_args=None, tool_result=None, msg_id=None,
        )
