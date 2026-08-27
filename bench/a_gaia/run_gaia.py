"""GAIA runner：逐题跑 poirot，输出每题结果到 runs.jsonl。

用法：
    python bench/a_gaia/run_gaia.py [--limit N] [--seed 42] [--resume]
                                    [--timeout-per-question 300]

- 默认全量 165 题；--limit N 按 level 分层抽样（冒烟用）。
- --resume：跳过 runs.jsonl 已完成的 task_id（断点续跑）。
- 进程内 AppRuntime（可拿到 state/usage/治理指标）；每题独立 thread_id 隔离。
- 附件题：附件复制到 .poirot/sandbox/local/uploads/（LocalSandbox 映射目录）。
- 超时：单题 300s 上限（ThreadPoolExecutor 弃线程）。
- 跑 GAIA 时关闭 skill（POIROT_SKILL_ENABLED=false），避免污染 skill 统计。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from bench.common.env import PROJECT_ROOT, data_root, ensure_project_root, load_env
from bench.common.reporter import collect_after_run
from bench.common.runtime import build_full_runtime, run_with_timeout, shutdown_runtime

DATA_DIR = data_root() / "gaia"
RUNS_DIR = data_root() / "runs" / "gaia"
UPLOADS_DIR = PROJECT_ROOT / ".poirot" / "sandbox" / "local" / "uploads"


def _load_questions(limit: int | None, seed: int) -> list[dict]:
    path = DATA_DIR / "gaia_validation.jsonl"
    if not path.exists():
        print(f"[error] 请先运行 download_data.py 生成 {path}", file=sys.stderr)
        sys.exit(1)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit is None or limit >= len(rows):
        return rows
    # 按 level 分层抽样
    rng = random.Random(seed)
    by_level: dict = {}
    for r in rows:
        by_level.setdefault(r["level"], []).append(r)
    picked: list[dict] = []
    per_level = max(1, limit // max(len(by_level), 1))
    for level in sorted(by_level):
        pool = by_level[level]
        picked.extend(rng.sample(pool, min(per_level, len(pool))))
        if len(picked) >= limit:
            break
    if len(picked) < limit:
        remaining = [r for r in rows if r not in picked]
        picked.extend(rng.sample(remaining, limit - len(picked)))
    picked.sort(key=lambda r: r["task_id"])
    return picked


def _load_done() -> set[str]:
    path = RUNS_DIR / "runs.jsonl"
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                done.add(json.loads(line)["task_id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def _copy_attachment(question: dict) -> str | None:
    """附件复制到 uploads 映射目录（保留原文件名），返回目标路径或 None。

    兼容两种 schema：旧版 file_path（完整路径）/ 新版 file_name（仅文件名）。
    """
    file_name = question.get("file_name") or question.get("file_path") or ""
    if not file_name:
        return None
    fname = Path(file_name).name  # 纯文件名
    src = DATA_DIR / "attachments" / f"{question['task_id']}{Path(fname).suffix}"
    if not src.exists():
        return None
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dst = UPLOADS_DIR / fname
    dst.write_bytes(src.read_bytes())
    return str(dst)


def run_question_with_timeout(runtime, question: str, thread_id: str, run_id: str, timeout_s: float):
    def _run():
        return runtime.run_question(
            question=question,
            thread_id=thread_id,
            run_id=run_id,
        )

    return run_with_timeout(_run, timeout_s=timeout_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="GAIA benchmark runner")
    parser.add_argument("--limit", type=int, default=None, help="分层抽样题数（冒烟）")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true", help="跳过已完成 task_id")
    parser.add_argument("--timeout-per-question", type=float, default=300.0)
    parser.add_argument("--delay-between", type=float, default=2.0, help="题间延迟（DDG 限流缓解）")
    args = parser.parse_args()

    ensure_project_root()
    load_env()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    questions = _load_questions(args.limit, args.seed)
    done = _load_done() if args.resume else set()
    todo = [q for q in questions if q["task_id"] not in done]
    print(f"[info] 共 {len(questions)} 题，待跑 {len(todo)} 题（已完成 {len(done)}）")

    if not todo:
        print("[info] 全部完成，无需运行")
        return

    runtime = build_full_runtime(
        expert_mode=True,
        provider="deepseek",
        logs_root=RUNS_DIR,
        skill_enabled=False,
    )
    print(f"[info] runtime 装配完成 thread={runtime.thread_id}")

    progress_path = RUNS_DIR / "progress.json"
    progress: dict = {}
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            progress = {}

    results_path = RUNS_DIR / "runs.jsonl"
    start_all = time.time()
    try:
        for idx, q in enumerate(todo, 1):
            task_id = q["task_id"]
            progress[task_id] = "running"
            progress_path.write_text(json.dumps(progress), encoding="utf-8")

            thread_id = f"gaia-{task_id}"
            run_id = f"gaia-{task_id}"
            print(f"\n[{idx}/{len(todo)}] task {task_id} (level {q.get('level')}, file={q.get('has_file')})")

            att = _copy_attachment(q)
            if q.get("has_file") and not att:
                print(f"  [warn] 附件复制失败，按无附件跑（可能影响答案）")

            question = q["question"]
            t0 = time.time()
            result, timed_out = run_question_with_timeout(
                runtime, question, thread_id, run_id, args.timeout_per_question
            )
            duration = time.time() - t0

            if timed_out:
                rec = {
                    "task_id": task_id,
                    "status": "timeout",
                    "att_ok": bool(att),
                    "duration_s": round(duration, 1),
                }
                progress[task_id] = "timeout"
                print(f"  [timeout] {duration:.0f}s 超时")
                # 超时线程还在旧 runtime 上跑，禁止复用 → 重建
                shutdown_runtime(runtime)
                runtime = build_full_runtime(
                    expert_mode=True,
                    provider="deepseek",
                    logs_root=RUNS_DIR,
                    skill_enabled=False,
                )
                print(f"  [info] runtime 已重建 thread={runtime.thread_id}")
            else:
                datum = collect_after_run(runtime, result, duration_s=duration)
                rec = {
                    "task_id": task_id,
                    "status": "ok",
                    "att_ok": bool(att),
                    "answer": datum.last_ai_content or datum.final_report,
                    "answer_source": "last_ai" if datum.last_ai_content else "final_report",
                    "duration_s": round(datum.duration_s, 1),
                    "usage": datum.usage,
                    "tool_calls_count": datum.tool_calls_count,
                    "web_search_count": datum.web_search_count,
                    "error": datum.error,
                }
                progress[task_id] = "done"
                print(f"  [done] {duration:.0f}s, tokens={rec['usage'] and rec['usage'].get('total_tokens')}")

            with results_path.open("a", encoding="utf-8") as fw:
                fw.write(json.dumps(rec, ensure_ascii=False) + "\n")
            progress_path.write_text(json.dumps(progress), encoding="utf-8")

            if idx < len(todo) and args.delay_between > 0:
                time.sleep(args.delay_between)
    finally:
        shutdown_runtime(runtime)

    total_s = time.time() - start_all
    print(f"\n[done] 共耗时 {total_s/60:.1f} 分钟，结果在 {results_path}")
    print(f"[hint] 下一步: python bench/a_gaia/judge.py && python bench/a_gaia/score_gaia.py")


if __name__ == "__main__":
    main()
