"""C.2 Skill 评测 runner：跑任务集 → L1 打点采集 + L3 显式评测。

每 run 结束后：
- L1：store.get_metrics(skill_id) 读 4 计数器（selections/applied/completions/fallbacks
  → 4 rate），全 skill 快照入 runs.jsonl（同一 DB 跨 phase 累积，analyze 取快照差值）
- L3 显式：eval_layer.task_judge.judge_task(task_id, 任务文本, 最终输出) → 4 维加权分
  （0.50/0.35/0.05/0.10），进 skills.db 的 task_scores 表 + 本地快照
- 工具覆盖：skill.allowed_tools ∩ runtime 可用工具（registry.tools + builtin）→ 口径标注

用法：
    python bench/c_skill/run_skill_bench.py [--phase baseline|post] [--smoke] [--resume] [--no-task-judge]
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time

from bench.common.env import PROJECT_ROOT, ensure_project_root, load_env
from bench.common.reporter import collect_after_run
from bench.common.runtime import build_full_runtime, run_with_timeout, shutdown_runtime

DATA_DIR = PROJECT_ROOT / "bench" / "data" / "c_skill"
SKILL_DB = DATA_DIR / "skills.db"
USER_SKILL_DIR = DATA_DIR / "user_skills"  # build_skill_manager 要求存在目录
RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "c_skill"
TASKS_PATH = DATA_DIR / "tasks.json"

TIMEOUT_S = 480.0


def _task_judge_sync(eval_layer, task_id: str, trace: str, output: str) -> dict | None:
    judge = eval_layer.task_judge
    if judge is None:
        return None
    try:
        score = asyncio.run(judge.judge_task(task_id, trace, output))
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] task judge 失败: {exc}", file=sys.stderr)
        return None
    if score is None:
        return None
    return dataclasses.asdict(score)


def _skill_snapshot(runtime) -> dict:
    """全 skill 4 计数器快照（name → metrics dict）。"""
    mgr = runtime.skill_manager
    if mgr is None:
        return {}
    snap = {}
    for info in mgr.list_skills():
        m = mgr.store.get_metrics(info["skill_id"])
        if m is not None:
            snap[info["name"]] = {
                "skill_id": info["skill_id"],
                "selections": m.selections,
                "applied": m.applied,
                "completions": m.completions,
                "fallbacks": m.fallbacks,
                "applied_rate": round(m.applied_rate, 4),
                "completion_rate": round(m.completion_rate, 4),
                "effective_rate": round(m.effective_rate, 4),
                "fallback_rate": round(m.fallback_rate, 4),
                "allowed_tools": list(info["allowed_tools"]),
            }
    return snap


def _tool_coverage(runtime) -> dict:
    """skill.allowed_tools 与 runtime 实际可用工具的覆盖映射（口径标注用）。"""
    from poirot.backend.agents.agent_tools.available import get_available_tools

    registry_tools = set(getattr(runtime.capability_registry, "tools", {}) or {})
    builtin = {t.name for t in get_available_tools()}
    available = registry_tools | builtin
    coverage = {}
    mgr = runtime.skill_manager
    if mgr is None:
        return coverage
    for info in mgr.list_skills():
        allowed = list(info["allowed_tools"])
        covered = [t for t in allowed if t in available]
        coverage[info["name"]] = {
            "allowed": allowed,
            "covered": covered,
            "missing": [t for t in allowed if t not in available],
            "class": "guidance" if not allowed else ("tool-covered" if covered else "tool-uncovered"),
        }
    return coverage


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill 评测 runner")
    parser.add_argument("--phase", choices=["baseline", "post"], default="baseline")
    parser.add_argument("--smoke", action="store_true", help="只跑前 3 个任务")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-task-judge", action="store_true", help="跳过 L3 LLM 评测")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S)
    args = parser.parse_args()

    ensure_project_root()
    load_env()

    if not TASKS_PATH.exists():
        print(f"[error] 缺任务集，先跑 build_task_set.py: {TASKS_PATH}", file=sys.stderr)
        sys.exit(1)
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]
    if args.smoke:
        tasks = tasks[:3]

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    USER_SKILL_DIR.mkdir(parents=True, exist_ok=True)
    SKILL_DB.parent.mkdir(parents=True, exist_ok=True)

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

    runtime = build_full_runtime(
        expert_mode=True,
        provider=os.environ.get("POIROT_PROVIDER", "sub2api"),
        logs_root=RUNS_DIR,
        skill_enabled=True,
        skill_db_path=SKILL_DB,
        skill_dirs=USER_SKILL_DIR,
    )
    print(f"[info] 装配完成，DB={SKILL_DB}，当前 skill 数={len(runtime.skill_manager.list_skills())}")
    print(f"[info] 工具覆盖：{json.dumps(_tool_coverage(runtime), ensure_ascii=False)}")

    scores: list[dict] = []
    for idx, t in enumerate(tasks, 1):
        run_id = f"{args.phase}-{t['task_id']}"
        if run_id in done:
            print(f"[skip] {run_id}")
            continue
        print(f"\n[{idx}/{len(tasks)}] {run_id} (target={t['skill_target']})")
        t0 = time.time()
        result, timed_out = run_with_timeout(
            lambda: runtime.run_question(question=t["text"], run_id=run_id),
            timeout_s=args.timeout,
        )
        duration = time.time() - t0
        if timed_out:
            rec = {"run_id": run_id, "phase": args.phase, "task_id": t["task_id"],
                   "status": "timeout", "duration_s": round(duration, 1)}
            print(f"  [timeout] {duration:.0f}s")
        else:
            datum = collect_after_run(runtime, result, duration_s=duration)
            output = (datum.final_report or "") + "\n" + (datum.last_ai_content or "")
            score = None if args.no_task_judge else _task_judge_sync(
                runtime.skill_manager.get_eval_layer(), t["task_id"], t["text"], output[:20000])
            if score:
                scores.append(score)
            rec = {
                "run_id": run_id, "phase": args.phase, "task_id": t["task_id"],
                "skill_target": t["skill_target"],
                "status": "ok", "duration_s": round(datum.duration_s, 1),
                "usage": datum.usage,
                "task_judge_score": score,
            }
            print(f"  [done] {duration:.0f}s, tokens={datum.usage and datum.usage.get('total_tokens')}, "
                  f"judge={score and round(score.get('overall_score', 0), 3)}")

        with runs_path.open("a", encoding="utf-8") as fw:
            fw.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # phase 快照（全 skill 计数器 + 覆盖 + 评分）
    snap = {
        "phase": args.phase,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "skills": _skill_snapshot(runtime),
        "tool_coverage": _tool_coverage(runtime),
        "task_scores": scores,
    }
    snap_path = RUNS_DIR / f"snapshot_{args.phase}.json"
    snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    # 打印本轮（增量）指标
    print(f"\n[done] 快照 → {snap_path}")
    print(f"[info] 本轮 task judge: {len(scores)} 个（overall 均值 "
          f"{round(sum(s['overall_score'] for s in scores) / len(scores), 3) if scores else '-'}）")
    shutdown_runtime(runtime)


if __name__ == "__main__":
    main()
