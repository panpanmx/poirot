from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.leader.prompts import apply_prompt_template
from poirot.backend.agents.middlewares.run_journal_middleware import RunJournalMiddleware
from poirot.backend.agents.middlewares.summarization_middleware import SummarizationMiddleware
from poirot.backend.agents.middlewares.system_context_middleware import SystemContextMiddleware
from poirot.backend.agents.middlewares.title_middleware import TitleMiddleware
from poirot.backend.agents.middlewares.todo_middleware import TodoMiddleware
from poirot.backend.agents.middlewares.tool_call_middleware import ToolCallMiddleware
from poirot.backend.agents.middlewares.evidence_middleware import EvidenceMiddleware
from poirot.backend.agents.middlewares.reflection_middleware import ReflectionMiddleware
from poirot.backend.agents.middlewares.report_middleware import ReportMiddleware
from poirot.backend.agents.state.types import ThreadState


def _build_middlewares(mode: str, model: BaseChatModel | None = None) -> list:
    middlewares = [
        SummarizationMiddleware(),
        SystemContextMiddleware(),
        ToolCallMiddleware(),
        TitleMiddleware(),
        RunJournalMiddleware(),
    ]
    if mode in ("general", "expert"):
        middlewares.insert(2, TodoMiddleware())
        middlewares.insert(3, EvidenceMiddleware())
        middlewares.insert(4, ReflectionMiddleware())
        if model is not None:
            middlewares.append(ReportMiddleware(model))
    return middlewares


def make_lead_agent(
    capability_registry: CapabilityRegistry | None = None,
    middleware_manager: Any = None,
    runnable_config: RunnableConfig | None = None,
) -> Any:
    """App-layer factory: config-driven, resolves deps from CapabilityRegistry.

    Registry MUST store BaseChatModel / BaseTool instances directly.
    Directly calls langchain.agents.create_agent (no intermediate adapter layer).
    """
    from poirot.backend.agents.leader.agent import LeaderAgent

    if runnable_config is not None and "configurable" in runnable_config:
        registry = runnable_config["configurable"].get("capability_registry")
    else:
        registry = capability_registry
        runnable_config = {"configurable": {"mode": "general", "capability_registry": registry}}

    if registry is None:
        raise ValueError("capability_registry is required (in configurable or as param)")

    configurable = runnable_config.get("configurable", {})
    mode = configurable.get("mode", "general")

    model = registry.get_model("researcher")

    tools: list[BaseTool] = []
    for tool in registry.tools.values():
        if isinstance(tool, BaseTool) and tool not in tools:
            tools.append(tool)

    return LeaderAgent(
        graph=create_agent(
            model=model,
            tools=tools or None,
            middleware=_build_middlewares(mode, model),
            system_prompt=apply_prompt_template(mode),
            state_schema=ThreadState,
        ),
        capability_registry=registry,
    )
