"""B.1 合成治理压测长任务（确定性、可自动校验）。

子任务 4 类（无外部网络依赖，纯推理 + 沙箱写文件）：
- calc:     数据表计算（总和/平均/最大项）——代码可验证数值答案
- extract:  文本块实体提取（客户编号）——代码可验证字符串答案
- write:    报告写入沙箱文件（write_file）——完成即输出 TASK:n DONE 行
- combine:  引用前置子任务数据块中的数值事实 + 偏移——测压缩后跨摘要记忆无损性

每个子任务携带 ≥1 个数值事实（label→value），combine 以 (任务号, label, delta) 引用，
期望值 = value + delta。check_completion 只依赖最终文本：
1. `TASK:<n> DONE` 标记覆盖度（子任务完成率）
2. combine 期望数值是否出现在最终输出（压缩无损探针）
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from bench.common.env import PROJECT_ROOT, ensure_project_root

DATA_DIR = PROJECT_ROOT / "bench" / "data" / "gov"
TASKS_PATH = DATA_DIR / "tasks.json"

TOOLS = ["螺丝刀", "扳手", "电缆剪", "热熔胶枪", "手电钻", "卷尺", "水平仪", "冲击钻"]
CUSTOMERS = ["CUST-ALP", "CUST-BRD", "CUST-CKL", "CUST-DMN", "CUST-ERT", "CUST-FQZ"]
DEPT = ["销售部", "工程部", "采购部", "质检部"]


def _rng_for(index: int, seed: int) -> random.Random:
    return random.Random(seed * 1000 + index)


def _calc_task(index: int, seed: int) -> dict:
    """数据表计算。facts = {物品: 件数}。"""
    rng = _rng_for(index, seed)
    items = rng.sample(TOOLS, 6)
    values = [rng.randint(30, 990) for _ in items]
    table = "\n".join(f"- {name}: {v} 件" for name, v in zip(items, values))
    op, answer = random.Random(seed * 7 + index).choice([
        ("总件数", sum(values)),
        ("平均件数（保留一位小数）", round(sum(values) / len(values), 1)),
        ("件数最多的物品名", items[values.index(max(values))]),
        ("总件数与最少件数的差值", max(values) - min(values)),
    ])
    body = (
        f"下面是 2026 年 Q2 部分工具的月末库存表：\n{table}\n"
        f"请计算：这 6 种工具的{op}。"
    )
    return {
        "id": index,
        "type": "calc",
        "title": f"计算库存{op}",
        "body": body,
        "answer": str(answer),
        "facts": dict(zip(items, values)),
    }


def _extract_task(index: int, seed: int) -> dict:
    """文本块实体提取。facts = {客户编号: 部门}。"""
    rng = _rng_for(index, seed)
    codes = rng.sample(CUSTOMERS, 4)
    rows = []
    facts: dict = {}
    for code in codes:
        dep = rng.choice(DEPT)
        income = rng.randint(40, 900)  # 数值事实（combine 引用）
        facts[code] = dep
        facts[f"{code}收入"] = income
        rows.append(f"客户 {code}（部门：{dep}，上季度收入 {income} 万元）")
    block = "\n".join(rows)
    body = (
        f"以下是客户登记表摘录：\n{block}\n"
        "请列出所有客户编号，按字母序排列，用逗号分隔。"
    )
    return {
        "id": index,
        "type": "extract",
        "title": "提取客户编号",
        "body": body,
        "answer": ", ".join(sorted(codes)),
        "facts": facts,
    }


def _write_task(index: int, seed: int) -> dict:
    """写报告到沙箱。facts = {文件行数: n}。"""
    rng = _rng_for(index, seed)
    lines = [f"报告 #{index}：{rng.choice(['巡检记录', '月度小结', '安全审查', '用量统计'])}"]
    for _ in range(2):
        lines.append(rng.choice([
            f"- 关键指标：{rng.randint(10, 999)}",
            f"- 负责人：{rng.choice(['张', '李', '王', '赵'])}{rng.choice(['工', '工'])}",
            f"- 结论：{rng.choice(['达标', '需跟进', '已复核', '待审批'])}",
        ]))
    content = "\n".join(lines)
    body = (
        f"请把以下内容用文件工具保存为沙箱文件 task{index}.md（写入后不需要读出内容）：\n"
        f"```\n{content}\n```"
    )
    return {
        "id": index,
        "type": "write",
        "title": f"写文件 task{index}.md",
        "body": body,
        "answer": f"task{index}.md",
        "facts": {"文件行数": len(lines)},
    }


def _combine_task(index: int, seed: int, ref: dict) -> dict:
    """引用前置子任务 ref 的一个数值事实 + 偏移。"""
    rng = _rng_for(index, seed)
    label, value = rng.choice(list(ref["facts"].items()))
    delta = rng.randint(11, 59)
    body = (
        f"子任务 {ref['id']} 的数据块中提到「{label}」的数值（件数/万元/行数等）。"
        f"取该数值加上 {delta}，结果是多少？"
    )
    return {
        "id": index,
        "type": "combine",
        "title": f"引用子任务 {ref['id']} 数据",
        "body": body,
        "answer": str(value + delta),
        "facts": {f"{label}+{delta}": value + delta},
        "ref": ref["id"],
        "ref_label": label,
    }


def build_task_set(n_full: int, n_short: int, seed: int = 42) -> dict:
    """生成 full/short 两套任务（确定性）。combine 间隔固定（压缩间参照）。"""
    return {
        "n_full": n_full,
        "n_short": n_short,
        "seed": seed,
        "full": {"text": _assemble(_make_tasks(n_full, seed)), "tasks": _make_tasks(n_full, seed)},
        "short": {"text": _assemble(_make_tasks(n_short, seed + 1)), "tasks": _make_tasks(n_short, seed + 1)},
    }


def _make_tasks(n: int, seed: int) -> list[dict]:
    tasks: list[dict] = []
    for i in range(1, n + 1):
        kind = (i - 1) % 4
        if kind == 0:
            tasks.append(_calc_task(i, seed))
        elif kind == 1:
            tasks.append(_extract_task(i, seed))
        elif kind == 2:
            tasks.append(_write_task(i, seed))
        else:
            # combine 引用上一个非 combine 任务（≈5 步前的数据块，跨压缩窗口）
            ref = next(t for t in reversed(tasks) if t["type"] != "combine")
            tasks.append(_combine_task(i, seed, ref))
    return tasks


def _assemble(tasks: list[dict]) -> str:
    lines = [
        "你是一个自动化研究助手。以下有 {} 个子任务，必须按顺序完成，不得跳过。".format(len(tasks)),
        "每个子任务完成后，单独输出一行，格式必须为：TASK:<编号> DONE: <一句话说明>（编号从 1 开始递增，不要跳号）。",
        "全部完成后，写一份最终总结报告，逐条汇总每个 TASK 的结果，并包含 combine 类任务的答案数值。",
        "注意：所有数值必须精确，不要四舍五入到整数以外的精度。",
        "",
    ]
    for t in tasks:
        lines.append(f"### 子任务 {t['id']}（TASK:{t['id']}）")
        lines.append(t["body"])
        lines.append("")
    lines.append("请开始。")
    return "\n".join(lines)


# ── 完成度校验 ─────────────────────────────────────────────

_TASK_DONE_RE = re.compile(r"TASK:\s*(\d+)\s*DONE", re.IGNORECASE)


def _all_numbers(text: str) -> list[float]:
    return [float(m) for m in re.findall(r"-?\d+(?:\.\d+)?", text)]


def check_completion(text: str, tasks: list[dict]) -> dict:
    """从最终输出解析：子任务完成率 + combine 期望值命中率。"""
    text = text or ""
    done_ids = {int(m) for m in _TASK_DONE_RE.findall(text)}
    done_ids = {i for i in done_ids if 1 <= i <= len(tasks)}
    numbers = _all_numbers(text)

    combine_ok = 0
    combine_total = 0
    for t in tasks:
        if t["type"] != "combine":
            continue
        combine_total += 1
        expect = float(t["answer"])
        if any(abs(n - expect) <= max(1e-3 * abs(expect), 1e-9) for n in numbers):
            combine_ok += 1

    return {
        "done_count": len(done_ids),
        "done_total": len(tasks),
        "done_rate": round(len(done_ids) / len(tasks), 4) if tasks else None,
        "done_ids": sorted(done_ids),
        "combine_correct": combine_ok,
        "combine_total": combine_total,
        "combine_rate": round(combine_ok / combine_total, 4) if combine_total else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成治理压测长任务（tasks.json）")
    parser.add_argument("--full", type=int, default=28, help="full 任务子任务数（缩窗组）")
    parser.add_argument("--short", type=int, default=6, help="short 任务子任务数（默认窗口组）")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    ensure_project_root()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = build_task_set(args.full, args.short, args.seed)
    TASKS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    f = data["full"]
    print(f"[done] tasks.json: full={args.full} 题（文本约 {len(f['text'])} 字符），"
          f"short={args.short} 题 → {TASKS_PATH}")
    print(f"[hint] 下一步: python bench/b_governance/run_gov_experiment.py")


if __name__ == "__main__":
    main()
