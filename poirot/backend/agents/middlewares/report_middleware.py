"""ReportMiddleware — ReAct 循环结束后独立合成 final_report。

after_agent 阶段：observations 非空时用 reporter prompt 单独调一次 LLM，
基于 observations + sources + errors 合成结构化 Markdown 写回 state["final_report"]。
不再赌最后一条 AIMessage（deer-flow 模式）。仅 general/expert 启用。
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from poirot.backend.agents.state.types import ThreadState

_REPORTER_SYSTEM = """你是一名专业的研究报告撰写专家。你的任务是把已收集的研究证据（observations）和来源（sources）综合成一份严谨、结构化、可追溯的中文 Markdown 研究报告。

## 核心原则
1. **只基于已提供材料**：报告中的事实性陈述必须能在给出的 observations 中找到依据。严禁编造数据、结论或来源。不得引用未在 sources 列表中出现的 URL 或 source_id。
2. **全程可追溯**：每条事实性陈述后用 [source_id] 标注来源（如 [src-abc123]）。无法定位来源的判断，要么标注"基于推断"，要么不要写入。
3. **客观中立**：第三人称陈述，不带推销或主观情绪。证据之间存在矛盾时，客观呈现各方并明确指出分歧，不擅自取舍。
4. **显式声明缺口**：若 tools 失败（errors）或某方面证据不足，必须在"信息缺口"分节如实说明"未能获取 X"，绝不静默掩盖或用空话填充。

## 输出结构（Markdown，按此顺序）
# {研究问题作为标题}
## 摘要
2–4 句话概括研究问题、核心发现与结论，让读者快速把握全貌。
## 研究背景
简要交代问题的上下文与为什么值得研究（证据不足时从简）。
## 核心发现
报告主体。按主题用 ### 子节组织，每条发现配证据与 [source_id] 引用。这是正文，必须有实质内容。
## 分析与结论
跨发现综合，给出结论、意义或建议；明确区分"证据充分支持"与"证据有限时推断"。
## 来源
列出用到的 sources：`- [source_id] 标题 — URL`。未在正文引用的来源不必列出。
## 信息缺口
仅当存在 errors 或证据不足时输出；否则省略此节。

## 格式与边界
- 直接输出 Markdown 正文，不要包裹在代码块 ``` 里，不要加前后缀解释。
- 禁止只写一句收尾、客套话或"以上就是报告"式空泛总结——发现与分析分节必须有实质内容。
- 正文长度应与证据量匹配：证据少则简明，证据多则充分展开；不要为凑篇幅注水。
- 语言跟随研究问题的语言（中文问题用中文）。
"""


def _format_observations(observations: list[Any]) -> str:
    if not observations:
        return "（无观察记录）"
    lines: list[str] = []
    for obs in observations:
        oid = _field(obs, "observation_id") or "?"
        sid = _field(obs, "step_id") or "-"
        content = _field(obs, "content") or ""
        refs = _field(obs, "source_refs") or ()
        refs_str = ", ".join(refs) if refs else "无"
        lines.append(f"[{oid}] (step={sid}, sources={refs_str})\n{content}")
    return "\n\n".join(lines)


def _format_sources(sources: list[Any]) -> str:
    if not sources:
        return "（无来源）"
    lines: list[str] = []
    for src in sources:
        sid = _field(src, "source_id") or "?"
        url = _field(src, "url") or ""
        title = _field(src, "title") or ""
        lines.append(f"[{sid}] {title} — {url}".rstrip(" —"))
    return "\n".join(lines)


def _format_errors(errors: list[Any]) -> str:
    if not errors:
        return ""
    lines = ["以下工具调用失败，对应信息未能获取："]
    for err in errors:
        msg = _field(err, "message") or str(err)
        lines.append(f"- {msg}")
    return "\n".join(lines)


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _build_reporter_messages(state: dict[str, Any]) -> list[Any]:
    question = state.get("research_question") or state.get("user_input") or "Research report"
    observations = state.get("observations") or []
    sources = state.get("sources") or []
    errors = state.get("errors") or []

    user_content = (
        f"# 研究问题\n{question}\n\n"
        f"# 已收集的观察（observations）\n{_format_observations(observations)}\n\n"
        f"# 来源（sources）\n{_format_sources(sources)}\n"
    )
    err_block = _format_errors(errors)
    if err_block:
        user_content += f"\n# 工具失败（errors）\n{err_block}\n"
    user_content += "\n\n请基于以上证据撰写完整研究报告。"

    return [SystemMessage(content=_REPORTER_SYSTEM), HumanMessage(content=user_content)]


class ReportMiddleware(AgentMiddleware):
    """after_agent 阶段独立合成 final_report。MVP 复用 researcher 模型（D5）。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    def _synthesize(self, state: dict[str, Any]) -> str:
        messages = _build_reporter_messages(state)
        response = self._model.invoke(messages)
        return getattr(response, "content", str(response))

    async def _asynthesize(self, state: dict[str, Any]) -> str:
        messages = _build_reporter_messages(state)
        response = await self._model.ainvoke(messages)
        return getattr(response, "content", str(response))

    @override
    def after_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        observations = state.get("observations") or []  # type: ignore[assignment]
        if not observations:
            return None
        report = self._synthesize(state if isinstance(state, dict) else dict(state))
        return {"final_report": report}

    @override
    async def aafter_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        observations = state.get("observations") or []  # type: ignore[assignment]
        if not observations:
            return None
        report = await self._asynthesize(state if isinstance(state, dict) else dict(state))
        return {"final_report": report}
