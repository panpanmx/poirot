from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage

from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.state.thread_state import create_initial_thread_state


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    thread_id: str
    final_report: str
    events_path: str
    artifact_path: str | None
    state: dict[str, Any]


@dataclass
class LeaderAgent:
    """Thin shell: invokes compiled graph + collects report + saves artifact.

    ReAct intelligence (multi-turn decisions, tool calls, exit logic) lives
    inside the graph via create_agent + AgentMiddleware. This class only does
    graph.ainvoke() + reporter + artifact + outer config wiring. All logging
    is handled by RunJournalMiddleware inside the graph.
    """

    graph: Any
    capability_registry: CapabilityRegistry

    def run(self, question: str, run_context: Any) -> AgentRunResult:
        initial = create_initial_thread_state(question)
        initial["research_question"] = question
        initial["metadata"] = {"mode": run_context.config.runtime.mode}

        config = {
            "configurable": {
                "mode": run_context.config.runtime.mode,
                "run_id": run_context.run_id,
                "thread_id": run_context.thread_id,
                "journal": run_context.journal,
                "output_dir": str(run_context.output_dir),
                "plan_enabled": run_context.config.runtime.plan_enabled,
                "timezone": run_context.config.runtime.timezone,
                "model": run_context.config.models.researcher_model,
            },
            # F8.5：调高 recursion_limit 让硬预算（30）先生效优雅退出，不靠 recursion limit 硬截断。
            "recursion_limit": 50,
        }

        # MCP tools are async-only StructuredTool; graph must run in async mode.
        final_state = asyncio.run(self.graph.ainvoke(
            {
                "messages": [HumanMessage(content=question)],
                "user_input": question,
                "research_question": question,
            },
            config=config,
        ))

        report_result = self.capability_registry.get_reporter().generate_report(final_state, run_context)

        artifact_path = None
        if run_context.config.reporting.save_artifact:
            artifact = self.capability_registry.get_artifact_store().save_artifact(
                content=report_result.final_report,
                output_dir=run_context.output_dir,
                title="Final Report",
                filename="final_report.md",
                metadata={"mode": run_context.config.runtime.mode},
            )
            artifact_path = artifact.path
            run_context.journal.append(
                "report.generated",
                {
                    "artifact_id": artifact.artifact_id,
                    "title": artifact.title,
                    "path": artifact.path,
                    "mode": run_context.config.runtime.mode,
                },
            )

        return AgentRunResult(
            run_id=run_context.run_id,
            thread_id=run_context.thread_id,
            final_report=report_result.final_report,
            events_path=str(run_context.events_path),
            artifact_path=artifact_path,
            state=final_state if isinstance(final_state, dict) else dict(final_state),
        )
