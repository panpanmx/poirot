"""C.4 Skill 评测分析：baseline vs post → report.json + markdown 表。

量化口径：
- L1 4 率（selections/applied/completions/fallbacks → applied/completion/effective/fallback rate）
  ——snapshot 差值（同 DB 累积计数，post − baseline = 进化后增量）
- L3 task judge 4 维加权分（0.50/0.35/0.05/0.10）——按 task_id 对齐前后
- 进化记录（evolutions.jsonl）：次数、类型、gate 分布、created_version
- 工具覆盖口径标注（tool-covered / guidance / tool-uncovered）
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from bench.common.env import PROJECT_ROOT, ensure_project_root

RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "c_skill"


def _load_snapshot(phase: str) -> dict:
    p = RUNS_DIR / f"snapshot_{phase}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _load_evolutions() -> list[dict]:
    p = RUNS_DIR / "evolutions.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _metric_delta(base: dict | None, post: dict | None, key: str):
    if not base or not post:
        return None
    return post.get(key) - base.get(key)


def main() -> None:
    ensure_project_root()
    base = _load_snapshot("baseline")
    post = _load_snapshot("post")
    evolutions = _load_evolutions()

    if not base:
        print("[error] 缺 snapshot_baseline.json（先跑 run_skill_bench.py --phase baseline）",
              file=sys.stderr)
        sys.exit(1)

    skills = {}
    for name in sorted(set(base.get("skills", {})) | set(post.get("skills", {}))):
        b = base.get("skills", {}).get(name)
        p = post.get("skills", {}).get(name)
        cls = (post.get("tool_coverage") or base.get("tool_coverage") or {}).get(name, {}).get("class")
        skills[name] = {
            "class": cls,
            "baseline": b,
            "post": p,
            "delta_selections": _metric_delta(b, p, "selections"),
            "delta_applied": _metric_delta(b, p, "applied"),
            "delta_completions": _metric_delta(b, p, "completions"),
            "delta_effective_rate_pp": (
                round((p["effective_rate"] - b["effective_rate"]) * 100, 2)
                if b and p else None),
            "delta_fallback_rate_pp": (
                round((p["fallback_rate"] - b["fallback_rate"]) * 100, 2)
                if b and p else None),
        }

    # task judge 对齐（按 task_id）
    scores_by_task = {}
    for phase, snap in (("baseline", base), ("post", post)):
        for s in snap.get("task_scores", []):
            scores_by_task.setdefault(s["task_id"], {})[phase] = s

    # 口径分组聚合
    def agg_rates(phase: str) -> dict:
        total = {"selections": 0, "applied": 0, "completions": 0, "fallbacks": 0}
        covered = [name for name, d in skills.items()
                   if d.get("class") == "tool-covered" and (base.get("skills", {}).get(name) or post.get("skills", {}).get(name))]
        for name in covered:
            m = base.get("skills", {}).get(name) or post.get("skills", {}).get(name)
            for k in total:
                total[k] += m.get(k, 0)
        s = total["selections"]
        a = total["applied"]
        c = total["completions"]
        return {
            "n_skills": len(covered),
            "total_selections": s,
            "total_applied": a,
            "total_completions": c,
            "total_fallbacks": total["fallbacks"],
            "applied_rate": round(a / s, 4) if s else None,
            "completion_rate": round(c / a, 4) if a else None,
            "effective_rate": round(c / s, 4) if s else None,
            "fallback_rate": round(total["fallbacks"] / s, 4) if s else None,
        }

    report = {
        "methodology": {
            "scope": "builtin core skills（启动自动激活 12 个）；其余 25 个按需激活不纳入",
            "classes": {
                "tool-covered": "allowed_tools 在 bench runtime 可用 → applied 可判定",
                "guidance": "无 allowed_tools → 只打 selections 不归因完成",
                "tool-uncovered": "有 allowed_tools 但 runtime 无对应工具 → applied=False 诚实归因",
            },
            "counters": "selections/applied/completions/fallbacks（SkillMetricsMiddleware 自动打点）",
            "judge": "TaskQualityJudge 4 维加权 0.50/0.35/0.05/0.10（deepseek LLM）",
        },
        "cohort": {
            "baseline": agg_rates("baseline"),
            "post": agg_rates("post"),
        },
        "per_skill": skills,
        "task_judge": {
            "tasks": {tid: v for tid, v in scores_by_task.items()},
            "baseline_mean": (round(statistics.mean([s["overall_score"] for s in base.get("task_scores", [])]), 4)
                              if base.get("task_scores") else None),
            "post_mean": (round(statistics.mean([s["overall_score"] for s in post.get("task_scores", [])]), 4)
                          if post.get("task_scores") else None),
        },
        "evolutions": {
            "n": len(evolutions),
            "records": evolutions,
            "by_type": {},
            "by_gate": {},
        },
    }
    for rec in evolutions:
        t = rec.get("evolution_type", "?")
        report["evolutions"]["by_type"][t] = report["evolutions"]["by_type"].get(t, 0) + 1
        g = rec.get("gate_decision", "?")
        report["evolutions"]["by_gate"][g] = report["evolutions"]["by_gate"].get(g, 0) + 1

    out = RUNS_DIR / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown 表
    print("| skill | class | base sel/app/comp/fb | post sel/app/comp/fb | Δeffective(pp) | Δfallback(pp) |")
    print("|---|---|---|---|---|---|")
    for name, d in skills.items():
        b, p = d["baseline"], d["post"]
        bf = f"{b['selections']}/{b['applied']}/{b['completions']}/{b['fallbacks']}" if b else "-"
        pf = f"{p['selections']}/{p['applied']}/{p['completions']}/{p['fallbacks']}" if p else "-"
        print(f"| {name} | {d['class']} | {bf} | {pf} | {d['delta_effective_rate_pp']} | {d['delta_fallback_rate_pp']} |")
    print()
    print(f"tool-covered 组: baseline effective={report['cohort']['baseline'].get('effective_rate')} "
          f"→ post={report['cohort']['post'].get('effective_rate')}")
    print(f"task judge: baseline mean={report['task_judge'].get('baseline_mean')} "
          f"→ post mean={report['task_judge'].get('post_mean')}")
    print(f"evolutions: n={len(evolutions)} {report['evolutions']['by_type']} "
          f"gate={report['evolutions']['by_gate']}")
    print(f"\n[done] 报告 → {out}")


if __name__ == "__main__":
    main()
