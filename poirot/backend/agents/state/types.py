from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


ThreadState = dict[str, Any]
