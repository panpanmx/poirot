"""ProgrammaticEvalBridge — 零 LLM eval floor（D8 拒绝裸跑底线）。

SkillEvo 7 mode（借鉴 AutoSkill/SkillEvo evals.py）确定性检查 candidate SKILL.md：
- nonempty: body 非空
- json_parseable: frontmatter YAML 可解析
- must_cite: 含引用/来源标记（@/http/来源）
- paragraph_limit: body 段落不超限（防冗长）
- lead_with_conclusion: 首段含结论性词（结论/总结/核心）
- markdown_table: 含 markdown 表格结构（如适用）
- no_unfounded_claims: 无绝对化无据声明（绝对/一定/必然 + 无来源）

SkillOpt semantic_density：统计 MUST/ALWAYS/NEVER/SHOULD 等指令性词密度（过高=冗长，过低=缺指令）。

返 EvalResult（score [0,1] + hard_failures + evidence）。零 LLM 调用。
L3 建好后降为 EvalAdapter registry 一员，EvalBridge Protocol 不变零侵入替换。
"""
from __future__ import annotations

import re
from typing import Any

from poirot.backend.agents.skill.evolution.types import (
    EvalContext,
    EvalEvidence,
    EvalResult,
)

# hard failure modes（关键失败，触发即 reject 倾向）
_HARD_MODES = ("nonempty", "json_parseable")

# 指令性词（semantic_density，借鉴 SkillOpt）
_DIRECTIVE_WORDS = ("MUST", "ALWAYS", "NEVER", "SHOULD", "MUST NOT", "REQUIRED", "FORBIDDEN")
_UNFOUNDED_WORDS = ("绝对", "一定", "必然", "毫无疑问", "absolutely", "definitely", "certainly")
_CONCLUSION_WORDS = ("结论", "总结", "核心", "要点", "conclusion", "summary", "key")
_CITE_PATTERN = re.compile(r"(https?://|@[\w-]+|来源|引用|source|cite)", re.IGNORECASE)
_TABLE_PATTERN = re.compile(r"^\|.+\|$", re.MULTILINE)
_YAML_FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)

_PARAGRAPH_LIMIT = 20  # 段落数上限
_SEMANTIC_DENSITY_MIN = 0.005  # 指令性词最低密度（过低=缺指令）
_SEMANTIC_DENSITY_MAX = 0.15   # 最高密度（过高=冗长）


