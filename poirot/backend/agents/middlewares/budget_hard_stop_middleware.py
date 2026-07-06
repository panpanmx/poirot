"""BudgetHardStopMiddleware — after_model 单 run 硬底线熔断（公共固定）。

累计 token 超硬阈值则剥最后 AIMessage tool_calls + 注入停止文本 + jump model。
硬底线是安全需求，所有策略必需，固定 real 不经 registry。noop=run 失控（安全坏）。
软警告属策略 bundle 内部实现，不在此。run-scoped 累计增强见后续策略实现。
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from poirot.backend.agents.state.types import ThreadState

_DEFAULT_HARD_THRESHOLD = 200_000


class BudgetHardStopMiddleware(AgentMiddleware):
    """after_model 硬底线熔断（公共固定）。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, hard_threshold: int | None = None) -> None:
        self._hard_threshold = hard_threshold or _DEFAULT_HARD_THRESHOLD

    def _cumulative_tokens(self, messages: list) -> int:
        total = 0
        for m in messages:
            if isinstance(m, AIMessage) and getattr(m, "usage_metadata", None):
                usage = m.usage_metadata or {}
                total += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return total

    @hook_config(can_jump_to=["model"])
    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        if self._cumulative_tokens(messages) < self._hard_threshold:
            return None
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if not last_ai or not getattr(last_ai, "tool_calls", None):
            return None
        cleared = AIMessage(
            content=last_ai.content or "",
            tool_calls=[],
            additional_kwargs={**last_ai.additional_kwargs, "budget_hard_stop": True},
        )
        stop_msg = HumanMessage(
            name="budget_hard_stop",
            additional_kwargs={"hide_from_ui": True},
            content="[BUDGET HARD STOP] token 累计超硬阈值，强制收尾。",
        )
        return {"messages": [cleared, stop_msg], "jump_to": "model"}

    @hook_config(can_jump_to=["model"])
    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
