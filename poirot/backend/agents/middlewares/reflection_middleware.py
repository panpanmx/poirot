"""ReflectionMiddleware — ReAct 退出闸门，简单反思（L1 充分性）。

after_model：模型想退出时，用 observations 对 todos step 覆盖度判断实质充分性。
不足 → reflection_items + jump_to model 补研究。外壳 + 可替换 Strategy 架构，
ReflectionAction 契约预留 revise_plan/backtrack/rollback_to 供未来 L2/L3 扩展。
仅 general/expert 启用。完整设计见 design_docs/15-reflection-middleware-design.md。
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, TypedDict, override

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from poirot.backend.agents.middlewares import _jump_budget
from poirot.backend.agents.middlewares.todo_middleware import _has_tool_call_intent
from poirot.backend.agents.state.types import ReflectionItem, ThreadState


class ReflectionAction(TypedDict):
    """策略返回的动作契约。L1 只用 pass/continue；revise_plan/backtrack/rollback_to 预留。"""

    verdict: str  # "pass" | "continue" | "revise_plan" | "backtrack"
    reflection_items: list[Any]
    plan: Any  # revise_plan/backtrack 时的新 plan，否则 None
    guidance: str  # 注回模型的提示
    rollback_to: str  # backtrack 回退到的决策节点 id（L3 未来）


class ReflectionStrategy(Protocol):
    def reflect(self, state: dict[str, Any], runtime: Runtime) -> ReflectionAction: ...


def _make_reflection_id() -> str:
    return f"refl-{uuid.uuid4().hex[:12]}"


def _step_id(obs: Any) -> str | None:
    if isinstance(obs, dict):
        return obs.get("step_id")
    return getattr(obs, "step_id", None)


class SufficiencyStrategy:
    """L1 充分性守门：todos 全完成时，检查每步是否有 observation 覆盖。

    未完成 todo 交给 Todo Layer 2（形式完成），Reflection 只在 todo 全完成时
    判实质充分——避免与 Todo 同轮双跳。
    """

    def reflect(self, state: dict[str, Any], runtime: Runtime) -> ReflectionAction:
        todos = state.get("todos") or []
        if todos and not all(t.get("status") == "completed" for t in todos):
            return ReflectionAction(verdict="pass", reflection_items=[], plan=None, guidance="", rollback_to="")

        observations = state.get("observations") or []
        if not observations:
            return ReflectionAction(verdict="pass", reflection_items=[], plan=None, guidance="", rollback_to="")

        covered = {_step_id(o) for o in observations if _step_id(o)}
        missing = [f"todo-{i}" for i, _ in enumerate(todos) if f"todo-{i}" not in covered]
        if not missing:
            return ReflectionAction(verdict="pass", reflection_items=[], plan=None, guidance="", rollback_to="")

        item = ReflectionItem(
            item_id=_make_reflection_id(),
            scope="run",
            kind="gap",
            question=f"以下步骤标记完成但缺少证据覆盖：{', '.join(missing)}",
            related_refs=tuple(missing),
        )
        guidance = (
            "<system_reminder>\n"
            f"以下研究步骤已标记完成但缺少证据支撑：{', '.join(missing)}。\n"
            "请针对这些步骤补充搜索/调研，确保每步都有 observations 证据后再给出最终答案。\n"
            "</system_reminder>"
        )
        return ReflectionAction(verdict="continue", reflection_items=[item], plan=None, guidance=guidance, rollback_to="")


class ReflectionMiddleware(AgentMiddleware):
    """外壳：管触发时机 + jump 预算；判断逻辑委托给 ReflectionStrategy。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def __init__(self, strategy: ReflectionStrategy | None = None) -> None:
        self._strategy = strategy or SufficiencyStrategy()

    @hook_config(can_jump_to=["model"])
    @override
    def after_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if not last_ai or _has_tool_call_intent(last_ai):
            return None

        action = self._strategy.reflect(state if isinstance(state, dict) else dict(state), runtime)
        if action["verdict"] == "pass":
            return None

        # 共享 jump 预算门（与 Todo 合计 ≤3，D6）
        if not _jump_budget.try_consume(runtime):
            return None

        update: dict[str, Any] = {"reflection_items": action["reflection_items"]}
        if action["guidance"]:
            update["messages"] = [HumanMessage(
                name="reflection",
                additional_kwargs={"hide_from_ui": True},
                content=action["guidance"],
            )]
        if action["plan"]:
            update["plan"] = action["plan"]
        return {"jump_to": "model", **update}

    @hook_config(can_jump_to=["model"])
    @override
    async def aafter_model(self, state: ThreadState, runtime: Runtime) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
