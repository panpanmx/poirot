"""Multi-Agent bootstrap — 装配 specialist + 凭证检测 + metrics + 注入 CapabilityRegistry。

设计（spec.md bootstrap Requirement + design.md §2）:
- 反射加载 specialist（config.specialists.use）
- 凭证检测（缺失 → specialist disabled，tool 不注册）
- SubagentProvider 构造（agent_factory 注入）
- metrics store 构造
- OrchestrationMiddleware 构造
- 动态生成 specialist tools
- enabled=false 时不装配（lead agent 行为不变）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.tools import BaseTool

from poirot.backend.agents.multiagent.config import MultiAgentConfig
from poirot.backend.agents.multiagent.middleware import OrchestrationMiddleware
from poirot.backend.agents.multiagent.metrics import MultiAgentMetricsStore
from poirot.backend.agents.multiagent.registry import SpecialistRegistry
from poirot.backend.agents.multiagent.runtimes.subagent_runtime import SubagentRuntime
from poirot.backend.agents.multiagent.tools import (
    make_specialist_tool,
    make_subagent_tool,
)


@dataclass(frozen=True)
class MultiAgentSetup:
    """setup_multiagent 结果——注入 CapabilityRegistry + factory。"""

    specialist_registry: SpecialistRegistry | None
    subagent_provider: SubagentRuntime | None
    metrics_store: MultiAgentMetricsStore | None
    orchestration_middleware: OrchestrationMiddleware | None
    specialist_tools: tuple[BaseTool, ...]


_EMPTY_SETUP = MultiAgentSetup(
    specialist_registry=None,
    subagent_provider=None,
    metrics_store=None,
    orchestration_middleware=None,
    specialist_tools=(),
)


def _load_specialist(
    name: str,
    config: MultiAgentConfig,
    agent_factory: Callable[[], Any] | None = None,
) -> tuple[Any, Any, Any] | None:
    """反射加载 specialist + 凭证检测 + 匹配 summarizer。

    返 None 表示 specialist disabled（凭证缺失或未知 name）。
    """
    if name == "codex":
        from poirot.backend.agents.multiagent.credentials.codex_credential import (
            CodexCredentialProvider,
        )
        cred = CodexCredentialProvider().get_credential()
        if cred is None:
            return None
        from poirot.backend.agents.multiagent.specialists.codex_specialist import (
            CodexSpecialist,
        )
        from poirot.backend.agents.multiagent.summarizers.context.codex_context_summarizer import (
            CodexContextSummarizer,
        )
        from poirot.backend.agents.multiagent.summarizers.result.codex_result_summarizer import (
            CodexResultSummarizer,
        )
        return CodexSpecialist(), CodexContextSummarizer(), CodexResultSummarizer()

    if name == "claude":
        from poirot.backend.agents.multiagent.credentials.claude_credential import (
            ClaudeCredentialProvider,
        )
        cred = ClaudeCredentialProvider().get_credential()
        if cred is None:
            return None
        from poirot.backend.agents.multiagent.specialists.claude_code_specialist import (
            ClaudeCodeSpecialist,
        )
        from poirot.backend.agents.multiagent.summarizers.context.claude_code_context_summarizer import (
            ClaudeCodeContextSummarizer,
        )
        from poirot.backend.agents.multiagent.summarizers.result.claude_code_result_summarizer import (
            ClaudeCodeResultSummarizer,
        )
        return (
            ClaudeCodeSpecialist(),
            ClaudeCodeContextSummarizer(),
            ClaudeCodeResultSummarizer(),
        )

    if name == "subagent":
        from poirot.backend.agents.multiagent.runtimes.subagent_runtime import (
            SubagentRuntime,
        )
        from poirot.backend.agents.multiagent.specialists.subagent_specialist import (
            SubagentSpecialist,
        )
        from poirot.backend.agents.multiagent.summarizers.context.self_copy_context_summarizer import (
            SelfCopyContextSummarizer,
        )
        from poirot.backend.agents.multiagent.summarizers.result.self_copy_result_summarizer import (
            SelfCopyResultSummarizer,
        )
        runtime = SubagentRuntime(agent_factory=agent_factory) if agent_factory else SubagentRuntime()
        return (
            SubagentSpecialist(runtime=runtime),
            SelfCopyContextSummarizer(),
            SelfCopyResultSummarizer(),
        )

    return None


def setup_multiagent(
    config: MultiAgentConfig,
    agent_factory: Callable[[], Any] | None = None,
) -> MultiAgentSetup:
    """装配 multi-agent orchestration。

    enabled=false → 返空 setup（lead agent 行为不变）。
    enabled=true → 反射加载 specialist + 凭证检测 + metrics + middleware + tools。
    """
    if not config.enabled:
        return _EMPTY_SETUP

    metrics = MultiAgentMetricsStore(config.metrics_db_path)
    orch_mw = OrchestrationMiddleware(metrics_store=metrics)
    specialist_registry = SpecialistRegistry()
    tools: list[BaseTool] = []

    for name in config.specialists_use:
        loaded = _load_specialist(name, config, agent_factory=agent_factory)
        if loaded is None:
            continue
        specialist, ctx_summarizer, result_summarizer = loaded
        specialist_registry.register(specialist)
        tools.append(
            make_specialist_tool(
                name,
                specialist,
                ctx_summarizer,
                result_summarizer,
                max_steps=config.max_steps,
                timeout_seconds=config.timeout_seconds,
            )
        )

    subagent_provider: SubagentRuntime | None = None
    if agent_factory is not None and "subagent" not in config.specialists_use:
        # Only create standalone delegate_to_subagent tool if "subagent" not already a specialist
        subagent_provider = SubagentRuntime(agent_factory=agent_factory)
        from poirot.backend.agents.multiagent.summarizers.context.self_copy_context_summarizer import (
            SelfCopyContextSummarizer,
        )
        from poirot.backend.agents.multiagent.summarizers.result.self_copy_result_summarizer import (
            SelfCopyResultSummarizer,
        )
        tools.append(
            make_subagent_tool(
                subagent_provider,
                SelfCopyContextSummarizer(),
                SelfCopyResultSummarizer(),
                max_steps=config.subagent_max_steps,
                timeout_seconds=config.subagent_timeout_seconds,
            )
        )

    return MultiAgentSetup(
        specialist_registry=specialist_registry,
        subagent_provider=subagent_provider,
        metrics_store=metrics,
        orchestration_middleware=orch_mw,
        specialist_tools=tuple(tools),
    )
