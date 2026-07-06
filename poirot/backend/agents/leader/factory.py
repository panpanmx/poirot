from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from poirot.backend.agents.agent_tools.available import get_available_tools
from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.leader.prompts import apply_prompt_template
from poirot.backend.agents.middlewares.evidence_middleware import EvidenceMiddleware
from poirot.backend.agents.middlewares.loop_detection_middleware import (
    LoopDetectionMiddleware,
)
from poirot.backend.agents.middlewares.reflection_middleware import (
    LightReflectionStrategy,
    ReflectionMiddleware,
    SufficiencyStrategy,
)
from poirot.backend.agents.middlewares.report_middleware import ReportMiddleware
from poirot.backend.agents.middlewares.run_journal_middleware import RunJournalMiddleware
from poirot.backend.agents.middlewares.system_context_middleware import SystemContextMiddleware
from poirot.backend.agents.middlewares.title_middleware import TitleMiddleware
from poirot.backend.agents.middlewares.todo_middleware import TodoMiddleware
from poirot.backend.agents.middlewares.tool_call_middleware import ToolCallMiddleware
from poirot.backend.agents.runtime.checkpointer import get_checkpointer
from poirot.backend.agents.state.types import ThreadState


def _build_middlewares(
    expert_mode: bool,
    model: BaseChatModel | None = None,
    context_governance: Any = None,
) -> list:
    """全模式全挂 middleware，参数化控制行为差异。

    default (expert_mode=False): 温和参数——Todo 不强制完成、Reflection 不 jump、
        Report 不自动合成。靠 prompt 引导模型自判深度。
    expert (expert_mode=True): 激进参数——Todo 强制完成、Reflection 充分性 jump、
        Report after_agent 自动合成。

    治理层（context_governance）挂载顺序见 builder.build_governance_middlewares。
    挂载顺序：治理层（公共3 + StrategyMiddleware） → SystemContext → Title → RunJournal →
    LoopDetection → ToolCall → Evidence → Todo → Reflection → Report。
    """
    middlewares: list = []
    if context_governance is not None:
        from poirot.backend.agents.context_engineering.builder import (
            build_governance_middlewares,
        )

        middlewares.extend(build_governance_middlewares(context_governance))
    middlewares.extend([
        SystemContextMiddleware(),
        TitleMiddleware(),
        RunJournalMiddleware(),
        LoopDetectionMiddleware(),
        ToolCallMiddleware(),
        EvidenceMiddleware(),
        TodoMiddleware(enforce_completion=expert_mode),
        ReflectionMiddleware(
            strategy=SufficiencyStrategy(llm=model) if expert_mode else LightReflectionStrategy(),
            llm=model,
        ),
    ])
    if model is not None:
        middlewares.append(ReportMiddleware(model, auto_synthesize=expert_mode))
    return middlewares


def make_lead_agent(
    expert_mode: bool = False,
    capability_registry: CapabilityRegistry | None = None,
    middleware_manager: Any = None,
    runnable_config: RunnableConfig | None = None,
    context_governance: Any = None,
) -> Any:
    """App-layer factory: expert_flag 参数化装配 graph。

    - middleware: _build_middlewares(expert_mode) 全挂参数化
    - tools: get_available_tools(groups=...) 按 expert 选 core / core+deferred
    - system_prompt: apply_prompt_template(expert_mode)
    - checkpointer: get_checkpointer() 单例，thread_id 跨轮 + 跨模式保留 state

    Registry MUST store BaseChatModel / BaseTool instances directly.
    """
    from poirot.backend.agents.leader.agent import LeaderAgent

    if runnable_config is not None and "configurable" in runnable_config:
        registry = runnable_config["configurable"].get("capability_registry")
    else:
        registry = capability_registry
        runnable_config = {"configurable": {"expert_mode": expert_mode, "capability_registry": registry}}

    if registry is None:
        raise ValueError("capability_registry is required (in configurable or as param)")

    configurable = runnable_config.get("configurable", {})
    # runnable_config 透传的 expert_mode 优先，否则用参数
    resolved_expert = bool(configurable.get("expert_mode", expert_mode))

    model = registry.get_model("researcher")

    # tool groups: default=core, expert=core+deferred
    groups = ["core", "deferred"] if resolved_expert else ["core"]
    tools: list[BaseTool] = []
    for tool in get_available_tools(groups=groups):
        if isinstance(tool, BaseTool) and tool not in tools:
            tools.append(tool)
    # registry 额外注册的工具（如 web_search_mcp 别名）保留
    for tool in registry.tools.values():
        if isinstance(tool, BaseTool) and tool not in tools:
            tools.append(tool)

    return LeaderAgent(
        graph=create_agent(
            model=model,
            tools=tools or None,
            middleware=_build_middlewares(resolved_expert, model, context_governance),
            system_prompt=apply_prompt_template(expert_mode=resolved_expert),
            state_schema=ThreadState,
            checkpointer=get_checkpointer(),
        ),
        capability_registry=registry,
    )
