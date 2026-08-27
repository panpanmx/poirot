"""B.3 治理对照分析：按 cell 聚合 → report.json + markdown 表 + 水位 CSV。

量化指标（对应简历口径）：
- P4 实测压缩率（before/after token 实测比值，区别于 summarize.md 报告值）
- P1 外化次数 / 累计 tokens_saved（含 interval suppression 场景）
- P5 熔断次数（context_budget_stop）
- 无损性：开/关治理子任务完成率对比（TASK 标记自动判定）
- 长会话存活率：完成(status=ok) / 超时(timeout) 之比
- 水位曲线：compaction 事件 fraction 序列 → CSV
- 治理开销：开/关的每轮 token 与耗时差（同任务同窗口）
"""

from __future__ import annotations

import csv
import json
import statistics
import sys

from bench.common.env import PROJECT_ROOT, ensure_project_root

RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "gov"
CELLS = ["gov_on_8k", "gov_off_8k", "gov_on_default", "gov_off_default"]


def _median(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 2) if values else None


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 2) if values else None


def _agg(cell_runs: list[dict]) -> dict:
    ok = [r for r in cell_runs if r.get("status") == "ok"]
    n = len(cell_runs)
    if not ok:
        return {"n_runs": n, "survival_rate": 0.0, "status": "all_failed_or_timeout"}

    usage_tokens = [r["usage"].get("total_tokens", 0) for r in ok if r.get("usage")]
    ratios = [r["measured_ratio"]["ratio"] for r in ok if r.get("measured_ratio")]
    reported = [r["reported_ratio"] for r in ok if r.get("reported_ratio") is not None]
    done_rates = [r["completion"]["done_rate"] for r in ok if r.get("completion", {}).get("done_rate") is not None]
    combine_rates = [r["completion"]["combine_rate"] for r in ok if r.get("completion", {}).get("combine_rate") is not None]
    p4_events = [r.get("p4_events", 0) for r in ok]
    p1_events = [r.get("p1_events", 0) for r in ok]
    p5_events = [r.get("p5_events", 0) for r in ok]

    return {
        "n_runs": n,
        "survival_rate": round(len(ok) / n, 4) if n else None,
        "duration_s_median": _median([r["duration_s"] for r in ok]),
        "total_tokens_median": _median(usage_tokens),
        "total_tokens_sum": sum(usage_tokens),
        "cost_usd_sum": round(sum(r.get("cost_usd", 0.0) for r in ok), 4),
        "completion_rate_median": _median(done_rates),
        "combine_rate_median": _median(combine_rates),
        "externalized_count_sum": sum(r.get("externalized_count", 0) for r in ok),
        "externalized_tokens_saved_sum": sum(r.get("externalized_tokens_saved", 0) for r in ok),
        "budget_stop_count_sum": sum(r.get("budget_stop_count", 0) for r in ok),
        "p4_events_sum": sum(p4_events),
        "p1_events_sum": sum(p1_events),
        "p5_events_sum": sum(p5_events),
        "measured_ratio_mean": _mean(ratios),
        "measured_ratio_events": len(ratios),
        "reported_ratio_mean": _mean(reported),
        "final_fraction_mean": _mean([r.get("final_fraction") for r in ok]),
    }


def _delta(a: dict, b: dict, key: str, higher_is_better: bool = True) -> dict | None:
    """a vs b 差异：相对百分比 + 绝对差（b 为对照基准）。"""
    va, vb = a.get(key), b.get(key)
    if va is None or vb is None or vb == 0:
        return None
    return {"a": va, "b": vb, "delta_pct": round((va - vb) / vb * 100, 2)}


def main() -> None:
    ensure_project_root()
    runs_path = RUNS_DIR / "runs.jsonl"
    if not runs_path.exists():
        print("[error] 缺少 runs.jsonl（先跑 run_gov_experiment.py）", file=sys.stderr)
        sys.exit(1)

    runs = [json.loads(line) for line in runs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_cell = {c: [r for r in runs if r.get("cell") == c] for c in CELLS}

    report: dict = {"cells": {}, "comparisons": {}}
    for c in CELLS:
        agg = _agg(by_cell[c])
        report["cells"][c] = agg
        # 水位 CSV（每 run 一个文件）
        for r in by_cell[c]:
            if r.get("water"):
                csv_path = RUNS_DIR / f"water_{r['run_id']}.csv"
                with csv_path.open("w", newline="", encoding="utf-8") as fw:
                    w = csv.writer(fw)
                    w.writerow(["event", "stage", "fraction"])
                    for e in r["water"]:
                        w.writerow([e.get("event"), e.get("stage"), e.get("fraction")])

    # 对照（同窗口组内开 vs 关）
    for on_key, off_key in (("gov_on_8k", "gov_off_8k"), ("gov_on_default", "gov_off_default")):
        on_, off = report["cells"][on_key], report["cells"][off_key]
        report["comparisons"][on_key] = {
            "tokens_saving_pct": _delta(on_, off, "total_tokens_sum"),
            "completion_delta": _delta(on_, off, "completion_rate_median"),
            "combine_delta": _delta(on_, off, "combine_rate_median"),
            "latency_delta_pct": _delta(on_, off, "duration_s_median", higher_is_better=False),
            "cost_delta_pct": _delta(on_, off, "cost_usd_sum"),
        }

    out = RUNS_DIR / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown 表
    print("| cell | 存活率 | 完成率 | combine | 耗时s | tokens | 成本$ | P1外化 | saved | P4 | P5 | 实测压缩率 | 报告率 | 水位终值 |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for c in CELLS:
        a = report["cells"][c]
        m = a.get("measured_ratio_mean")
        print(f"| {c} | {a.get('survival_rate', '-')} | {a.get('completion_rate_median', '-')} "
              f"| {a.get('combine_rate_median', '-')} | {a.get('duration_s_median', '-')} "
              f"| {a.get('total_tokens_median', '-')} | {a.get('cost_usd_sum', '-')} "
              f"| {a.get('p1_events_sum', 0)} | {a.get('externalized_tokens_saved_sum', 0)} "
              f"| {a.get('p4_events_sum', 0)} | {a.get('p5_events_sum', 0)} "
              f"| {m if m is not None else '-'} | {a.get('reported_ratio_mean', '-')} "
              f"| {a.get('final_fraction_mean', '-')} |")
    print()
    for k, v in report["comparisons"].items():
        print(f"[{k}] vs 关治理基线：{json.dumps(v, ensure_ascii=False)}")
    print(f"\n[done] 报告 → {out}")


if __name__ == "__main__":
    main()
