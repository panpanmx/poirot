from __future__ import annotations

import argparse
import sys
from typing import Sequence

from dotenv import load_dotenv

load_dotenv()

from poirot.backend.agents.capabilities.models.chat_adapter_factory import create_chat_adapter
from poirot.backend.agents.config.provider_config import select_provider_config
from poirot.backend.app.bootstrap import bootstrap_runtime
from poirot.backend.app.cli.banner import render_banner


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
    chat_parser = subparsers.add_parser("chat")
    chat_parser.add_argument("--provider", default=None)
    chat_parser.add_argument("--model", default=None)

    args = parser.parse_args(argv)
    if args.command is None:
        return run_chat(provider=args.provider, model=args.model)
    if args.command == "run":
        overrides = {}
        if args.logs_root:
            overrides["logs_root"] = args.logs_root
        if args.no_artifact:
            overrides["save_artifact"] = False
        runtime = bootstrap_runtime(mode=args.mode, cli_overrides=overrides)
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
    if args.command == "chat":
        return run_chat(provider=args.provider, model=args.model)
    return 1


def run_chat(provider: str | None = None, model: str | None = None) -> int:
    config = select_provider_config(provider=provider, model=model)
    adapter = create_chat_adapter(config)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    print(render_banner("POIROT"))
    print(f"provider: {config.provider}")
    print(f"model: {config.model}")
    print("type /exit or /quit to leave")
    history: list[tuple[str, str]] = []
    while True:
        try:
            prompt = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if prompt in {"/exit", "/quit"}:
            return 0
        if not prompt:
            continue
        history.append(("user", prompt))
        print()
        chunks: list[str] = []
        for chunk in adapter.stream(_format_prompt(history)):
            print(chunk, end="", flush=True)
            chunks.append(chunk)
        print()
        history.append(("assistant", "".join(chunks)))


def _format_prompt(history: list[tuple[str, str]]) -> str:
    return "\n".join(f"{role}: {content}" for role, content in history)


if __name__ == "__main__":
    raise SystemExit(main())
