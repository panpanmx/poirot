"""治理层数据类型：能力上下文 / 结果 / metric。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from poirot.backend.agents.state.types import GovernanceState


@dataclass(frozen=True)
class CapabilityContext:
    """能力实现执行上下文，由 middleware 构造传入。

    state 为 ThreadState 只读快照；governance 为 state["governance"] 引用。
    hook-specific 字段按触发 hook 填充，不适用时为 None。
    """

    state: Mapping[str, Any]
    governance: GovernanceState | None
    config: Any
    token_counter: Callable[[list], int]
    runtime: Any
    messages: list | None = None
    tools: list | None = None
    model_request: Any | None = None
    tool_call_request: Any | None = None
    tool_result: Any | None = None


@dataclass(frozen=True)
class CapabilityResult:
    """能力实现返回值，middleware 据此 apply 到 state 或 request。

    - state_patch：写入 ThreadState（含 governance，经 reducer 合并），持久
    - request_override：替换 request payload，request-scoped 不持久
    - messages_patch：消息级操作（RemoveMessage / 替换）
    - metrics：本次产出 metric
    - jump_to：跳转目标节点
    """

    state_patch: dict[str, Any] | None = None
    request_override: Any | None = None
    messages_patch: list | None = None
    metrics: list[GovernanceMetric] = field(default_factory=list)
    jump_to: str | None = None


@dataclass(frozen=True)
class GovernanceMetric:
    """能力级 metric。capability + metric_key 组合前缀写入 governance.metrics。"""

    capability: str
    metric_key: str
    value: int | float
    run_id: str = ""
    thread_id: str = ""


def merge_metrics_into_governance(
    governance: GovernanceState | None, metrics: list[GovernanceMetric]
) -> GovernanceState:
    """将 GovernanceMetric 列表合并进 governance，按 ``{cap}.{key}`` 前缀写入 metrics 子 dict。"""
    if not metrics:
        return dict(governance) if governance else {}  # type: ignore[return-value]
    g: dict[str, Any] = dict(governance) if governance else {}
    metrics_dict: dict[str, Any] = dict(g.get("metrics") or {})
    for m in metrics:
        metrics_dict[f"{m.capability}.{m.metric_key}"] = m.value
    g["metrics"] = metrics_dict
    return g  # type: ignore[return-value]


def apply_capability_result(state: Mapping[str, Any], result: CapabilityResult) -> dict[str, Any] | None:
    """将 CapabilityResult 转为 state-channel hook 返回的 dict patch。

    适用于 before/after_agent、before/after_model（返回 dict 的 hook）。
    wrap_model_call/wrap_tool_call 的 request_override 由调用方 inline 处理。
    """
    patch: dict[str, Any] = dict(result.state_patch or {})
    if result.messages_patch:
        patch["messages"] = result.messages_patch
    if result.metrics:
        base_gov = patch.get("governance", state.get("governance"))
        patch["governance"] = merge_metrics_into_governance(base_gov, result.metrics)
    if result.jump_to:
        patch["jump_to"] = result.jump_to
    return patch or None
