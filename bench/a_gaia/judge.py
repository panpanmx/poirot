"""GAIA 双通道评分：规则严格匹配（保守下界）+ deepseek LLM judge（每题 2 次取 majority）。

用法：
    python bench/a_gaia/judge.py [--limit N] [--no-llm] [--review-top 20]

输入：bench/data/runs/gaia/runs.jsonl + bench/data/gaia/metadata_full.jsonl（含 final_answer）
输出：bench/data/runs/gaia/verdicts.jsonl + review_top_conflicts.jsonl（争议题人工复核）

设计：LLM judge 与官方 evaluator 同思路（question + reference answer + model answer →
correct/reason JSON），deepseek 替代 OpenAI；temperature=0 + 双判 majority 抑制偏差；
规则通道（归一化精确匹配/数字容差/日期/yes-no）作为零成本保守下界并交叉验证。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

from bench.common.env import PROJECT_ROOT, ensure_project_root, load_env

DATA_DIR = PROJECT_ROOT / "bench" / "data" / "gaia"
RUNS_DIR = PROJECT_ROOT / "bench" / "data" / "runs" / "gaia"

JUDGE_PROMPT = """你是严格客观的答案判分器。判断"模型答案"与"参考答案"是否语义等价（表达方式可不同，但信息必须一致；参考答案不可得时判断是否合理回答该问题）。

问题: {question}

参考答案: {reference}

模型答案: {answer}

只输出 JSON（不要其他文字）：
{{"correct": true 或 false, "reason": "一句话理由"}}
"""


# ── 通道 1：规则严格匹配 ────────────────────────────────

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    text = re.sub(r"[^\w\s\-.,%]+", "", text)  # 去标点
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_number(text: str) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", str(text))
    return float(m.group()) if m else None


def rule_match(reference: str, answer: str) -> bool:
    """保守下界：归一化精确匹配 / 数字相对容差 / 日期多格式 / yes-no 变体。"""
    if not answer or not reference:
        return False
    norm_ref, norm_ans = _normalize(reference), _normalize(answer)
    if not norm_ref or not norm_ans:
        return False
    if norm_ref == norm_ans:
        return True
    # 数字容差
    num_ref, num_ans = _extract_number(reference), _extract_number(answer)
    if num_ref is not None and num_ans is not None and num_ref != 0:
        if abs(num_ref - num_ans) / abs(num_ref) <= 1e-3:
            return True
    # yes/no 变体
    yn_ref = norm_ref in ("yes", "correct", "true", "no", "incorrect", "false")
    yn_ans = norm_ans in ("yes", "correct", "true", "no", "incorrect", "false")
    if yn_ref and yn_ans and norm_ref.startswith(norm_ans[:2]) and norm_ans.startswith(norm_ref[:2]):
        return True
    return False


# ── 通道 2：LLM judge ───────────────────────────────────

def _build_judge():
    from langchain_deepseek import ChatDeepSeek

    key = __import__("os").environ.get("DEEPSEEK_API_KEY", "")
    model = __import__("os").environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    return ChatDeepSeek(model=model, api_key=key, temperature=0)


def llm_judge(judge, question: str, reference: str, answer: str) -> bool | None:
    if not answer:
        return None
    prompt = JUDGE_PROMPT.format(question=question, reference=reference, answer=answer[:4000])
    try:
        resp = judge.invoke(prompt)
        text = resp.content if hasattr(resp, "content") else str(resp)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        return bool(data.get("correct"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] LLM judge 失败: {exc}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="GAIA 双通道评分")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-llm", action="store_true", help="只跑规则通道（零成本）")
    parser.add_argument("--review-top", type=int, default=20, help="导出前 N 争议题")
    args = parser.parse_args()

    ensure_project_root()
    load_env()

    runs_path = RUNS_DIR / "runs.jsonl"
    meta_path = DATA_DIR / "metadata_full.jsonl"
    if not runs_path.exists() or not meta_path.exists():
        print("[error] 缺少 runs.jsonl 或 metadata_full.jsonl", file=sys.stderr)
        sys.exit(1)

    answers = {}
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = json.loads(line)
            answers[rec["task_id"]] = rec

    references = {}
    for line in meta_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = json.loads(line)
            references[rec["task_id"]] = {
                "final_answer": rec.get("final_answer", ""),
                "question": rec.get("question", ""),
            }

    if args.limit:
        answers = dict(list(answers.items())[: args.limit])

    judge = None if args.no_llm else _build_judge()
    verdicts = []
    conflicts = []

    for task_id, rec in answers.items():
        if rec.get("status") != "ok":
            verdicts.append({"task_id": task_id, "status": rec.get("status")})
            continue
        meta = references.get(task_id, {})
        reference = meta.get("final_answer", "")
        question = meta.get("question", "")
        answer = rec.get("answer", "")
        rv = rule_match(reference, answer)
        l1 = llm_judge(judge, question, reference, answer) if judge and answer else None
        l2 = llm_judge(judge, question, reference, answer) if judge and answer else None
        votes = [v for v in (l1, l2) if v is not None]
        majority = None
        if votes:
            # 严格多数：2 票取 2（1:1 不算对），1 票取 1（单判退化为该票）
            majority = sum(votes) > len(votes) // 2
        verdicts.append({
            "task_id": task_id,
            "level": None,  # score 阶段补
            "rule": rv,
            "llm1": l1,
            "llm2": l2,
            "majority": majority,
            "reference": reference,
            "answer": (answer or "")[:500],
        })
        if rv is not None and majority is not None and rv != majority:
            conflicts.append({"task_id": task_id, "rule": rv, "llm": majority})

    with (RUNS_DIR / "verdicts.jsonl").open("w", encoding="utf-8") as fw:
        for v in verdicts:
            fw.write(json.dumps(v, ensure_ascii=False) + "\n")

    conflicts_path = RUNS_DIR / "review_top_conflicts.jsonl"
    with conflicts_path.open("w", encoding="utf-8") as fw:
        for c in conflicts[: args.review_top]:
            fw.write(json.dumps(c, ensure_ascii=False) + "\n")

    n_llm = sum(1 for v in verdicts if v.get("majority") is not None)
    agree = sum(1 for v in verdicts if v.get("rule") is not None and v.get("majority") is not None and v["rule"] == v["majority"])
    print(f"[done] verdicts={len(verdicts)}, rule判={sum(1 for v in verdicts if 'rule' in v)}, "
          f"LLM判={n_llm}, rule/LLM 一致率={agree}/{max(n_llm,1)} "
          f"(={agree/max(n_llm,1):.0%} 若全判), 争议题 {len(conflicts)} 条 → {conflicts_path}")


if __name__ == "__main__":
    main()
