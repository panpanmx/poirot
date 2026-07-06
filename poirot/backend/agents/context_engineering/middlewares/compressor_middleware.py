"""CompressorMiddleware — before_model 接入历史压缩能力。

持 Compressor Protocol 实例，hook 内构造 CapabilityContext 调用
impl.compress/acompress，apply CapabilityResult。@hook_config(can_jump_to=["model"])
允许 impl 压缩后跳转 model 节点。
"""

from __future__ import annotations

from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langgraph.runtime import Runtime

from poirot.backend.agents.context_engineering.protocols import Compressor
from poirot.backend.agents.context_engineering.types import (
    CapabilityContext,
    apply_capability_result,
)
from poirot.backend.agents.context_engineering.utilities import token_counter
from poirot.backend.agents.state.types import ThreadState


class CompressorMiddleware(AgentMiddleware):
    """before_model 接入 Compressor 能力。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, impl: Compressor, config: Any = None) -> None:
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
    def before_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        result = self._impl.compress(self._ctx(state, runtime))
        return apply_capability_result(state, result)

    @hook_config(can_jump_to=["model"])
    @override
    async def abefore_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        result = await self._impl.acompress(self._ctx(state, runtime))
        return apply_capability_result(state, result)
