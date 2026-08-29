# -*- coding: utf-8 -*-
"""AppRuntime assembly helper module for benchmarks."""

from __future__ import annotations

import os
import random
import string
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_CST = timezone(timedelta(hours=8))


def _make_thread_id(prefix: str = "bench") -> str:
    ts = datetime.now(_CST).strftime("%Y%m%dT%H%M%S")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{prefix}-{ts}-{suffix}"


def build_full_runtime(
    *,
    expert_mode: bool = True,
    provider: str | None = None,
    logs_root: str | Path | None = None,
    skill_enabled: bool = False,
    skill_db_path: str | Path | None = None,
    skill_dirs: str | Path | None = None,
    multiagent_enabled: bool | None = None,
    sandbox_use: str | None = None,
) -> Any:
    """Build full runtime for benchmarks."""
    from poirot.backend.app.bootstrap import bootstrap_runtime

    provider = provider or os.environ.get("POIROT_PROVIDER", "sub2api")

    if skill_enabled:
        os.environ["POIROT_SKILL_ENABLED"] = "true"
        os.environ["POIROT_SKILL_EVOLVE_ENABLED"] = "true"
        os.environ["POIROT_SKILL_EVAL_ENABLED"] = "true"
        if skill_db_path:
            os.environ["POIROT_SKILL_DB_PATH"] = str(Path(skill_db_path).resolve())
        if skill_dirs:
            d = Path(skill_dirs)
            d.mkdir(parents=True, exist_ok=True)
            os.environ["POIROT_SKILL_DIRS"] = str(d.resolve())
    else:
        os.environ["POIROT_SKILL_ENABLED"] = "false"

    if multiagent_enabled is not None:
        os.environ["POIROT_MULTIAGENT_ENABLED"] = "true" if multiagent_enabled else "false"
    if sandbox_use is not None:
        os.environ["POIROT_SANDBOX_USE"] = sandbox_use

    cli_overrides: dict[str, Any] = {}
    if logs_root is not None:
        cli_overrides["logs_root"] = str(Path(logs_root).resolve())
    return bootstrap_runtime(
        expert_mode=expert_mode,
        provider=provider,
        cli_overrides=cli_overrides or None,
    )


def build_governance_runtime(
    *,
    expert_mode: bool = False,
    provider: str | None = None,
    logs_root: str | Path,
    governance_enabled: bool = True,
    window_override: int | None = None,
) -> Any:
    """Governance runtime build."""
    provider = provider or os.environ.get("POIROT_PROVIDER", "sub2api")
    from poirot.backend.agents.capabilities.registry import CapabilityRegistry
    from poirot.backend.agents.config.loader import load_config
    from poirot.backend.agents.config.model_router import ModelRouter
    from poirot.backend.agents.journal.run_journal import RunJournal
    from poirot.backend.agents.leader.factory import make_lead_agent
    from poirot.backend.agents.reporting.markdown_reporter import MarkdownReporter
    from poirot.backend.agents.runtime.run_manager import RunManager
    from poirot.backend.agents.artifacts.local_store import LocalArtifactStore
    from poirot.backend.app.bootstrap import (
        AppRuntime,
        _build_path_mappings,
        _load_sandbox_provider,
        _resolve_relative_paths,
    )

    # 排除干扰（装配前设 env）
    os.environ["POIROT_SKILL_ENABLED"] = "false"
    os.environ["POIROT_MULTIAGENT_ENABLED"] = "false"
    os.environ["POIROT_MEMORY_USE"] = ""

    logs_root = Path(logs_root).resolve()
    config = load_config(expert_mode=expert_mode, cli_overrides={"logs_root": str(logs_root)})
    config = replace(config, runtime=replace(config.runtime, logs_root=str(logs_root)))
    config = _resolve_relative_paths(config)

    if window_override is not None:
        params = dict(config.context_governance.params)
        params["window"] = int(window_override)
        config = replace(
            config,
            context_governance=replace(config.context_governance, params=params),
        )

    router = ModelRouter()
    model = router.build_single(provider)

    # 沙箱装配（照抄 bootstrap：provider 反射 + make_sandbox_tools 注入 registry，
    # 否则手工组装没有 write_file/read_file，长任务"写报告到沙箱"无法执行）
    sandbox_provider = _load_sandbox_provider(config)
    sandbox_tools: dict = {}
    if sandbox_provider is not None:
        from poirot.backend.agents.sandbox.integration.bootstrap_sandbox import register_sandbox_shutdown
        from poirot.backend.agents.sandbox.integration.tools import make_sandbox_tools

        tools = make_sandbox_tools(
            sandbox_provider,
            allow_host_bash=getattr(config.sandbox, "allow_host_bash", True),
        )
        sandbox_tools = {t.name: t for t in tools}
        register_sandbox_shutdown(sandbox_provider)

    registry = CapabilityRegistry(
        models={"researcher": model, "reporter": model},
        tools=sandbox_tools,
        reporter=MarkdownReporter(),
        artifact_store=LocalArtifactStore(),
    )

    thread_id = _make_thread_id("gov")
    thread_dir = logs_root / "threads" / thread_id
    thread_dir.mkdir(parents=True, exist_ok=True)
    journal = RunJournal(run_id=thread_id, events_path=thread_dir / "thread-events.jsonl")
    journal.append("thread.started", {"expert_mode": expert_mode, "provider": provider,
                                      "governance_enabled": governance_enabled,
                                      "window_override": window_override})

    cg = config.context_governance if governance_enabled else None
    leader = make_lead_agent(
        expert_mode=expert_mode,
        capability_registry=registry,
        context_governance=cg,
        sandbox_provider=sandbox_provider,
    )

    return AppRuntime(
        config=config,
        capability_registry=registry,
        run_manager=RunManager(config),
        researcher_model_name=provider,
        thread_id=thread_id,
        thread_dir=thread_dir,
        thread_journal=journal,
        leader_agent=leader,
    )


def run_with_timeout(fn, timeout_s: float = 300.0, *args, **kwargs):
    """Execute fn with thread timeout."""
    import concurrent.futures

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout_s), False
    except concurrent.futures.TimeoutError:
        return None, True
    finally:
        # wait=False: daemon threads
        pool.shutdown(wait=False)


def shutdown_runtime(runtime: Any) -> None:
    """Shutdown runtime cleanly."""
    try:
        if getattr(runtime, "artifact_server", None) is not None:
            runtime.artifact_server.stop()
    except Exception:
        pass
    try:
        from poirot.backend.agents.memory.bootstrap import shutdown_memory_worker

        shutdown_memory_worker()
    except Exception:
        pass
