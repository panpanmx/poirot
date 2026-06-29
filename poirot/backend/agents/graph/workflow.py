from __future__ import annotations

from typing import Any


def run_workflow(agent: Any, question: str, run_context: Any) -> Any:
    return agent.run(question, run_context)
