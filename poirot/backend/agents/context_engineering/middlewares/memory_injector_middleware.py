"""MemoryInjectorMiddleware — before_agent 接入 memory 注入能力（策略）。

持 MemoryInjector Protocol 实例，hook 内构造 CapabilityContext 调用
impl.inject/ainject，apply CapabilityResult。治理逻辑位于 impl。
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langgraph.runtime import Runtime

from poirot.backend.agents.context_engineering.protocols import MemoryInjector
from poirot.backend.agents.context_engineering.types import (
    CapabilityContext,
    apply_capability_result,
)
from poirot.backend.agents.context_engineering.utilities import token_counter
from poirot.backend.agents.state.types import ThreadState


class MemoryInjectorMiddleware(AgentMiddleware):
    """before_agent 接入 MemoryInjector 能力。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, impl: MemoryInjector, config: Any = None) -> None:
        self._impl = impl
        self._config = config

    def _ctx(self, state: ThreadState, runtime: Runtime) -> CapabilityContext:
        return CapabilityContext(
            state=state,
            governance=state.get("governance"),
            config=self._config,
            token_counter=token_counter,
            runtime=runtime,
            messages=state.get("messages") or [],
        )

    @override
    def before_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        result = self._impl.inject(self._ctx(state, runtime))
        return apply_capability_result(state, result)

    @override
    async def abefore_agent(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        result = await self._impl.ainject(self._ctx(state, runtime))
        return apply_capability_result(state, result)
