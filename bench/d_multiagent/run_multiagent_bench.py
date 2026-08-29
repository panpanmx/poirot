"""D.2 多 Agent 对照 runner：单 agent vs 多 agent（同任务集 × N 重复）。

指标采集：
- 委派：state.messages 中 delegate_to_* tool_calls 计数（每次 run）+ 隔离 DB 的
  MultiAgentMetricsStore 4 计数器（selections/invoked/completions/fallbacks）
- 产物跨 Agent 连续性：最终 report 中 specialist 名 / artifacts 引用次数（代理信号）
- 质量：TaskQualityJudge（与 C 同一 L3 评分器，4 维加权 0.50/0.35/0.05/0.10）
- 深度控制：leaf subagent 探针（装配层验证 leaf 无 delegate 工具）
- 成本/耗时：usage_metadata + 计时

用法：
    python bench/d_multiagent/run_multiagent_bench.py [--repeats 3] [--smoke] [--resume] [--only-config multi|single]
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import re
import sys
import time

from bench.common.env import PROJECT_ROOT, ensure_project_root, load_env
from bench.common.reporter import collect_after_run
from bench.common.runtime import build_full_runtime, run_with_timeout, shutdown_runtime
from bench.common.store_io import read_multiagent_records
from bench.common.tokens import estimate_cost_usd

DATA_DIR = PROJECT_ROOT / "bench" / "data" / "d_multiagent"
MULTIAGENT_DB = DATA_DIR / "multiagent.db"
RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "d_multiagent"
TASKS_PATH = DATA_DIR / "tasks.json"

CONFIGS = {
    "multi": {"enabled": True, "label": "多 agent（delegate_to_subagent/claude）"},
    "single": {"enabled": False, "label": "单 agent（无委派工具）"},
}
TIMEOUT_S = 480.0

SPECIALIST_NAMES = ["subagent", "claude"]


def _delegate_calls_from_state(state: dict) -> int:
    n = 0
    for msg in state.get("messages", []) or []:
        for call in getattr(msg, "tool_calls", None) or []:
            if (call.get("name", "") or "").startswith("delegate_to_"):
                n += 1
    return n


def _continuity_refs(text: str) -> dict:
    """最终 report 引用 specialist 产物/路径的次数（产物跨 Agent 连续性代理信号）。"""
    text = text or ""
    artifact_refs = len(re.findall(r"artifacts|artifact[_-]?path|/mnt/poirot", text, re.IGNORECASE))
    name_refs = sum(len(re.findall(rf"\b{n}\b", text, re.IGNORECASE)) for n in SPECIALIST_NAMES)
    return {"artifact_refs": artifact_refs, "specialist_name_refs": name_refs, "total": artifact_refs + name_refs}


def _leaf_probe(runtime) -> dict:
    """深度控制探针：leaf subagent 装配层不得有 delegate 工具（防递归）。

    路径：runtime.multiagent_setup.subagent_provider.agent_factory
    （MultiAgentSetup 无 agent_factory 字段；agent_factory 在 SubagentRuntime 上）。
    """
    setup = getattr(runtime, "multiagent_setup", None)
    probe = {"setup_present": setup is not None}
    if setup is None:
        return probe
    # agent_factory 在 SubagentRuntime（subagent_provider）上，不在 setup 上
    subagent_rt = getattr(setup, "subagent_provider", None)
    factory = getattr(subagent_rt, "agent_factory", None) if subagent_rt else None
    probe["subagent_provider_present"] = subagent_rt is not None
    probe["agent_factory_configured"] = factory is not None
    if factory is not None:
        try:
            leaf = factory()
            for attr in ("tools", "bound", "_tools"):
                tools = getattr(leaf, attr, None) or []
                if tools:
                    names = [getattr(t, "name", str(t)) for t in tools]
                    probe["leaf_tool_names"] = names
                    probe["leaf_has_delegate"] = any(n.startswith("delegate_to_") for n in names)
                    break
        except Exception as exc:  # noqa: BLE001
            probe["leaf_probe_error"] = str(exc)
    leader_delegate = []
    for t in getattr(setup, "specialist_tools", []) or []:
        leader_delegate.append(getattr(t, "name", str(t)))
    probe["leader_delegate_tools"] = leader_delegate
    return probe


def _judge_sync(llm, task_id: str, trace: str, output: str) -> dict | None:
    from poirot.backend.agents.skill.eval.analyzers.task_quality_judge import TaskQualityJudge

    judge = TaskQualityJudge(llm, None)
    try:
        score = asyncio.run(judge.judge_task(task_id, trace, output[:20000]))
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] judge 失败: {exc}", file=sys.stderr)
        return None
    return dataclasses.asdict(score) if score else None


def main() -> None:
    parser = argparse.ArgumentParser(description="多 agent 对照 runner")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--smoke", action="store_true", help="只跑第 1 个任务 × 1 重复")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--only-config", choices=list(CONFIGS), default=None)
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S)
    args = parser.parse_args()

    ensure_project_root()
    load_env()

    if not TASKS_PATH.exists():
        print(f"[error] 缺任务集，先跑 build_tasks.py: {TASKS_PATH}", file=sys.stderr)
        sys.exit(1)
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    if args.smoke:
        tasks = tasks[:1]
    repeats = 1 if args.smoke else args.repeats

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    runs_path = RUNS_DIR / "runs.jsonl"
    done = set()
    if args.resume and runs_path.exists():
        for line in runs_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["run_id"])
                except (json.JSONDecodeError, KeyError):
                    pass

    from poirot.backend.agents.config.model_router import ModelRouter

    llm = ModelRouter().build_single(os.environ.get("POIROT_PROVIDER", "sub2api"))

    configs = [c for c in CONFIGS if args.only_config is None or c == args.only_config]
    total = len(configs) * len(tasks) * repeats
    finished = 0

    for cfg in configs:
        os.environ["POIROT_MULTIAGENT_ENABLED"] = "true" if CONFIGS[cfg]["enabled"] else "false"
        os.environ["POIROT_MULTIAGENT_DB_PATH"] = str(MULTIAGENT_DB)
        runtime = build_full_runtime(
            expert_mode=True,
            provider=os.environ.get("POIROT_PROVIDER", "sub2api"),
            logs_root=RUNS_DIR,
            multiagent_enabled=CONFIGS[cfg]["enabled"],
        )
        probe = _leaf_probe(runtime) if cfg == "multi" else {}
        print(f"\n[info] 配置 {cfg}: {CONFIGS[cfg]['label']}（DB={MULTIAGENT_DB}）")
        if probe:
            print(f"[info] leaf 探针: {json.dumps(probe, ensure_ascii=False)}")

        for t in tasks:
            for r in range(1, repeats + 1):
                run_id = f"{cfg}-{t['task_id']}-r{r}"
                finished += 1
                if run_id in done:
                    print(f"[skip] {run_id}")
                    continue
                print(f"\n[{finished}/{total}] {run_id} (cls={t['cls']})")
                t0 = time.time()
                try:
                    result, timed_out = run_with_timeout(
                        lambda: runtime.run_question(question=t["text"], run_id=run_id),
                        timeout_s=args.timeout,
                    )
                except Exception as exc:
                    print(f"  [error] run 异常 ({exc})，等待 15s 后重试...", file=sys.stderr)
                    time.sleep(15)
                    try:
                        result, timed_out = run_with_timeout(
                            lambda: runtime.run_question(question=t["text"], run_id=run_id),
                            timeout_s=args.timeout,
                        )
                    except Exception as exc2:
                        print(f"  [error] 重试仍失败: {exc2}", file=sys.stderr)
                        rec = {"run_id": run_id, "config": cfg, "task_id": t["task_id"],
                               "cls": t["cls"], "status": "error", "error": str(exc2),
                               "duration_s": round(time.time() - t0, 1)}
                        with runs_path.open("a", encoding="utf-8") as fw:
                            fw.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        continue

                duration = time.time() - t0
                if timed_out:
                    rec = {"run_id": run_id, "config": cfg, "task_id": t["task_id"],
                           "cls": t["cls"], "status": "timeout", "duration_s": round(duration, 1)}
                    print(f"  [timeout] {duration:.0f}s")
                else:
                    datum = collect_after_run(runtime, result, duration_s=duration)
                    state = getattr(result, "state", {}) or {}
                    output = (datum.final_report or "") + "\n" + (datum.last_ai_content or "")
                    score = _judge_sync(llm, t["task_id"], t["text"], output)
                    rec = {
                        "run_id": run_id, "config": cfg, "task_id": t["task_id"],
                        "cls": t["cls"], "status": "ok",
                        "duration_s": round(datum.duration_s, 1),
                        "usage": datum.usage,
                        "cost_usd": round(estimate_cost_usd(datum.usage) or 0.0, 4),
                        "judge_score": score and score.get("overall_score"),
                        "delegate_calls": _delegate_calls_from_state(state),
                        "continuity": _continuity_refs(output),
                        "error": datum.error,
                    }
                    print(f"  [done] {duration:.0f}s, tokens={datum.usage and datum.usage.get('total_tokens')}, "
                          f"judge={rec['judge_score']}, delegate={rec['delegate_calls']}, "
                          f"continuity={rec['continuity']['total']}")

                with runs_path.open("a", encoding="utf-8") as fw:
                    fw.write(json.dumps(rec, ensure_ascii=False) + "\n")
                time.sleep(5)

        # 配置级快照：委派计数器（隔离 DB，{表名: rows}）+ 探针
        snap = {
            "config": cfg,
            "delegate_metrics": read_multiagent_records(MULTIAGENT_DB) if CONFIGS[cfg]["enabled"] else {},
            "leaf_probe": probe,
        }
        snap_path = RUNS_DIR / f"snapshot_{cfg}.json"
        snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[info] 快照 → {snap_path}")
        shutdown_runtime(runtime)

    print(f"\n[done] 结果 → {runs_path}")
    print("[hint] 下一步: python bench/d_multiagent/analyze_multiagent.py")


if __name__ == "__main__":
    main()
