"""BudgetGuardMiddleware — after_model 接入单 run 软预算警告能力（策略）。

持 BudgetGuard Protocol 实例，hook 内构造 CapabilityContext 调用
impl.guard/aguard，apply CapabilityResult。软警告逻辑位于 impl。
硬底线剥 tool_calls 属公共 BudgetHardStopMiddleware，不在此。
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langgraph.runtime import Runtime

from poirot.backend.agents.context_engineering.protocols import BudgetGuard
from poirot.backend.agents.context_engineering.types import (
    CapabilityContext,
    apply_capability_result,
)
from poirot.backend.agents.context_engineering.utilities import token_counter
from poirot.backend.agents.state.types import ThreadState


class BudgetGuardMiddleware(AgentMiddleware):
    """after_model 接入 BudgetGuard 能力（软警告）。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, impl: BudgetGuard, config: Any = None) -> None:
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

    @hook_config(can_jump_to=["model"])
    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        result = self._impl.guard(self._ctx(state, runtime))
        return apply_capability_result(state, result)

    @hook_config(can_jump_to=["model"])
    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        result = await self._impl.aguard(self._ctx(state, runtime))
        return apply_capability_result(state, result)
