"""AppRuntime 装配公共层。

两种装配模式（约束：不修改任何生产代码，import 范式照抄 tests/v1/integration/）：
1. build_full_runtime —— 走 bootstrap_runtime 完整装配（skill/multiagent/sandbox/MCP 全链，
   供 A 跑 GAIA、C 跑 skill、D 跑 multiagent）；env 定制在装配前注入。
2. build_governance_runtime —— 手工组装变体（仿 test_minimum_agent_loop.py），
   支持关治理（make_lead_agent(context_governance=None)）与缩窗（params.window），
   供 B 上下文治理对照实验。关闭 skill/multiagent/memory 排除干扰。

env 设置顺序约定：调用方先 load_env() 加载 .env，本模块再显式设置/覆盖，最后装配。
"""

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
    provider: str = "deepseek",
    logs_root: str | Path | None = None,
    skill_enabled: bool = False,
    skill_db_path: str | Path | None = None,
    skill_dirs: str | Path | None = None,
    multiagent_enabled: bool | None = None,
    sandbox_use: str | None = None,
) -> Any:
    """完整装配（bootstrap_runtime）。env 定制必须先于装配生效。

    - skill_enabled=True 时同时打开 EVOLVE/EVAL（取进化闭环数字的前提）。
      注意 build_skill_manager 要求 skill_dirs 至少一个存在——项目根无 skills/ 目录，
      必须传 skill_dirs 指向存在的目录（bench 自带用户 skill 目录）。
    - multiagent_enabled=None 表示不干预（继承 .env）。
    - sandbox_use 默认 None 继承 .env（local 沙箱已配）。
    """
    from poirot.backend.app.bootstrap import bootstrap_runtime

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
    provider: str = "deepseek",
    logs_root: str | Path,
    governance_enabled: bool = True,
    window_override: int | None = None,
) -> Any:
    """治理实验用手工组装（零生产改动）。

    关键点（探索/Plan 验证）：
    - make_lead_agent(context_governance=None) → _build_middlewares 跳过整个治理层。
    - context_governance.params={"window": N} → 缩窗压测（P4@0.8N、P5@0.9N）。
    - 关 skill/multiagent/memory 排除干扰（env 在 load_config 前设好）。
    """
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
    """在单线程池里执行 fn，超时后丢弃线程（graph 不可中断，线程随进程退出）。

    返回 (result | None, timed_out: bool)。异常透传。

    注意：超时线程会继续跑完并写自己的日志目录（无害，调用方忽略即可）；
    **调用方收到 timed_out=True 后必须 shutdown 并重建 runtime**，禁止复用旧
    runtime 跑下一题（两个 graph 并发共享 state 会互相污染）。
    """
    import concurrent.futures

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout_s), False
    except concurrent.futures.TimeoutError:
        return None, True
    finally:
        # wait=False：不阻塞等超时线程（3.9+ 工作线程是 daemon，进程退出不等待）
        pool.shutdown(wait=False)


def shutdown_runtime(runtime: Any) -> None:
    """安全收尾：停 artifact server / memory worker（若装配）。"""
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
