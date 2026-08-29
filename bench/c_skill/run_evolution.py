"""C.3 Skill 进化 runner：run_cycle（阈值触发）+ 手动 FIX 兜底。

- run_cycle：EvolutionManager 扫 MetricMonitor 等 trigger（effective_rate<阈值 / fallback_rate>0.4
  命中才进 focus→mutate→eval→gate 闭环），一次调用返回全部 EvolutionRecord。
- --target NAME：run_cycle 无产出时对指定 skill 手动 evolve_skill（FIX），
  保证第一批真实进化数字（补跑现状：skills.db 从未有记录）。

用法：
    python bench/c_skill/run_evolution.py [--target systematic-debugging] [--smoke]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys

from bench.common.env import PROJECT_ROOT, ensure_project_root, load_env
from bench.common.runtime import build_full_runtime, shutdown_runtime

DATA_DIR = PROJECT_ROOT / "bench" / "data" / "c_skill"
SKILL_DB = DATA_DIR / "skills.db"
USER_SKILL_DIR = DATA_DIR / "user_skills"
RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "c_skill"


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill 进化 runner")
    parser.add_argument("--target", default=None, help="run_cycle 无产出时手动 FIX 的 skill 名")
    parser.add_argument("--smoke", action="store_true", help="只跑 run_cycle，不触发手动 FIX")
    args = parser.parse_args()

    ensure_project_root()
    load_env()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    USER_SKILL_DIR.mkdir(parents=True, exist_ok=True)

    runtime = build_full_runtime(
        expert_mode=True,
        provider=os.environ.get("POIROT_PROVIDER", "sub2api"),
        logs_root=RUNS_DIR,
        skill_enabled=True,
        skill_db_path=SKILL_DB,
        skill_dirs=USER_SKILL_DIR,
    )
    mgr = runtime.skill_manager
    evo = mgr.get_evolution_manager()
    if evo is None:
        print("[error] EvolutionManager 未装配（需 POIROT_SKILL_EVOLVE_ENABLED=true）", file=sys.stderr)
        sys.exit(1)

    records: list[dict] = []
    try:
        cycle = evo.run_cycle()
        for rec in cycle:
            records.append(dataclasses.asdict(rec))
        print(f"[info] run_cycle 产出 {len(cycle)} 条 EvolutionRecord")
        for r in records:
            print(f"  - {r['skill_name']} {r['evolution_type']} gate={r['gate_decision']} "
                  f"score={r['eval_score']} created={r['created_version_id']}")

        if not records and args.target:
            print(f"[info] 无阈值触发，手动 FIX: {args.target}")
            rec = evo.evolve_skill(args.target)
            records.append(dataclasses.asdict(rec))
            print(f"  - {rec.skill_name} {rec.evolution_type} gate={rec.gate_decision} "
                  f"score={rec.eval_score} created={rec.created_version_id}")

        if not records and not args.smoke:
            print("[warn] 无进化记录——可能 metrics 样本不足或阈值未命中；"
                  "可先跑 run_skill_bench.py 积累样本，或用 --target 手动 FIX")
    finally:
        shutdown_runtime(runtime)

    evo_path = RUNS_DIR / "evolutions.jsonl"
    with evo_path.open("a", encoding="utf-8") as fw:
        for r in records:
            fw.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[done] {len(records)} 条进化记录 → {evo_path}")
    print("[hint] 下一步: python bench/c_skill/run_skill_bench.py --phase post，再 analyze_skill.py")


if __name__ == "__main__":
    main()
