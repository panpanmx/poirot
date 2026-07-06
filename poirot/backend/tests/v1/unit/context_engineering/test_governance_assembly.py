"""治理层装配集成测：strategy 驱动挂载 / 公共始终挂 / 默认 minimal / 启动期切换。"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.config.schema import ContextGovernanceConfig
from poirot.backend.agents.context_engineering.builder import (
    _resolve_impl,
    build_governance_middlewares,
)
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
from poirot.backend.agents.context_engineering.strategy import get_strategy
from poirot.backend.agents.leader.agent import LeaderAgent
from poirot.backend.agents.leader.factory import make_lead_agent
from poirot.backend.agents.middlewares.budget_hard_stop_middleware import (
    BudgetHardStopMiddleware,
)
from poirot.backend.agents.middlewares.date_injector_middleware import (
    DateInjectorMiddleware,
)
from poirot.backend.agents.middlewares.message_normalizer_middleware import (
    MessageNormalizerMiddleware,
)
from poirot.backend.agents.reporting.markdown_reporter import MarkdownReporter

_STRATEGY_MW_TYPES = (
    CompressorMiddleware,
    ExternalizerMiddleware,
    ToolSchemaFilterMiddleware,
    MemoryInjectorMiddleware,
    BudgetGuardMiddleware,
)


def test_minimal_strategy_assembles_8_middlewares() -> None:
    ms = build_governance_middlewares(ContextGovernanceConfig(strategy="minimal"))
    assert len(ms) == 8
    types = [type(m).__name__ for m in ms]
    assert types == [
        "DateInjectorMiddleware",
        "MessageNormalizerMiddleware",
        "BudgetHardStopMiddleware",
        "CompressorMiddleware",
        "ExternalizerMiddleware",
        "ToolSchemaFilterMiddleware",
        "MemoryInjectorMiddleware",
        "BudgetGuardMiddleware",
    ]


def test_public_3_always_present() -> None:
    ms = build_governance_middlewares(ContextGovernanceConfig(strategy="minimal"))
    assert any(isinstance(m, DateInjectorMiddleware) for m in ms)
    assert any(isinstance(m, MessageNormalizerMiddleware) for m in ms)
    assert any(isinstance(m, BudgetHardStopMiddleware) for m in ms)


def test_minimal_strategy_5_strategy_mw_hold_noop() -> None:
    ms = build_governance_middlewares(ContextGovernanceConfig(strategy="minimal"))
    strategy_mw = [m for m in ms if isinstance(m, _STRATEGY_MW_TYPES)]
    assert len(strategy_mw) == 5
    for m in strategy_mw:
        assert isinstance(m._impl, NoopCapability)


def test_resolve_impl_noop_returns_noop() -> None:
    assert isinstance(_resolve_impl("noop"), NoopCapability)


def test_resolve_impl_unknown_fallback_noop() -> None:
    impl = _resolve_impl("nonexistent.impl")
    assert isinstance(impl, NoopCapability)


def test_unknown_strategy_raises() -> None:
    with pytest.raises(KeyError):
        get_strategy("nonexistent")


def test_default_config_strategy_minimal() -> None:
    from poirot.backend.agents.config.loader import load_config

    assert load_config().context_governance.strategy == "minimal"


def test_make_lead_agent_with_governance_builds_graph() -> None:
    registry = CapabilityRegistry(
        models={"researcher": FakeListChatModel(responses=["ok"])},
        tools={},
        reporter=MarkdownReporter(),
        artifact_store=object(),
    )
    agent = make_lead_agent(
        capability_registry=registry,
        context_governance=ContextGovernanceConfig(strategy="minimal"),
    )
    assert isinstance(agent, LeaderAgent)
    assert agent.graph is not None


def test_make_lead_agent_without_governance_still_works() -> None:
    registry = CapabilityRegistry(
        models={"researcher": FakeListChatModel(responses=["ok"])},
        tools={},
        reporter=MarkdownReporter(),
        artifact_store=object(),
    )
    agent = make_lead_agent(capability_registry=registry)
    assert isinstance(agent, LeaderAgent)
    assert agent.graph is not None
