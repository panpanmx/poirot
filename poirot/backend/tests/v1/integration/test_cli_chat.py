from langchain_core.language_models.fake_chat_models import FakeListChatModel

from poirot.backend.agents.artifacts.local_store import LocalArtifactStore
from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.config.loader import load_config
from poirot.backend.agents.journal.run_journal import RunJournal
from poirot.backend.agents.leader.factory import make_lead_agent
from poirot.backend.agents.reporting.markdown_reporter import MarkdownReporter
from poirot.backend.agents.runtime.run_manager import RunManager
from poirot.backend.app.bootstrap import AppRuntime


def test_chat_run_question_produces_report_and_logs(tmp_path) -> None:
    config = load_config(mode="general", cli_overrides={"logs_root": str(tmp_path)})
    model = FakeListChatModel(responses=["你好！我是 Poirot 研究助手。"])
    registry = CapabilityRegistry(
        models={"researcher": model, "reporter": model},
        tools={},
        reporter=MarkdownReporter(),
        artifact_store=LocalArtifactStore(),
    )
    thread_dir = tmp_path / "threads" / "thread-chat"
    thread_dir.mkdir(parents=True, exist_ok=True)
    runtime = AppRuntime(
        config=config,
        capability_registry=registry,
        run_manager=RunManager(config),
        researcher_model_name="fake-test-model",
        thread_id="thread-chat",
        thread_dir=thread_dir,
        thread_journal=RunJournal("thread-chat", thread_dir / "thread-events.jsonl"),
        leader_agent=make_lead_agent(capability_registry=registry),
    )

    result = runtime.run_question("你好")

    assert result.final_report
    assert result.run_id
    assert "events.jsonl" in result.events_path
