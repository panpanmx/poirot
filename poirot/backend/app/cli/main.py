from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Sequence

from dotenv import load_dotenv

load_dotenv()

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

from poirot.backend.app.bootstrap import bootstrap_runtime, AppRuntime
from poirot.backend.app.cli.banner import render_banner
from poirot.backend.app.cli.commands import handle_command
from poirot.backend.app.cli.stream_handler import StreamRenderer
from poirot.backend.app.services.stream_service import PoirotStreamClient
from poirot.backend.agents.leader.agent import _resolve_actual_model_name


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="poirot")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("question")
    run_parser.add_argument("--mode", choices=("fast", "general", "expert"), default="general")
    run_parser.add_argument("--thread-id", default="default-thread")
    run_parser.add_argument("--run-id", default=None)
    run_parser.add_argument("--logs-root", default=None)
    run_parser.add_argument("--no-artifact", action="store_true")

    subparsers.add_parser("chat")

    args = parser.parse_args(argv)

    if args.command is None or args.command == "chat":
        return run_chat(provider=args.provider, model=args.model)

    if args.command == "run":
        overrides: dict = {}
        if args.logs_root:
            overrides["logs_root"] = args.logs_root
        if args.no_artifact:
            overrides["save_artifact"] = False
        runtime = bootstrap_runtime(
            mode=args.mode,
            provider=args.provider,
            model=args.model,
            cli_overrides=overrides,
        )
        result = runtime.run_question(
            question=args.question,
            thread_id=args.thread_id,
            run_id=args.run_id,
        )
        print(result.final_report)
        print(f"run_id: {result.run_id}")
        print(f"events_jsonl: {result.events_path}")
        if result.artifact_path:
            print(f"final_report_md: {result.artifact_path}")
        return 0

    return 1


def run_chat(provider: str | None = None, model: str | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    # bootstrap 在 asyncio.run 之前（同步阶段），避免 MCP 的 asyncio.run 嵌套
    runtime = bootstrap_runtime(provider=provider, model=model)
    return asyncio.run(_run_chat_async(runtime, provider, model))


def _build_stream_config(runtime: AppRuntime, run_context: Any) -> dict:
    """构建 graph config（stream 用，与 LeaderAgent.run 一致）。"""
    return {
        "configurable": {
            "mode": run_context.config.runtime.mode,
            "run_id": run_context.run_id,
            "thread_id": run_context.thread_id,
            "journal": run_context.journal,
            "output_dir": str(run_context.output_dir),
            "plan_enabled": run_context.config.runtime.plan_enabled,
            "timezone": run_context.config.runtime.timezone,
            "model": _resolve_actual_model_name(runtime.capability_registry),
        },
        "recursion_limit": 300,
    }


async def _run_chat_async(runtime: AppRuntime, provider: str | None, model: str | None) -> int:
    console = Console()
    session: PromptSession = PromptSession()
    renderer = StreamRenderer(console=console)
    cli_state: dict[str, Any] = {"pending_mode": None}

    def _print_status() -> None:
        mode = runtime.config.runtime.mode
        model_name = _resolve_actual_model_name(runtime.capability_registry)
        console.print(f"[dim]Poirot v1.0.0 | mode: {mode} | {model_name} | thread: {runtime.thread_id[:20]}[/dim]")

    provider_label = provider or "default"
    console.print(render_banner("POIROT"))
    _print_status()
    console.print("type /exit or /quit to leave\n")

    # 开场白——用 stream 流式展示
    try:
        ctx = runtime.run_manager.create_run(
            thread_id=runtime.thread_id,
            user_id="default-user",
            run_id=None,
            model_name=runtime.researcher_model_name,
            thread_dir=runtime.thread_dir,
        )
        runtime.run_manager.mark_running(ctx.run_id)
        config = _build_stream_config(runtime, ctx)
        client = PoirotStreamClient(graph=runtime.leader_agent.graph, config=config)
        async for event in client.stream(
            "请用中文简短介绍你自己：你是谁，你能做什么，用户可以如何使用你。回复控制在100字以内，语气友好自然。"
        ):
            renderer.render(event)
        runtime.run_manager.mark_success(ctx.run_id)
    except Exception:
        pass

    # 主循环
    while True:
        try:
            with patch_stdout():
                user_input = await session.prompt_async("> ")
        except (EOFError, KeyboardInterrupt):
            # Ctrl+C / Ctrl+D 输入时退出进程
            console.print()
            return 0

        prompt = user_input.strip()
        if prompt in {"/exit", "/quit"}:
            return 0
        if not prompt:
            continue
        if prompt.startswith("/"):
            should_exit = handle_command(prompt, console, renderer, cli_state, runtime)
            if should_exit:
                return 0

            # /mode 切换：下轮重建 agent
            if cli_state.get("pending_mode"):
                new_mode = cli_state["pending_mode"]
                cli_state["pending_mode"] = None
                runtime = bootstrap_runtime(provider=provider, model=model, mode=new_mode)
                _print_status()
                console.print(f"[green]Switched to {new_mode} mode[/green]\n")
            continue

        # 流式研究
        try:
            ctx = runtime.run_manager.create_run(
                thread_id=runtime.thread_id,
                user_id="default-user",
                run_id=None,
                model_name=runtime.researcher_model_name,
                thread_dir=runtime.thread_dir,
            )
            runtime.run_manager.mark_running(ctx.run_id)
            config = _build_stream_config(runtime, ctx)
            client = PoirotStreamClient(graph=runtime.leader_agent.graph, config=config)

            async for event in client.stream(prompt):
                renderer.render(event)

            runtime.run_manager.mark_success(ctx.run_id)
            console.print(f"\n[dim]run_id: {ctx.run_id} | events: {ctx.events_path}[/dim]\n")
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[yellow]⚠ Interrupted[/yellow]\n")
            runtime.run_manager.mark_failed(ctx.run_id, "interrupted")
            continue
        except Exception as exc:
            console.print(f"\n[red]✗ Error: {exc}[/red]\n")
            runtime.run_manager.mark_failed(ctx.run_id, str(exc))
            continue


if __name__ == "__main__":
    raise SystemExit(main())
