from __future__ import annotations

import random
import shutil
import string
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from poirot.backend.agents.artifacts.local_store import LocalArtifactStore
from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.config.loader import load_config
from poirot.backend.agents.config.provider_config import ProviderConfig, select_provider_config
from poirot.backend.agents.config.schema import AppConfig
from poirot.backend.agents.journal.events import utc_now_iso
from poirot.backend.agents.journal.run_journal import RunJournal
from poirot.backend.agents.leader.agent import AgentRunResult, LeaderAgent
from poirot.backend.agents.leader.factory import make_lead_agent
from poirot.backend.agents.reporting.markdown_reporter import MarkdownReporter
from poirot.backend.agents.runtime.run_manager import RunManager
from poirot.backend.agents.agent_tools.available import get_available_tools, select_search_tool

_PROJECT_ROOT = Path(__file__).parents[3]
_CST = timezone(timedelta(hours=8))


def _make_thread_id() -> str:
    ts = datetime.now(_CST).strftime("%Y%m%dT%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"thread-{ts}-{suffix}"


def _build_chat_model(config: ProviderConfig) -> BaseChatModel:
    config.require_api_key()
    if config.provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(model=config.model, api_key=config.api_key)
    if config.provider in ("openai", "qwen"):
        from langchain_openai import ChatOpenAI
        kwargs: dict[str, Any] = {"model": config.model, "api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatOpenAI(**kwargs)
    raise ValueError(f"unsupported provider: {config.provider}")


def _check_node_available() -> bool:
    return shutil.which("npx") is not None


@dataclass
class AppRuntime:
    config: AppConfig
    capability_registry: CapabilityRegistry
    run_manager: RunManager
    researcher_model_name: str
    thread_id: str
    thread_dir: Path
    thread_journal: RunJournal
    leader_agent: LeaderAgent

    def run_question(
        self,
        question: str,
        thread_id: str | None = None,
        user_id: str | None = "default-user",
        run_id: str | None = None,
    ) -> AgentRunResult:
        effective_thread_id = thread_id or self.thread_id
        context = self.run_manager.create_run(
            thread_id=effective_thread_id,
            user_id=user_id,
            run_id=run_id,
            model_name=self.researcher_model_name,
            thread_dir=self.thread_dir,
        )
        self.run_manager.mark_running(context.run_id)
        try:
            result = self.leader_agent.run(question, context)
            self.run_manager.mark_success(context.run_id)
            return result
        except Exception as exc:
            self.run_manager.mark_failed(context.run_id, str(exc))
            raise

    def switch_expert_mode(self, expert_mode: bool) -> AppRuntime:
        """切换 expert 模式，精准重建受影响部分，保留 thread 连续性。

        重建：config + run_manager + leader_agent（依赖 expert_mode 编译参数）。
        保留：thread_id / thread_dir / thread_journal / capability_registry /
        researcher_model_name（checkpointer state 跨模式连续，MCP/models 不重载）。

        返回新 AppRuntime 实例（不可变语义），CLI 用 runtime = runtime.switch_expert_mode(...)。
        """
        new_config = load_config(expert_mode=expert_mode)
        logs_root = Path(new_config.runtime.logs_root)
        if not logs_root.is_absolute():
            logs_root = _PROJECT_ROOT / logs_root
        new_config = replace(
            new_config,
            runtime=replace(new_config.runtime, logs_root=str(logs_root)),
        )
        new_leader = make_lead_agent(
            expert_mode=expert_mode,
            capability_registry=self.capability_registry,
        )
        self.thread_journal.append("mode.switched", {
            "expert_mode": expert_mode,
            "thread_id": self.thread_id,
        })
        return AppRuntime(
            config=new_config,
            capability_registry=self.capability_registry,
            run_manager=RunManager(new_config),
            researcher_model_name=self.researcher_model_name,
            thread_id=self.thread_id,
            thread_dir=self.thread_dir,
            thread_journal=self.thread_journal,
            leader_agent=new_leader,
        )


def bootstrap_runtime(
    expert_mode: bool = False,
    provider: str | None = None,
    model: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AppRuntime:
    config = load_config(expert_mode=expert_mode, cli_overrides=cli_overrides)
    logs_root = Path(config.runtime.logs_root)
    if not logs_root.is_absolute():
        logs_root = _PROJECT_ROOT / logs_root
    config = replace(
        config,
        runtime=replace(config.runtime, logs_root=str(logs_root)),
    )

    # Thread-level setup — journal created BEFORE MCP/LLM loading.
    thread_id = _make_thread_id()
    threads_root = logs_root / "threads"
    thread_dir = threads_root / thread_id
    thread_dir.mkdir(parents=True, exist_ok=True)
    thread_journal = RunJournal(
        run_id=thread_id,
        events_path=thread_dir / "thread-events.jsonl",
    )
    thread_journal.append("thread.started", {
        "expert_mode": expert_mode,
        "provider": provider or "default",
    })

    # LLM construction — 角色化智能路由（deepseek 兜底），或 CLI --provider 强制单 provider。
    from poirot.backend.agents.config.model_router import ModelRouter

    router = ModelRouter()
    if provider:
        researcher_model = router.build_single(provider, model)
        reporter_model = researcher_model
        thread_journal.append("llm.constructed", {
            "mode": "single",
            "provider": provider,
            "model": model or "default",
        })
        researcher_model_name = model or provider
    else:
        researcher_model = router.build_model("researcher")
        reporter_model = router.build_model("reporter")
        thread_journal.append("llm.constructed", {
            "mode": "routed",
            "researcher_chain": router.chain_names("researcher"),
            "reporter_chain": router.chain_names("reporter"),
        })
        researcher_model_name = "routed:" + ",".join(router.chain_names("researcher"))

    # MCP tool loading — logged to thread journal (success or failure).
    tools: dict[str, Any] = {}
    if _check_node_available():
        try:
            mcp_tools = get_available_tools(include_mcp=True)
            for tool in mcp_tools:
                tools[tool.name] = tool
            search_tool = select_search_tool(mcp_tools)
            if search_tool:
                tools["web_search_mcp"] = search_tool
            thread_journal.append("mcp.loaded", {
                "tools": list(tools.keys()),
                "count": len(tools),
            })
        except Exception as exc:
            thread_journal.append("mcp.load_failed", {"error": str(exc)})
    else:
        thread_journal.append("mcp.skipped", {"reason": "npx not found"})
        print(
            "Node.js / npx not found; MCP search disabled.",
            file=sys.stderr,
        )

    # Registry + LeaderAgent — built ONCE per thread, reused across runs.
    registry = CapabilityRegistry(
        models={"researcher": researcher_model, "reporter": reporter_model},
        tools=tools,
        reporter=MarkdownReporter(),
        artifact_store=LocalArtifactStore(),
    )
    leader_agent = make_lead_agent(expert_mode=expert_mode, capability_registry=registry)
    thread_journal.append("agent.constructed", {
        "expert_mode": expert_mode,
        "middleware_count": 6,
        "tools_count": len(tools),
    })

    return AppRuntime(
        config=config,
        capability_registry=registry,
        run_manager=RunManager(config),
        researcher_model_name=researcher_model_name,
        thread_id=thread_id,
        thread_dir=thread_dir,
        thread_journal=thread_journal,
        leader_agent=leader_agent,
    )
