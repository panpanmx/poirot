"""GAIA 评分汇总：从 verdicts.jsonl + runs.jsonl 产出 score_report.json。

指标：
- LLM-judged 总准确率 + Level 1/2/3 分层准确率（主报告口径）
- 规则严格匹配下界（可复现背书）
- 每题成本/总成本估算、耗时 avg/p50/p95、超时/错误数
- 工具调用分布
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import date
from pathlib import Path

from bench.common.env import PROJECT_ROOT, ensure_project_root, load_env, env_snapshot
from bench.common.tokens import estimate_cost_usd

RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "gaia"
DATA_DIR = PROJECT_ROOT / "bench" / "data" / "gaia"


def main() -> None:
    parser = argparse.ArgumentParser(description="GAIA 评分汇总")
    args = parser.parse_args()

    ensure_project_root()
    load_env()

    verdicts_path = RUNS_DIR / "verdicts.jsonl"
    runs_path = RUNS_DIR / "runs.jsonl"
    if not verdicts_path.exists() or not runs_path.exists():
        print("[error] 缺少 verdicts.jsonl 或 runs.jsonl（先跑 run_gaia.py + judge.py）", file=sys.stderr)
        sys.exit(1)

    verdicts = {}
    for line in verdicts_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = json.loads(line)
            verdicts[rec["task_id"]] = rec

    levels = {}
    meta_path = DATA_DIR / "gaia_validation.jsonl"
    if meta_path.exists():
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rec = json.loads(line)
                levels[rec["task_id"]] = rec.get("level")
    for tid, v in verdicts.items():
        v["level"] = levels.get(tid)

    runs = []
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            runs.append(json.loads(line))
    runs_by_id = {r["task_id"]: r for r in runs}

    # ── 准确率 ──────────────────────────────────────────
    judged = [v for v in verdicts.values() if v.get("majority") is not None]
    ruled = [v for v in verdicts.values() if v.get("rule") is not None]

    acc_llm = sum(1 for v in judged if v["majority"]) / len(judged) if judged else None
    acc_rule = sum(1 for v in ruled if v["rule"]) / len(ruled) if ruled else None

    acc_by_level: dict = {}
    for lv in sorted({v.get("level") for v in judged if v.get("level") is not None}):
        group = [v for v in judged if v.get("level") == lv]
        acc_by_level[str(lv)] = round(sum(1 for v in group if v["majority"]) / len(group), 4) if group else None

    # 附件题 / 无附件题分层（按 task_id 判定，避免 dict 值比较）
    file_ids = {r["task_id"] for r in runs if r.get("att_ok", False)}
    file_judged = [v for v in judged if v["task_id"] in file_ids]
    non_file_judged = [v for v in judged if v["task_id"] not in file_ids]

    # ── 成本 / 耗时 / 工具 ──────────────────────────────
    durations = [r.get("duration_s", 0.0) for r in runs if r.get("status") == "ok"]
    usage_list = [r.get("usage") for r in runs if r.get("usage")]
    total_tokens = sum(u.get("total_tokens", 0) or 0 for u in usage_list)
    prompt_tokens = sum(u.get("prompt_tokens", 0) or 0 for u in usage_list)
    completion_tokens = sum(u.get("completion_tokens", 0) or 0 for u in usage_list)
    usd_total = sum(estimate_cost_usd(u) or 0.0 for u in usage_list)
    usd_per_q = usd_total / len(usage_list) if usage_list else None

    timeouts = sum(1 for r in runs if r.get("status") == "timeout")
    errors = sum(1 for r in runs if r.get("status") == "error" or r.get("error"))

    tool_stats = {
        "web_search": sum(r.get("web_search_count", 0) for r in runs),
        "tool_calls": sum(r.get("tool_calls_count", 0) for r in runs),
    }

    # ── 双通道一致性 ─────────────────────────────────────
    both = [v for v in verdicts.values() if v.get("rule") is not None and v.get("majority") is not None]
    agree_rate = sum(1 for v in both if v["rule"] == v["majority"]) / len(both) if both else None
    n_contested = sum(1 for v in both if v["rule"] != v["majority"])

    report = {
        "meta": {
            "benchmark": "GAIA",
            "split": "validation",
            "date": date.today().isoformat(),
            "model": os.environ.get("SUB2API_MODEL") or os.environ.get("GEMINI_MODEL") or os.environ.get("DEEPSEEK_MODEL", "gemini-3.7-flash-high"),
            "provider": os.environ.get("POIROT_PROVIDER", "sub2api"),
            "judge_model": os.environ.get("SUB2API_MODEL") or os.environ.get("GEMINI_MODEL") or os.environ.get("DEEPSEEK_MODEL", "gemini-3.7-flash-high"),
            "judge_method": "LLM judge x2 majority + rule exact lower bound",
            "n_questions": len(verdicts),
            "env_snapshot": env_snapshot(),
        },
        "accuracy": {
            "llm_judge_overall": round(acc_llm, 4) if acc_llm is not None else None,
            "llm_judge_by_level": acc_by_level,
            "rule_exact_overall": round(acc_rule, 4) if acc_rule is not None else None,
            "file_questions": {
                "n": len(file_judged),
                "acc": round(sum(1 for v in file_judged if v["majority"]) / len(file_judged), 4) if file_judged else None,
            },
            "non_file_questions": {
                "n": len(non_file_judged),
                "acc": round(sum(1 for v in non_file_judged if v["majority"]) / len(non_file_judged), 4) if non_file_judged else None,
            },
        },
        "judge_agreement": {
            "rule_vs_llm_agree_rate": round(agree_rate, 4) if agree_rate is not None else None,
            "n_contested": n_contested,
            "review_path": str(RUNS_DIR / "review_top_conflicts.jsonl"),
        },
        "cost": {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_usd_est": round(usd_total, 2),
            "per_question_usd_avg": round(usd_per_q, 4) if usd_per_q is not None else None,
            "cost_note": "按 deepseek-chat 近似单价估算（input $0.27/M, output $1.10/M），非精确值",
        },
        "latency": {
            "avg_s": round(statistics.mean(durations), 1) if durations else None,
            "p50_s": round(statistics.median(durations), 1) if durations else None,
            "p95_s": round(sorted(durations)[int(len(durations) * 0.95) - 1], 1) if durations else None,
            "timeouts": timeouts,
            "errors": errors,
        },
        "tool_usage": tool_stats,
    }

    out = RUNS_DIR / "score_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[done] 报告已写 {out}")


if __name__ == "__main__":
    main()
