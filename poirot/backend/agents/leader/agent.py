from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.middlewares.middleware_manager import MiddlewareManager
from poirot.backend.agents.react.runner import ReActRunner
from poirot.backend.agents.state.reducers import merge_thread_state
from poirot.backend.agents.state.thread_state import create_initial_thread_state


@dataclass(frozen=True)
class AgentRunResult:
    run_id: str
    thread_id: str
    final_report: str
    draft_report: str
    events_path: str
    artifact_path: str | None
    state: dict[str, Any]


@dataclass
class LeaderAgent:
    capability_registry: CapabilityRegistry
    middleware_manager: MiddlewareManager | None = None
    runner: ReActRunner | None = None

    def __post_init__(self) -> None:
        if self.runner is None:
            self.runner = ReActRunner(
                capability_registry=self.capability_registry,
                middleware_manager=self.middleware_manager,
            )

    def run(self, question: str, run_context: Any) -> AgentRunResult:
        self._validate_dependencies()
        state = create_initial_thread_state(question)
        state = merge_thread_state(
            state,
            {
                "research_question": question,
                "metadata": {"mode": run_context.config.runtime.mode},
            },
        )
        if self.middleware_manager:
            state = self.middleware_manager.run_hook("before_agent", state, run_context)
            state = self.middleware_manager.run_hook("before_model", state, run_context)

        assert self.runner is not None
        state = self.runner.run(state, run_context)
        report_result = self.capability_registry.get_reporter().generate_report(state, run_context)

        artifact_path = None
        artifacts = tuple(report_result.artifacts)
        if run_context.config.reporting.save_artifact:
            artifact = self.capability_registry.get_artifact_store().save_artifact(
                content=report_result.final_report,
                output_dir=run_context.output_dir,
                title="Final Report",
                filename="final_report.md",
                metadata={"mode": run_context.config.runtime.mode},
            )
            artifact_path = artifact.path
            artifacts = artifacts + (artifact,)
            run_context.journal.append(
                "report.generated",
                {
                    "artifact_id": artifact.artifact_id,
                    "title": artifact.title,
                    "path": artifact.path,
                    "mode": run_context.config.runtime.mode,
                },
            )

        state = merge_thread_state(
            state,
            {
                "draft_report": report_result.draft_report,
                "final_report": report_result.final_report,
                "artifacts": list(artifacts),
            },
        )
        if self.middleware_manager:
            state = self.middleware_manager.run_hook("after_model", state, run_context)
            state = self.middleware_manager.run_hook("after_agent", state, run_context)

        return AgentRunResult(
            run_id=run_context.run_id,
            thread_id=run_context.thread_id,
            final_report=report_result.final_report,
            draft_report=report_result.draft_report,
            events_path=str(run_context.events_path),
            artifact_path=artifact_path,
            state=state,
        )

    def _validate_dependencies(self) -> None:
        self.capability_registry.get_reporter()
        self.capability_registry.get_artifact_store()
