"""Todo/Reflection/Report middleware 参数化行为测试。

default 模式（enforce_completion=False / LightReflectionStrategy / auto_synthesize=False）
vs expert 模式（True / SufficiencyStrategy / True）。
"""

from types import SimpleNamespace

from langchain_core.messages import AIMessage

from poirot.backend.agents.middlewares.reflection_middleware import (
    LightReflectionStrategy,
    ReflectionAction,
    ReflectionMiddleware,
    SufficiencyStrategy,
)
from poirot.backend.agents.middlewares.report_middleware import ReportMiddleware
from poirot.backend.agents.middlewares.todo_middleware import TodoMiddleware


def _runtime():
    return SimpleNamespace(context={})


# --------------------------------------------------------------------------- #
# TodoMiddleware enforce_completion
# --------------------------------------------------------------------------- #


def test_todo_default_init_enforce_completion_true() -> None:
    mw = TodoMiddleware()
    assert mw._enforce_completion is True


def test_todo_enforce_completion_false_can_be_set() -> None:
    mw = TodoMiddleware(enforce_completion=False)
    assert mw._enforce_completion is False


def test_todo_enforce_completion_false_skips_hard_enforcement() -> None:
    """default 模式：todos 未完成 + 模型想退出 → 不 jump，允许退出。"""
    mw = TodoMiddleware(enforce_completion=False)
    # 构造：todos 未完成 + 最后 AIMessage 无 tool_calls（想退出）
    state = {
        "messages": [AIMessage(content="最终答案", tool_calls=[])],
        "todos": [{"content": "step1", "status": "in_progress"}],
    }
    result = mw.after_model(state, _runtime())
    # default 不强制 → 不 jump_to model（返回 None 或仅 step_update，无 jump_to）
    assert result is None or "jump_to" not in result


# --------------------------------------------------------------------------- #
# ReflectionMiddleware strategy
# --------------------------------------------------------------------------- #


def test_light_reflection_strategy_always_pass() -> None:
    strategy = LightReflectionStrategy()
    action = strategy.reflect({"observations": [], "todos": []}, _runtime())
    assert action["verdict"] == "pass"
    assert action["reflection_items"] == []
    assert action["guidance"] == ""


def test_light_reflection_strategy_pass_even_with_gaps() -> None:
    """default 模式：即使有 observations 缺口也不 jump。"""
    strategy = LightReflectionStrategy()
    action = strategy.reflect(
        {"observations": [], "todos": [{"status": "completed"}]},
        _runtime(),
    )
    assert action["verdict"] == "pass"


def test_reflection_middleware_default_uses_light_strategy() -> None:
    """ReflectionMiddleware(strategy=LightReflectionStrategy) 不 jump。"""
    mw = ReflectionMiddleware(strategy=LightReflectionStrategy())
    state = {
        "messages": [AIMessage(content="答案", tool_calls=[])],
        "observations": [],
        "todos": [{"status": "completed"}],
    }
    result = mw.after_model(state, _runtime())
    assert result is None


def test_reflection_middleware_expert_uses_sufficiency_strategy() -> None:
    """ReflectionMiddleware(strategy=SufficiencyStrategy) 可 jump（专家模式）。"""
    mw = ReflectionMiddleware(strategy=SufficiencyStrategy(llm=None))
    # todos 全完成 + 无 observations → SufficiencyStrategy pass（无证据不判 gap）
    state = {
        "messages": [AIMessage(content="答案", tool_calls=[])],
        "observations": [],
        "todos": [{"status": "completed"}],
    }
    result = mw.after_model(state, _runtime())
    assert result is None  # 无 observations → pass


# --------------------------------------------------------------------------- #
# ReportMiddleware auto_synthesize
# --------------------------------------------------------------------------- #


class _FakeModel:
    def invoke(self, messages):
        return SimpleNamespace(content="合成报告")

    async def ainvoke(self, messages):
        return SimpleNamespace(content="合成报告")


def test_report_default_init_auto_synthesize_true() -> None:
    mw = ReportMiddleware(_FakeModel())
    assert mw._auto_synthesize is True


def test_report_auto_synthesize_false_skips_after_agent() -> None:
    """default 模式：auto_synthesize=False → after_agent 返回 None，不合成。"""
    mw = ReportMiddleware(_FakeModel(), auto_synthesize=False)
    state = {"observations": [{"content": "obs1"}]}
    result = mw.after_agent(state, _runtime())
    assert result is None


def test_report_auto_synthesize_true_synthesizes_when_observations() -> None:
    """expert 模式：auto_synthesize=True + observations 非空 → 合成 final_report。"""
    mw = ReportMiddleware(_FakeModel(), auto_synthesize=True)
    state = {"observations": [{"content": "obs1"}], "sources": []}
    result = mw.after_agent(state, _runtime())
    assert result is not None
    assert result["final_report"] == "合成报告"


def test_report_auto_synthesize_true_skips_when_no_observations() -> None:
    """expert 模式：observations 为空 → 不合成。"""
    mw = ReportMiddleware(_FakeModel(), auto_synthesize=True)
    state = {"observations": [], "sources": []}
    result = mw.after_agent(state, _runtime())
    assert result is None