class ProgrammaticEvalBridge:
    """零 LLM eval floor。对 candidate 跑 7 mode + semantic_density。"""

    def evaluate(self, ctx: EvalContext) -> EvalResult:
        """跑确定性检查，返 EvalResult。

        score = 通过 mode 数 / 总 mode 数（含 semantic_density）。
        hard_failures = 触发 hard mode（nonempty/json_parseable）失败的 rule 名。
        """
        candidate_content = self._read_content(ctx.candidate)
        baseline_content = self._read_content(ctx.baseline) if ctx.baseline else ""

        evidence: list[EvalEvidence] = []
        hard_failures: list[str] = []
        passed = 0
        total = 0

        # 7 mode
        for mode_name, check_fn in (
            ("nonempty", self._check_nonempty),
            ("json_parseable", self._check_json_parseable),
            ("must_cite", self._check_must_cite),
            ("paragraph_limit", self._check_paragraph_limit),
            ("lead_with_conclusion", self._check_lead_with_conclusion),
            ("markdown_table", self._check_markdown_table),
            ("no_unfounded_claims", self._check_no_unfounded_claims),
        ):
            total += 1
            baseline_pass = check_fn(baseline_content) if baseline_content else True
            candidate_pass = check_fn(candidate_content)
            if candidate_pass:
                passed += 1
            if mode_name in _HARD_MODES and not candidate_pass:
                hard_failures.append(mode_name)
            evidence.append(EvalEvidence(
                kind="programmatic_rule",
                rule_name=mode_name,
                baseline_pass=baseline_pass,
                candidate_pass=candidate_pass,
            ))

        # semantic_density（连续值，转 pass/fail：在 [min,max] 内 pass）
        total += 1
        density = self._semantic_density(candidate_content)
        density_pass = _SEMANTIC_DENSITY_MIN <= density <= _SEMANTIC_DENSITY_MAX if candidate_content else False
        if density_pass:
            passed += 1
        baseline_density = self._semantic_density(baseline_content) if baseline_content else 0.0
        evidence.append(EvalEvidence(
            kind="programmatic_rule",
            rule_name="semantic_density",
            baseline_pass=_SEMANTIC_DENSITY_MIN <= baseline_density <= _SEMANTIC_DENSITY_MAX,
            candidate_pass=density_pass,
            detail=f"density={density:.4f}",
        ))

        score = passed / total if total else 0.0
        # bridge 推荐：hard_failure → reject；否则 accept（gate 据 score delta 决策）
        recommendation = "reject" if hard_failures else "accept"

        return EvalResult(
            score=score,
            metric="hard",
            hard_failures=tuple(hard_failures),
            evidence=tuple(evidence),
            confidence=0.7,
            recommendation=recommendation,  # type: ignore[arg-type]
        )

    # ── 7 mode 检查 ───────────────────────────────────────

    @staticmethod
    def _read_content(record: Any) -> str:
        """读 SKILL.md 全文。record.path 文件。失败返空。"""
        try:
            from pathlib import Path
            return Path(record.path).read_text(encoding="utf-8")
        except Exception:
            return ""

    @staticmethod
    def _split_body(content: str) -> str:
        """去 frontmatter，返 body。"""
        m = _YAML_FRONTMATTER.match(content)
        if m:
            return content[m.end():]
        return content

    @staticmethod
    def _check_nonempty(content: str) -> bool:
        body = ProgrammaticEvalBridge._split_body(content)
        return len(body.strip()) > 0

    @staticmethod
    def _check_json_parseable(content: str) -> bool:
        """frontmatter YAML 可解析。无 frontmatter 也算 pass（CAPTURED 可能无）。"""
        m = _YAML_FRONTMATTER.match(content)
        if not m:
            return True
        try:
            import yaml
            yaml.safe_load(m.group(1))
            return True
        except Exception:
            return False

    @staticmethod
    def _check_must_cite(content: str) -> bool:
        """含引用/来源标记。"""
        return bool(_CITE_PATTERN.search(content))

    @staticmethod
    def _check_paragraph_limit(content: str) -> bool:
        """段落数不超限。"""
        body = ProgrammaticEvalBridge._split_body(content)
        paragraphs = [p for p in body.split("\n\n") if p.strip()]
        return len(paragraphs) <= _PARAGRAPH_LIMIT

    @staticmethod
    def _check_lead_with_conclusion(content: str) -> bool:
        """首 3 段含结论性词（lead with conclusion）。软检查，无则 fail 不 hard。"""
        body = ProgrammaticEvalBridge._split_body(content).strip()
        if not body:
            return False
        paras = body.split("\n\n")[:3]
        head = "\n\n".join(paras)
        return any(w.lower() in head.lower() for w in _CONCLUSION_WORDS)

    @staticmethod
    def _check_markdown_table(content: str) -> bool:
        """含 markdown 表格结构（如适用，无也 pass——非强制）。"""
        return True  # 非所有 skill 需表格，宽松 pass

    @staticmethod
    def _check_no_unfounded_claims(content: str) -> bool:
        """无绝对化无据声明。"""
        return not any(w in content for w in _UNFOUNDED_WORDS)

    @staticmethod
    def _semantic_density(content: str) -> float:
        """指令性词密度 = 指令词出现次数 / 总词数。"""
        if not content:
            return 0.0
        words = re.findall(r"\w+", content)
        if not words:
            return 0.0
        count = sum(content.upper().count(w) for w in _DIRECTIVE_WORDS)
        return count / len(words)
