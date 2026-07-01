"""RunJournalMiddleware — 把 agent/model/tool 生命周期事件记入 RunJournal。

AgentMiddleware 版（取代旧 BaseMiddleware 体系）。从 runtime configurable 读
journal / run_id（经 _get_runtime_value 三路径，兼容 LangGraph ≥1.1.9 与测试 SimpleNamespace）。
_get_runtime_value 为模块级函数，供 TodoMiddleware / _jump_budget 复用。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime


def _get_runtime_value(runtime: Any, key: str, default: Any = None) -> Any:
    """三路径提取 runtime configurable 值（兼容测试 SimpleNamespace + LangGraph ≥1.1.9）。"""
    if runtime is None:
        return default
    # Path 1: runtime.context（dict 或对象）—— 测试与旧版 LangGraph
    ctx = getattr(runtime, "context", None)
    if ctx is not None:
        if isinstance(ctx, dict):
            if key in ctx:
                return ctx[key]
        else:
            val = getattr(ctx, key, None)
            if val is not None:
                return val
    # Path 2: runtime.get_configurable()—— LangGraph runtime API
    get_cfg = getattr(runtime, "get_configurable", None)
    if callable(get_cfg):
        try:
            cfg = get_cfg()
            if cfg and isinstance(cfg, dict) and key in cfg:
                return cfg[key]
        except Exception:
            pass
    # Path 3: runtime.config["configurable"]—— 兜底
    config = getattr(runtime, "config", None)
    if isinstance(config, dict):
        configurable = config.get("configurable", {})
        if isinstance(configurable, dict) and key in configurable:
            return configurable[key]
    return default


def _tool_text(result: Any) -> str:
    if isinstance(result, ToolMessage):
        content = result.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item["text"] if isinstance(item, dict) and "text" in item else str(item)
                for item in content if item
            )
        return str(content)
    return str(result)


class RunJournalMiddleware(AgentMiddleware):
    """记录 agent/model/tool 事件到 RunJournal。无 journal 时静默不报错。"""

    def _journal(self, runtime: Runtime) -> Any:
        return _get_runtime_value(runtime, "journal", None)

    def _run_id(self, runtime: Runtime) -> Any:
        return _get_runtime_value(runtime, "run_id", None)

    @override
    def before_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        journal = self._journal(runtime)
        if journal is not None:
            journal.append("agent.started", {"run_id": self._run_id(runtime)})
        return None

    @override
    def after_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        journal = self._journal(runtime)
        if journal is not None:
            journal.append("agent.finished", {"run_id": self._run_id(runtime)})
        return None

    @override
    def before_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        journal = self._journal(runtime)
        if journal is not None:
            journal.append("llm.request", {"run_id": self._run_id(runtime)})
        return None

    @override
    def after_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        journal = self._journal(runtime)
        if journal is not None:
            journal.append("llm.response", {"run_id": self._run_id(runtime)})
        return None

    @override
    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        runtime = getattr(request, "runtime", None)
        journal = self._journal(runtime) if runtime is not None else None
        run_id = self._run_id(runtime) if runtime is not None else None
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        tool_input = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}

        if journal is not None:
            journal.append("tool.called", {
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
            })
        try:
            result = handler(request)
            status = "ok"
        except Exception as exc:
            status = "error"
            if journal is not None:
                journal.append("tool.finished", {
                    "run_id": run_id,
                    "tool_name": tool_name,
                    "output": str(exc),
                    "status": status,
                })
            raise
        if journal is not None:
            journal.append("tool.finished", {
                "run_id": run_id,
                "tool_name": tool_name,
                "output": _tool_text(result)[:2000],
                "status": status,
            })
        return result

    @override
    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        runtime = getattr(request, "runtime", None)
        journal = self._journal(runtime) if runtime is not None else None
        run_id = self._run_id(runtime) if runtime is not None else None
        tool_call = getattr(request, "tool_call", None) or {}
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        tool_input = tool_call.get("args", {}) if isinstance(tool_call, dict) else {}

        if journal is not None:
            journal.append("tool.called", {
                "run_id": run_id,
                "tool_name": tool_name,
                "tool_input": tool_input,
            })
        try:
            result = await handler(request)
            status = "ok"
        except Exception as exc:
            status = "error"
            if journal is not None:
                journal.append("tool.finished", {
                    "run_id": run_id,
                    "tool_name": tool_name,
                    "output": str(exc),
                    "status": status,
                })
            raise
        if journal is not None:
            journal.append("tool.finished", {
                "run_id": run_id,
                "tool_name": tool_name,
                "output": _tool_text(result)[:2000],
                "status": status,
            })
        return result
