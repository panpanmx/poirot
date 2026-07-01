from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, NotRequired

from langchain.agents import AgentState

from poirot.backend.agents.state.reducers import (
    merge_artifacts,
    merge_citations,
    merge_errors,
    merge_final_report,
    merge_metadata,
    merge_observations,
    merge_reflection_items,
    merge_sources,
    merge_todos,
)


@dataclass(frozen=True)
class IntentState:
    task_type: str
    depth: str
    objective: str
    constraints: tuple[str, ...] = field(default_factory=tuple)
    output_format: str = "markdown_report"
    clarification_needed: bool = False


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    title: str
    description: str = ""
    status: str = "pending"


@dataclass(frozen=True)
class ResearchPlan:
    plan_id: str
    goal: str
    steps: tuple[PlanStep, ...] = field(default_factory=tuple)
    status: str = "pending"


@dataclass(frozen=True)
class Observation:
    observation_id: str
    step_id: str | None
    content: str
    source_refs: tuple[str, ...] = field(default_factory=tuple)
    created_at: str | None = None


@dataclass(frozen=True)
class Source:
    source_id: str
    url: str
    title: str = ""
    source_type: str = "web"
    retrieved_at: str | None = None
    summary: str = ""


@dataclass(frozen=True)
class Citation:
    citation_id: str
    source_id: str
    quote: str
    claim: str
    location: str | None = None


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    artifact_type: str
    title: str
    path: str
    summary: str = ""
    source_refs: tuple[str, ...] = field(default_factory=tuple)
    created_at: str | None = None


@dataclass(frozen=True)
class ReflectionItem:
    item_id: str
    scope: str
    kind: str
    question: str
    status: str = "open"
    related_refs: tuple[str, ...] = field(default_factory=tuple)
    created_at: str | None = None


@dataclass(frozen=True)
class AgentError:
    error_id: str
    stage: str
    message: str
    related_refs: tuple[str, ...] = field(default_factory=tuple)
    created_at: str | None = None


class ThreadState(AgentState):
    """LangGraph state schema for Poirot research threads.

    Extends AgentState (inherits messages with add_messages reducer).
    Field-level Annotated reducers drive graph-internal state merge.
    """

    user_input: NotRequired[str]
    intent: NotRequired[Any]
    research_question: NotRequired[str]
    plan: NotRequired[Any]
    current_step_id: NotRequired[str | None]
    observations: Annotated[list, merge_observations]
    sources: Annotated[list, merge_sources]
    citations: Annotated[list, merge_citations]
    artifacts: Annotated[list, merge_artifacts]
    reflection_items: Annotated[list, merge_reflection_items]
    final_report: Annotated[str | None, merge_final_report]
    errors: Annotated[list, merge_errors]
    metadata: Annotated[dict, merge_metadata]
    todos: Annotated[list | None, merge_todos]
