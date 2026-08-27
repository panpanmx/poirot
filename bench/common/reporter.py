"""Run 数据采集：一次 run 结束后从 state + 磁盘汇总全部可量化信息。

数据来源（探索确认）：
- result.state["messages"] —— AIMessage.usage_metadata / POIROT_EXTERNALIZED_META / context_budget_stop
- result.state["governance"] —— budget.fraction / metrics.summarize_count / snapshot_path / summary
- 磁盘 thread_dir/runs/{run_id}/ —— record.json / events.jsonl / artifacts/final_report.md
- compaction.jsonl —— .poirot/logs/threads/{tid}/runs/{rid}/compaction.jsonl（相对 CWD，故 bench 从项目根运行）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from poirot.backend.agents.context_engineering.utilities import token_counter

POIROT_EXTERNALIZED_META = "poirot.externalized_meta"
POIROT_EXTERNALIZED_PATH = "poirot.externalized_path"
CONTEXT_BUDGET_STOP = "context_budget_stop"


@dataclass
class RunDatum:
    """一次 run 的全量量化采集结果。"""

    run_id: str
    thread_id: str
    final_report: str = ""
    duration_s: float = 0.0
    usage: dict | None = None  # {prompt_tokens, completion_tokens, total_tokens}
    governance: dict | None = None  # state.governance
    compaction_events: list[dict] = field(default_factory=list)
    externalized_count: int = 0
    externalized_tokens_saved: int = 0
    budget_stop_count: int = 0
    summary_text: str | None = None
    snapshot_path: str | None = None
    last_ai_content: str = ""
    error: str | None = None
    tool_calls_count: int = 0
    web_search_count: int = 0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["usage"] = self.usage
        return d


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        return "".join(parts)
    return str(content) if content else ""


def usage_from_state(state: dict) -> dict | None:
    """累加全部 AIMessage 的 usage_metadata（langchain 标准字段）。全空返 None。"""
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    found = False
    for msg in state.get("messages", []) or []:
        meta = getattr(msg, "usage_metadata", None)
        if not meta:
            continue
        found = True
        total["prompt_tokens"] += int(meta.get("input_tokens", 0) or 0)
        total["completion_tokens"] += int(meta.get("output_tokens", 0) or 0)
        total["total_tokens"] += int(meta.get("total_tokens", 0) or 0)
    return total if found else None


def collect_after_run(runtime: Any, result: Any, duration_s: float = 0.0) -> RunDatum:
    """从 run 结果 + 磁盘采集 RunDatum。runtime 可为 None（只读磁盘）。"""
    state: dict = getattr(result, "state", None) or {}
    run_id = result.run_id if result is not None else "?"
    thread_id = result.thread_id if result is not None else "?"
    final_report = getattr(result, "final_report", "") or ""

    datum = RunDatum(
        run_id=run_id,
        thread_id=thread_id,
        final_report=final_report,
        duration_s=duration_s,
        usage=usage_from_state(state),
        governance=state.get("governance"),
        last_ai_content=_last_ai_content(state),
    )

    # 消息级埋点扫描
    for msg in state.get("messages", []) or []:
        kw = getattr(msg, "additional_kwargs", {}) or {}
        if kw.get(POIROT_EXTERNALIZED_META):
            meta = kw[POIROT_EXTERNALIZED_META]
            datum.externalized_count += 1
            datum.externalized_tokens_saved += int(meta.get("tokens_saved", 0) or 0)
        if kw.get(CONTEXT_BUDGET_STOP) is not None:
            datum.budget_stop_count += 1
        tc = getattr(msg, "tool_calls", None) or []
        if tc:
            datum.tool_calls_count += len(tc)
            for call in tc:
                if "web_search" in (call.get("name", "") or ""):
                    datum.web_search_count += 1

    # governance 摘要
    gov = datum.governance or {}
    default = gov.get("default") or {}
    datum.summary_text = default.get("summary")
    datum.snapshot_path = default.get("snapshot_path")

    # compaction.jsonl（磁盘，CWD 项目根）
    compaction_path = (
        Path(".poirot") / "logs" / "threads" / thread_id / "runs" / run_id / "compaction.jsonl"
    )
    if compaction_path.exists():
        for line in compaction_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    datum.compaction_events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return datum


def _last_ai_content(state: dict) -> str:
    for msg in reversed(state.get("messages", []) or []):
        if getattr(msg, "type", "") == "ai":
            text = _extract_text_content(getattr(msg, "content", ""))
            if text.strip():
                return text
    return ""


def read_run_from_disk(threads_root: str | Path, thread_id: str, run_id: str) -> RunDatum:
    """CLI 子进程模式 / 事后补采：只读磁盘恢复 RunDatum（无 state 部分）。"""
    threads_root = Path(threads_root)
    run_dir = threads_root / thread_id / "runs" / run_id
    datum = RunDatum(run_id=run_id, thread_id=thread_id)
    record_path = run_dir / "record.json"
    if record_path.exists():
        try:
            rec = json.loads(record_path.read_text(encoding="utf-8"))
            datum.final_report = rec.get("final_report", "")
        except Exception:
            pass
    artifact = run_dir / "artifacts" / "final_report.md"
    if artifact.exists():
        datum.final_report = artifact.read_text(encoding="utf-8")
    compaction = run_dir / "compaction.jsonl"
    if compaction.exists():
        for line in compaction.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    datum.compaction_events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return datum


def compression_ratio_from_snapshot(snapshot_path: str | None, summary_text: str | None) -> dict | None:
    """实测压缩率 = token_counter(snapshot 全量消息) / token_counter(summary)。

    snapshot 文件为压缩前全量消息的 JSON dump（.poirot/snapshots/snapshot-*.json）。
    """
    if not snapshot_path or not summary_text:
        return None
    snapshot_path = Path(snapshot_path)
    if not snapshot_path.exists():
        return None
    try:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    messages = data.get("messages") if isinstance(data, dict) else data
    if not messages:
        return None
    before = token_counter(messages)
    after = token_counter([summary_text])
    if after <= 0:
        return None
    return {
        "before_tokens": before,
        "after_tokens": after,
        "ratio": round(before / after, 2),
        "pct_of_original": round(after / before * 100, 2),
    }


def parse_reported_ratio(summary_text: str | None) -> float | None:
    """正则提取压缩 prompt 要求 LLM 报告的 `compression ratio: ~N:1`（summarize.md:75）。"""
    import re

    if not summary_text:
        return None
    m = re.search(r"compression\s+ratio[:\s]*~?\s*([\d.]+)\s*:\s*1", summary_text, re.IGNORECASE)
    return float(m.group(1)) if m else None
