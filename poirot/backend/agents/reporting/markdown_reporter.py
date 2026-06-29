from __future__ import annotations

from typing import Any

from poirot.backend.agents.reporting.result import ReportResult


class MarkdownReporter:
    def generate_report(self, thread_state: dict[str, Any], run_context: Any) -> ReportResult:
        question = thread_state.get("research_question") or thread_state.get("user_input") or "Research report"
        observations = thread_state.get("observations", [])
        sources = thread_state.get("sources", [])

        lines = [
            f"# {question}",
            "",
            "## Summary",
            _summary(observations),
            "",
            "## Findings",
        ]
        if observations:
            lines.extend(f"- {_field(observation, 'content')}" for observation in observations)
        else:
            lines.append("- No observations collected.")

        lines.extend(["", "## Sources"])
        if sources:
            lines.extend(
                f"- [{_field(source, 'title') or _field(source, 'url')}]({_field(source, 'url')})"
                for source in sources
            )
        else:
            lines.append("- No sources.")

        draft_report = "\n".join(lines)
        final_report = draft_report
        run_context.journal.append(
            "report.generated",
            {
                "title": str(question),
                "mode": run_context.config.runtime.mode,
            },
        )
        return ReportResult(draft_report=draft_report, final_report=final_report)


def _summary(observations: list[Any]) -> str:
    if not observations:
        return "No evidence collected yet."
    return _field(observations[0], "content")


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)
