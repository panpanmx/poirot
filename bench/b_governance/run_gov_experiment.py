"""B.2 上下文治理对照实验 runner。

矩阵：{治理开, 治理关} × {缩窗 8k, 默认窗口} × N 次重复
- 缩窗 8k 组：full 任务（默认 28 子任务），window=8000 → P1@3.2k / P4@6.4k / P5@7.2k
  全程触发，压缩率/外化/熔断/无损性全指标压测。
- 默认窗口组：short 任务（默认 6 子任务），window 由 resolve_window_size 动态解析
  （deepseek-v4-flash→200k），治理近乎空闲 —— 对照证明"治理不空转"。
- 关治理 = make_lead_agent(context_governance=None)（factory 原生支持，零生产改动）。

每次 run 独立装配 runtime（thread_id 隔离）；超时线程弃置并重建 runtime。
用法：
    python bench/b_governance/run_gov_experiment.py [--repeats 3] [--smoke] [--resume] [--only KEY]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from bench.common.env import PROJECT_ROOT, ensure_project_root, load_env
from bench.common.reporter import (
    collect_after_run,
    compression_ratio_from_snapshot,
    parse_reported_ratio,
)
from bench.common.runtime import build_governance_runtime, run_with_timeout, shutdown_runtime
from bench.common.tokens import estimate_cost_usd
from bench.b_governance.build_long_task import TASKS_PATH, build_task_set, check_completion

RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "gov"

CELLS = [
    {"key": "gov_on_8k", "gov": True, "window": 8000, "task_key": "full"},
    {"key": "gov_off_8k", "gov": False, "window": 8000, "task_key": "full"},
    {"key": "gov_on_default", "gov": True, "window": None, "task_key": "short"},
    {"key": "gov_off_default", "gov": False, "window": None, "task_key": "short"},
]

TIMEOUT_S = 900.0


def _load_done(runs_path) -> set[str]:
    done = set()
    if runs_path.exists():
        for line in runs_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["run_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description="治理对照实验")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--smoke", action="store_true", help="full=8/short=4/repeats=1 快速验证")
    parser.add_argument("--resume", action="store_true", help="跳过已完成 run_id")
    parser.add_argument("--only", default=None, help="只跑指定 cell key")
    parser.add_argument("--timeout", type=float, default=TIMEOUT_S)
    args = parser.parse_args()

    ensure_project_root()
    load_env()

    n_full, n_short = (8, 4) if args.smoke else (28, 6)
    repeats = 1 if args.smoke else args.repeats
    tasks = build_task_set(n_full, n_short)
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASKS_PATH.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[info] 任务集: full={n_full} 子任务 / short={n_short} 子任务, repeats={repeats}")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    runs_path = RUNS_DIR / "runs.jsonl"
    done = _load_done(runs_path) if args.resume else set()

    cells = [c for c in CELLS if args.only is None or c["key"] == args.only]
    total = len(cells) * repeats
    finished = 0

    for cell in cells:
        text = tasks[cell["task_key"]]["text"]
        subtasks = tasks[cell["task_key"]]["tasks"]
        for r in range(1, repeats + 1):
            run_id = f"{cell['key']}-r{r}"
            finished += 1
            if run_id in done:
                print(f"[skip] {run_id} 已完成")
                continue
            print(f"\n[{finished}/{total}] {run_id} "
                  f"(governance={'on' if cell['gov'] else 'off'}, "
                  f"window={cell['window'] or 'default'}, task={cell['task_key']})")

            runtime = build_governance_runtime(
                expert_mode=False,
                provider=os.environ.get("POIROT_PROVIDER", "sub2api"),
                logs_root=RUNS_DIR,
                governance_enabled=cell["gov"],
                window_override=cell["window"],
            )

            t0 = time.time()
            result, timed_out = run_with_timeout(
                lambda: runtime.run_question(question=text, run_id=run_id),
                timeout_s=args.timeout,
            )
            duration = time.time() - t0

            if timed_out:
                # 超时线程还在旧 runtime 上跑 → 弃用旧 runtime，本次记录为 timeout
                shutdown_runtime(runtime)
                rec = {
                    "run_id": run_id,
                    "cell": cell["key"],
                    "governance_enabled": cell["gov"],
                    "window_override": cell["window"],
                    "task_key": cell["task_key"],
                    "status": "timeout",
                    "duration_s": round(duration, 1),
                }
                print(f"  [timeout] {duration:.0f}s")
            else:
                datum = collect_after_run(runtime, result, duration_s=duration)
                completion = check_completion(
                    (datum.final_report or "") + "\n" + (datum.last_ai_content or ""),
                    subtasks,
                )
                measured = compression_ratio_from_snapshot(datum.snapshot_path, datum.summary_text)
                water = [
                    {"event": e.get("event"), "stage": e.get("stage"),
                     "fraction": e.get("fraction", e.get("fraction_after"))}
                    for e in datum.compaction_events
                ]
                gov = datum.governance or {}
                final_fraction = (gov.get("default") or {}).get("budget", {}).get("fraction")
                rec = {
                    "run_id": run_id,
                    "cell": cell["key"],
                    "governance_enabled": cell["gov"],
                    "window_override": cell["window"],
                    "task_key": cell["task_key"],
                    "status": "ok",
                    "duration_s": round(datum.duration_s, 1),
                    "usage": datum.usage,
                    "cost_usd": round(estimate_cost_usd(datum.usage) or 0.0, 4),
                    "completion": completion,
                    "externalized_count": datum.externalized_count,
                    "externalized_tokens_saved": datum.externalized_tokens_saved,
                    "budget_stop_count": datum.budget_stop_count,
                    "p4_events": sum(1 for e in datum.compaction_events if e.get("stage") == "P4"),
                    "p1_events": sum(1 for e in datum.compaction_events if e.get("stage") == "P1"),
                    "p5_events": sum(1 for e in datum.compaction_events if e.get("stage") == "P5"),
                    "measured_ratio": measured,
                    "reported_ratio": parse_reported_ratio(datum.summary_text),
                    "final_fraction": final_fraction,
                    "water": water,
                    "error": datum.error,
                }
                shutdown_runtime(runtime)
                print(f"  [done] {duration:.0f}s, tokens={datum.usage and datum.usage.get('total_tokens')}, "
                      f"完成率={completion['done_count']}/{completion['done_total']}, "
                      f"P4×{rec['p4_events']} P1×{rec['p1_events']} P5×{rec['p5_events']}")

            with runs_path.open("a", encoding="utf-8") as fw:
                fw.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n[done] 结果 → {runs_path}")
    print("[hint] 下一步: python bench/b_governance/analyze_gov.py")


if __name__ == "__main__":
    main()
