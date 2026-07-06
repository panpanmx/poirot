from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, NotRequired, TypedDict

from langchain.agents import AgentState

from poirot.backend.agents.state.reducers import (
    merge_artifacts,
    merge_citations,
    merge_errors,
    merge_final_report,
    merge_governance,
    merge_metadata,
    merge_observations,
    merge_reflection_items,
    merge_sources,
    merge_todos,
)


class GovernanceState(TypedDict, total=False):
    """上下文治理层共享状态（存 ThreadState.governance，跨轮持久）。

    两层机制：
    - 固定槽（下述字段）：跨能力共享读的协调契约，强类型。如 Compressor 读
      externalized_refs 跳过已外化 ToolMessage。
    - per-capability 前缀：能力私有/扩展数据走 ``<cap>.<key>`` 前缀 key，主要
      落 metrics dict 内分桶（如 "externalizer.bytes_externalized"）。
      merge_governance deep-merge 并存，同 key last-write-wins。各能力只写
      自己前缀，不越界（单测/CR 把关，无中央强制）。

    边界准则：跨能力需读 → 固定槽；仅本能力私有 → 前缀。

    全字段可 JSON 序列化（str/int/dict/list），禁 file handle 等不可序列化对象。
    """

    strategy_name: str
    externalized_refs: dict[str, str]
    promoted_tools: dict[str, Any]
    compress_watermark: int
    budget_usage: dict[str, int]
    injected_reminder_ids: list[str]
    metrics: dict[str, Any]


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
    # F8.1：errors 升级为工具调用账本，扩展字段（带默认值兼容既有构造）
    kind: str = "failure"           # "failure" / "success"
    tool_name: str = ""
    attempt: int = 0                # 该 tool 连续失败次（成功归 0）
    error_type: str = ""            # F5 分类
    reason: str = ""                # F8.2 原因模板


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
    governance: Annotated[GovernanceState | None, merge_governance]
