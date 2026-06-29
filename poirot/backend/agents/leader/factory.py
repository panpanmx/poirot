from __future__ import annotations

from typing import Any

from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.leader.agent import LeaderAgent
from poirot.backend.agents.middlewares.middleware_manager import MiddlewareManager


def make_lead_agent(
    capability_registry: CapabilityRegistry,
    middleware_manager: MiddlewareManager | None,
    runnable_config: dict[str, Any] | None = None,
) -> LeaderAgent:
    return LeaderAgent(
        capability_registry=capability_registry,
        middleware_manager=middleware_manager,
    )
