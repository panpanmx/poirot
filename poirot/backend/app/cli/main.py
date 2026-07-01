from __future__ import annotations

import argparse
import sys
from typing import Sequence

from dotenv import load_dotenv

load_dotenv()

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
    runtime = bootstrap_runtime(provider=provider, model=model)
    provider_label = provider or "default"
    print(render_banner("POIROT"))
    print(f"provider: {provider_label}")
    print("type /exit or /quit to leave\n")

    # LLM-generated greeting — no hardcoded intro string
    try:
        greeting = runtime.run_question(
            "请用中文简短介绍你自己：你是谁，你能做什么，用户可以如何使用你。回复控制在100字以内，语气友好自然。",
        )
        # Strip the H1 title line (MarkdownReporter prepends `# {question}`)
        lines = greeting.final_report.splitlines()
        body = "\n".join(l for l in lines if not l.startswith("# ")).strip()
        if body:
            print(body)
            print()
    except Exception:
        pass  # greeting failure must not block chat entry

    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if prompt in {"/exit", "/quit"}:
            return 0
        if not prompt:
            continue
        result = runtime.run_question(prompt)
        lines = result.final_report.splitlines()
        body = "\n".join(l for l in lines if not l.startswith("# ")).strip()
        print()
        print(body or result.final_report)
        print(f"run_id: {result.run_id} | events: {result.events_path}")
        print()


if __name__ == "__main__":
    raise SystemExit(main())
