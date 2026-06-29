from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poirot.backend.agents.artifacts.local_store import LocalArtifactStore
from poirot.backend.agents.capabilities.models.base import FakeModel
from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.config.loader import load_config
from poirot.backend.agents.config.schema import AppConfig
from poirot.backend.agents.leader.agent import AgentRunResult
from poirot.backend.agents.leader.factory import make_lead_agent
from poirot.backend.agents.middlewares.middleware_manager import MiddlewareManager
from poirot.backend.agents.middlewares.run_journal_middleware import RunJournalMiddleware
from poirot.backend.agents.middlewares.system_context_middleware import SystemContextMiddleware
from poirot.backend.agents.middlewares.title_middleware import TitleMiddleware
from poirot.backend.agents.middlewares.todo_middleware import TodoMiddleware
from poirot.backend.agents.middlewares.tool_call_middleware import ToolCallMiddleware
from poirot.backend.agents.reporting.markdown_reporter import MarkdownReporter
from poirot.backend.agents.runtime.run_manager import RunManager
from poirot.backend.agents.tools.base import FakeSearchTool


@dataclass
class AppRuntime:
    config: AppConfig
    capability_registry: CapabilityRegistry
    middleware_manager: MiddlewareManager
    run_manager: RunManager

    def run_question(
        self,
        question: str,
        thread_id: str = "default-thread",
        user_id: str | None = "default-user",
        run_id: str | None = None,
    ) -> AgentRunResult:
        context = self.run_manager.create_run(
            thread_id=thread_id,
            user_id=user_id,
            run_id=run_id,
        )
        self.run_manager.mark_running(context.run_id)
        agent = make_lead_agent(
            capability_registry=self.capability_registry,
            middleware_manager=self.middleware_manager,
        )
        try:
            result = agent.run(question, context)
            self.run_manager.mark_success(context.run_id)
            return result
        except Exception as exc:
            self.run_manager.mark_failed(context.run_id, str(exc))
            raise


def bootstrap_runtime(
    mode: str = "general",
    cli_overrides: dict[str, Any] | None = None,
) -> AppRuntime:
    config = load_config(mode=mode, cli_overrides=cli_overrides)
    registry = CapabilityRegistry(
        models={
            "researcher": FakeModel(name=config.models.researcher_model),
            "reporter": FakeModel(name=config.models.reporter_model),
        },
        tools={"web_search_mcp": FakeSearchTool()},
        reporter=MarkdownReporter(),
        artifact_store=LocalArtifactStore(),
    )
    middleware_manager = MiddlewareManager(
        [
            RunJournalMiddleware(),
            TodoMiddleware(),
            SystemContextMiddleware(),
            ToolCallMiddleware(),
            TitleMiddleware(),
        ]
    )
    return AppRuntime(
        config=config,
        capability_registry=registry,
        middleware_manager=middleware_manager,
        run_manager=RunManager(config),
    )
