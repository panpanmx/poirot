from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from poirot.backend.agents.middlewares.middleware_manager import MiddlewareManager
from poirot.backend.agents.state.reducers import merge_thread_state
from poirot.backend.agents.state.types import Observation, ResearchPlan, Source


@dataclass(frozen=True)
class ReActRunner:
    capability_registry: Any
    middleware_manager: MiddlewareManager | None = None

    def run(self, thread_state: dict[str, Any], run_context: Any) -> dict[str, Any]:
        mode = run_context.config.runtime.mode
        state = dict(thread_state)
        if mode in {"general", "expert"}:
            state = merge_thread_state(state, {"plan": _make_plan(state)})
            tool = self.capability_registry.get_tool("web_search_mcp")
            if self.middleware_manager:
                state = self.middleware_manager.run_hook("before_tool", state, run_context)
            results = tool.invoke(
                {
                    "query": state.get("research_question") or state.get("user_input", ""),
                    "max_results": 3,
                },
                run_context,
            )
            patch = _search_results_to_patch(results)
            state = merge_thread_state(state, patch)
            if self.middleware_manager:
                state = self.middleware_manager.run_hook("after_tool", state, run_context)
        else:
            state = merge_thread_state(
                state,
                {
                    "observations": [
                        Observation(
                            observation_id="obs-fast-answer",
                            step_id=None,
                            content=f"Fast answer prepared for: {state.get('research_question') or state.get('user_input', '')}",
                        )
                    ]
                },
            )
        return state


def _make_plan(state: dict[str, Any]) -> ResearchPlan:
    question = state.get("research_question") or state.get("user_input", "")
    return ResearchPlan(
        plan_id="plan-1",
        goal=str(question),
        steps=(),
        status="completed",
    )


def _search_results_to_patch(results: list[Any]) -> dict[str, Any]:
    observations: list[Observation] = []
    sources: list[Source] = []
    for index, result in enumerate(results, start=1):
        source_id = f"s{index}"
        sources.append(
            Source(
                source_id=source_id,
                url=_field(result, "url"),
                title=_field(result, "title"),
                summary=_field(result, "snippet"),
            )
        )
        observations.append(
            Observation(
                observation_id=f"obs-{index}",
                step_id=None,
                content=_field(result, "snippet"),
                source_refs=(source_id,),
            )
        )
    return {"observations": observations, "sources": sources}


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name, "")
    return getattr(item, name)
