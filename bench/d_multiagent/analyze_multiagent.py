"""D.3 多 Agent 对照分析：单 vs 多 → report.json + markdown 表。

指标：
- 委派成功率/回退率：MultiAgentMetricsStore 4 计数器（invoked/completions/fallbacks）
- 单 vs 多对照：质量分（TaskQualityJudge overall）/ 耗时 / 成本差异 %
- 产物跨 Agent 连续性：report 引用 specialist 产物次数（均值）
- 深度控制：leaf 探针结果（leaf 无 delegate 工具 → 无递归）
"""

from __future__ import annotations

import json
import statistics
import sys

from bench.common.env import PROJECT_ROOT, ensure_project_root

RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "d_multiagent"


def _median(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 4) if values else None


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 4) if values else None


def main() -> None:
    ensure_project_root()
    runs_path = RUNS_DIR / "runs.jsonl"
    if not runs_path.exists():
        print("[error] 缺 runs.jsonl（先跑 run_multiagent_bench.py）", file=sys.stderr)
        sys.exit(1)

    runs = [json.loads(l) for l in runs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = [r for r in runs if r.get("status") == "ok"]

    by_cfg = {}
    for cfg in ("multi", "single"):
        group = [r for r in ok if r.get("config") == cfg]
        usage_tokens = [r["usage"].get("total_tokens", 0) for r in group if r.get("usage")]
        by_cfg[cfg] = {
            "n_runs": len(group),
            "n_timeout": sum(1 for r in runs if r.get("config") == cfg and r.get("status") == "timeout"),
            "judge_mean": _mean([r.get("judge_score") for r in group]),
            "judge_median": _median([r.get("judge_score") for r in group]),
            "duration_s_median": _median([r.get("duration_s") for r in group]),
            "tokens_sum": sum(usage_tokens),
            "tokens_median": _median(usage_tokens),
            "cost_usd_sum": round(sum(r.get("cost_usd", 0.0) for r in group), 4),
            "delegate_calls_sum": sum(r.get("delegate_calls", 0) for r in group),
            "continuity_mean": _mean([r.get("continuity", {}).get("total", 0) for r in group]),
            "by_cls": {
                cls: {
                    "n": len(g),
                    "judge_mean": _mean([r.get("judge_score") for r in g]),
                    "duration_s_median": _median([r.get("duration_s") for r in g]),
                    "delegate_calls": sum(r.get("delegate_calls", 0) for r in g),
                }
                for cls, g in [("parallel_research", [r for r in group if r["cls"] == "parallel_research"]),
                               ("isolated_compute", [r for r in group if r["cls"] == "isolated_compute"]),
                               ("mixed_toolchain", [r for r in group if r["cls"] == "mixed_toolchain"])]
            },
        }

    snap_multi = RUNS_DIR / "snapshot_multi.json"
    delegate_metrics = {}
    if snap_multi.exists():
        data = json.loads(snap_multi.read_text(encoding="utf-8"))
        # delegate_metrics 为 {表名: rows}；取含 specialist_name 列的表
        for _table, rows in data.get("delegate_metrics", {}).items():
            if rows and "specialist_name" in rows[0]:
                for row in rows:
                    delegate_metrics[row["specialist_name"]] = row
        leaf_probe = data.get("leaf_probe", {})

    # 单 vs 多差异
    def delta(metric: str) -> dict | None:
        va, vb = by_cfg["multi"].get(metric), by_cfg["single"].get(metric)
        if va is None or vb is None or vb == 0:
            return None
        return {"multi": va, "single": vb, "delta_pct": round((va - vb) / vb * 100, 2)}

    report = {
        "methodology": {
            "task_set": "3 类 × 4 题（parallel_research/isolated_compute/mixed_toolchain），单/多同题面",
            "judge": "TaskQualityJudge 4 维加权（deepseek LLM），与 C 同一评分器",
            "continuity": "最终报告引用 specialist 产物/路径次数的代理信号（非 ground truth）",
            "db": "POIROT_MULTIAGENT_DB_PATH 隔离",
        },
        "by_config": by_cfg,
        "delegate_metrics": delegate_metrics,
        "leaf_probe": leaf_probe,
        "comparison": {
            "judge_delta_pct": delta("judge_mean"),
            "latency_delta_pct": delta("duration_s_median"),
            "tokens_delta_pct": delta("tokens_median"),
            "cost_delta_pct": delta("cost_usd_sum"),
        },
    }

    # 委派率聚合
    invoked = sum(m.get("total_invoked", 0) for m in delegate_metrics.values())
    completions = sum(m.get("total_completions", 0) for m in delegate_metrics.values())
    fallbacks = sum(m.get("total_fallbacks", 0) for m in delegate_metrics.values())
    report["delegate_aggregate"] = {
        "invoked": invoked,
        "completions": completions,
        "fallbacks": fallbacks,
        "completion_rate": round(completions / invoked, 4) if invoked else None,
        "fallback_rate": round(fallbacks / invoked, 4) if invoked else None,
    }

    out = RUNS_DIR / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("| 配置 | n | 质量均值 | 耗时中位(s) | tokens中位 | 成本$ | delegate调用 | 连续性均值 |")
    print("|---|---|---|---|---|---|---|---|")
    for cfg in ("multi", "single"):
        a = by_cfg[cfg]
        print(f"| {cfg} | {a['n_runs']} | {a['judge_mean']} | {a['duration_s_median']} "
              f"| {a['tokens_median']} | {a['cost_usd_sum']} | {a['delegate_calls_sum']} | {a['continuity_mean']} |")
    print()
    print(f"委派聚合: invoked={invoked} completions={completions} fallbacks={fallbacks} "
          f"(completion_rate={report['delegate_aggregate']['completion_rate']})")
    print(f"leaf 探针: {json.dumps(leaf_probe, ensure_ascii=False)}")
    print(f"单 vs 多: {json.dumps(report['comparison'], ensure_ascii=False)}")
    print(f"\n[done] 报告 → {out}")


if __name__ == "__main__":
    main()
