"""5 策略 middleware noop 路由 + NoopCapability 满足 Protocol 单测。"""

from __future__ import annotations

from types import SimpleNamespace

from poirot.backend.agents.context_engineering.capabilities.noop import NoopCapability
from poirot.backend.agents.context_engineering.middlewares.budget_guard_middleware import (
    BudgetGuardMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.compressor_middleware import (
    CompressorMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.externalizer_middleware import (
    ExternalizerMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.memory_injector_middleware import (
    MemoryInjectorMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.tool_schema_filter_middleware import (
    ToolSchemaFilterMiddleware,
)
from poirot.backend.agents.context_engineering.protocols import (
    BudgetGuard,
    Compressor,
    Externalizer,
    MemoryInjector,
    ToolSchemaFilter,
)


def _state() -> dict:
    return {"messages": [], "governance": None}


def _tool_request() -> SimpleNamespace:
    return SimpleNamespace(runtime=SimpleNamespace(state=_state()))


def _model_request() -> SimpleNamespace:
    return SimpleNamespace(runtime=SimpleNamespace(state=_state()), messages=[], tools=[])


def test_noop_satisfies_5_strategy_protocols() -> None:
    n = NoopCapability()
    assert isinstance(n, Compressor)
    assert isinstance(n, Externalizer)
    assert isinstance(n, ToolSchemaFilter)
    assert isinstance(n, BudgetGuard)
    assert isinstance(n, MemoryInjector)


def test_compressor_noop_before_model_returns_none() -> None:
    m = CompressorMiddleware(NoopCapability())
    assert m.before_model(_state(), None) is None


def test_memory_injector_noop_before_agent_returns_none() -> None:
    m = MemoryInjectorMiddleware(NoopCapability())
    assert m.before_agent(_state(), None) is None


def test_budget_guard_noop_after_model_returns_none() -> None:
    m = BudgetGuardMiddleware(NoopCapability())
    assert m.after_model(_state(), None) is None


def test_externalizer_noop_passthrough_handler_result() -> None:
    m = ExternalizerMiddleware(NoopCapability())
    sentinel = object()

    def handler(_req: object) -> object:
        return sentinel

    assert m.wrap_tool_call(_tool_request(), handler) is sentinel


def test_tool_schema_filter_noop_passthrough_handler_result() -> None:
    m = ToolSchemaFilterMiddleware(NoopCapability())
    sentinel = object()

    def handler(_req: object) -> object:
        return sentinel

    assert m.wrap_model_call(_model_request(), handler) is sentinel
