"""DateInjectorMiddleware — before_agent 注入当前日期（公共固定）。

date 注入是基础事实需求，所有策略必需，固定 real 不经 registry。
noop=模型不知日期（功能坏），故公共。冻结快照/ID-swap 等增强见 S5 baseline。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

from poirot.backend.agents.state.types import ThreadState

_DATE_REMINDER_KEY = "date_reminder"


class DateInjectorMiddleware(AgentMiddleware):
    """before_agent 注入当前日期 SystemMessage（公共固定）。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def _has_date_reminder(self, messages: list) -> bool:
        return any(
            isinstance(m, SystemMessage) and m.additional_kwargs.get(_DATE_REMINDER_KEY)
            for m in messages
        )

    @override
    def before_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        if self._has_date_reminder(messages):
            return None
        date_str = datetime.now().strftime("%Y-%m-%d, %A")
        reminder = SystemMessage(
            content=f"<system-reminder><current_date>{date_str}</current_date></system-reminder>",
            additional_kwargs={_DATE_REMINDER_KEY: True, "hide_from_ui": True},
        )
        return {"messages": [reminder]}

    @override
    async def abefore_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)
