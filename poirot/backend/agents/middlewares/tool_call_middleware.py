"""ToolCallMiddleware — 工具调用账本 + 失败分类 + 重试预算 + 超限禁工具 + 硬预算。

FD17-FD19：最外层 wrap_tool_call，看到所有工具最终结果 + 捕获内层异常。
成败都记 errors 账本（AgentError kind=success/failure），per-tool 连续失败 + 全局调用数从 errors 派生。
禁工具时短路 + 自发 tool.blocked 事件。仅 general/expert 启用。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from poirot.backend.agents.middlewares.run_journal_middleware import _get_runtime_value
from poirot.backend.agents.state.types import AgentError, ThreadState

_RETRY_BUDGET = 3          # per-tool 连续失败上限（禁工具）
_HARD_BUDGET = 30          # run 级工具调用总数上限
_SUMMARY_THRESHOLDS = (3, 6, 9)  # 失败摘要递进注入阈值

# F5：业务失败特征正则
_BLOCKED_RE = re.compile(r"blocked|forbidden|captcha|access denied|403", re.IGNORECASE)
_EMPTY_RE = re.compile(r"no results? found|no results|empty result|nothing found|0 results", re.IGNORECASE)

_REASON_MAP = {
    "network": "网络问题（超时/连接失败）",
    "rate_limit": "API 限流",
    "blocked": "内容被封锁/拒绝访问",
    "empty": "无搜索结果",
    "server_error": "服务端错误（5xx）",
    "client_error": "客户端错误（4xx，换 provider 也会失败）",
    "unknown": "未知错误",
}


def _make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def _classify_exception(exc: Exception) -> str:
    """F5：按异常类型归基本错误分类。"""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "network"
    try:
        import openai
        if isinstance(exc, getattr(openai, "RateLimitError", type(None))):
            return "rate_limit"
        if isinstance(exc, getattr(openai, "APIStatusError", type(None))):
            status = getattr(exc, "status_code", None)
            if status is not None and 500 <= status < 600:
                return "server_error"
            if status is not None and 400 <= status < 500:
                return "client_error"
    except ImportError:
        pass
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg or "connection" in msg:
        return "network"
    if "rate" in msg and "limit" in msg:
        return "rate_limit"
    return "unknown"


def _classify_business_failure(text: str) -> str | None:
    """F5：HTTP 200 但内容含业务失败特征。"""
    if _BLOCKED_RE.search(text):
        return "blocked"
    if _EMPTY_RE.search(text):
        return "empty"
    return None


def _reason_for(error_type: str) -> str:
    return _REASON_MAP.get(error_type, "未知错误")


def _is_failure(result: Any) -> tuple[str, str] | None:
    """判断工具结果是否失败。返回 (error_type, reason) 或 None。

    - ToolMessage status="error" → 按内容/异常推断
    - HTTP 200 含封锁/空结果特征 → blocked/empty
    - 否则 None（成功）
    """
    if isinstance(result, ToolMessage) and getattr(result, "status", None) == "error":
        # 内层已标 error（如 Evidence 捕获异常）—— 从 content 推断分类
        text = _tool_text(result)
        for et in ("network", "rate_limit", "blocked", "empty", "server_error", "client_error"):
            if et in text.lower():
                return et, _reason_for(et)
        return "unknown", _reason_for("unknown")
    text = _tool_text(result)
    biz = _classify_business_failure(text)
    if biz:
        return biz, _reason_for(biz)
    # 检测工具返回的 error JSON（如 ddg {"error": "Search failed: ..."}）
    if '"error"' in text and ('search failed' in text.lower() or 'not installed' in text.lower() or 'failed' in text.lower()):
        return "unknown", "工具返回错误"
    return None


def _latest_attempt(errors: list, tool_name: str) -> int:
    """该 tool 最新条目的 attempt（连续失败计数，成功归 0）。"""
    for err in reversed(errors):
        if _field(err, "tool_name") == tool_name:
            return int(_field(err, "attempt") or 0)
    return 0


def _total_calls(errors: list) -> int:
    """全局工具调用数 = len(errors)（成功+失败都记）。"""
    return len(errors)


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


class ToolCallMiddleware(AgentMiddleware):
    """工具调用账本：成败都记 errors，per-tool 重试/禁工具，硬预算兜底。"""

    state_schema = ThreadState  # type: ignore[assignment]

    def _journal(self, runtime: Runtime) -> Any:
        return _get_runtime_value(runtime, "journal", None)

    def _emit(self, runtime: Runtime, event_type: str, payload: dict) -> None:
        j = self._journal(runtime)
        if j is not None:
            j.append(event_type, payload)

    @override
    def before_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        return None

    def _build_failure_summary(self, errors: list, tool_name: str) -> str:
        """F8.2：结构化失败摘要（错误类型→原因模板）。"""
        fails = [e for e in errors if _field(e, "tool_name") == tool_name and _field(e, "kind") == "failure"]
        lines = [f"工具 {tool_name} 已连续失败 {len(fails)} 次："]
        for e in fails[-3:]:
            lines.append(f"- {_field(e, 'error_type')}: {_field(e, 'reason') or _field(e, 'message')}")
        lines.append("请分析失败模式，考虑换搜索词/换工具/换方法；若判断不可恢复，基于现有证据收尾报告。")
        return "\n".join(lines)

    def _process_result(
        self, request: ToolCallRequest, result: Any, runtime: Runtime, exc: Exception | None,
    ) -> Any:
        """返回阶段处理：记 errors 账本 + 失败摘要 + 硬预算。"""
        tool_name = request.tool_call.get("name", "")
        call_id = request.tool_call.get("id", "")
        state = request.state
        errors = state.get("errors") or [] if isinstance(state, dict) else []

        # 判定成败 + 分类
        if exc is not None:
            error_type = _classify_exception(exc)
            kind = "failure"
            attempt = _latest_attempt(errors, tool_name) + 1
            reason = _reason_for(error_type)
            err = AgentError(
                error_id=_make_id("err"), stage="tool",
                message=f"{tool_name}: {exc}", tool_name=tool_name,
                kind=kind, attempt=attempt, error_type=error_type, reason=reason,
                related_refs=(call_id,), created_at=_now_iso(),
            )
            self._emit(runtime, "tool.failure_streak", {"tool": tool_name, "attempt": attempt, "type": error_type})
        else:
            fail = _is_failure(result)
            if fail:
                error_type, reason = fail
                kind = "failure"
                attempt = _latest_attempt(errors, tool_name) + 1
                err = AgentError(
                    error_id=_make_id("err"), stage="tool",
                    message=f"{tool_name}: 业务失败 {reason}", tool_name=tool_name,
                    kind=kind, attempt=attempt, error_type=error_type, reason=reason,
                    related_refs=(call_id,), created_at=_now_iso(),
                )
                self._emit(runtime, "tool.failure_streak", {"tool": tool_name, "attempt": attempt, "type": error_type})
            else:
                kind = "success"
                attempt = 0
                err = AgentError(
                    error_id=_make_id("err"), stage="tool",
                    message=f"{tool_name}: success", tool_name=tool_name,
                    kind=kind, attempt=attempt, error_type="", reason="",
                    related_refs=(call_id,), created_at=_now_iso(),
                )

        # 记账本
        new_errors_count = _total_calls(errors) + 1
        update: dict[str, Any] = {"errors": [err]}

        # F8.2：失败摘要递进注入（3/6/9）
        if kind == "failure" and attempt in _SUMMARY_THRESHOLDS:
            summary = self._build_failure_summary(errors + [err], tool_name)
            update["messages"] = [HumanMessage(
                name="tool_failure_summary",
                additional_kwargs={"hide_from_ui": True},
                content=f"<system_reminder>\n{summary}\n</system_reminder>",
            )]

        # F8.5：硬预算兜底
        if new_errors_count >= _HARD_BUDGET:
            update.setdefault("messages", []).append(HumanMessage(
                name="tool_budget_exhausted",
                additional_kwargs={"hide_from_ui": True},
                content=f"<system_reminder>\n工具调用总数已达 {new_errors_count}（预算 {_HARD_BUDGET}），必须收尾报告。\n</system_reminder>",
            ))
            self._emit(runtime, "tool.budget_exhausted", {"count": new_errors_count, "max": _HARD_BUDGET})

        # 合并：若 result 已是 Command（内层 Evidence 返回），合并 errors 进 update
        if isinstance(result, Command):
            merged = dict(result.update)
            merged.setdefault("errors", []).extend(update["errors"])
            if "messages" in update:
                merged.setdefault("messages", []).extend(update["messages"])
            return Command(update=merged)
        # 非 Command（原 ToolMessage 或异常）：总返 Command 带 errors（+ 注入的 messages）
        if "messages" in update:
            # 有摘要/预算注入，需把原 result 也放进 messages
            update.setdefault("messages", []).insert(0, result) if result is not None else None
            return Command(update=update)
        # 成功无注入：errors + 原 result 进 messages
        update["messages"] = [result] if result is not None else []
        return Command(update=update)

    @override
    def wrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")
        state = request.state
        errors = state.get("errors") or [] if isinstance(state, dict) else []

        # F8.3：禁工具短路
        if _latest_attempt(errors, tool_name) >= _RETRY_BUDGET:
            self._emit(request.runtime, "tool.blocked", {"tool": tool_name, "reason": "retry_budget_exhausted"})
            failure_msg = ToolMessage(
                content=f"⚠️ 工具 {tool_name} 已达重试上限（{_RETRY_BUDGET}），已被禁用，请换方法或收尾。",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )
            return Command(update={"messages": [failure_msg]})

        # F8.5：硬预算短路——总调用数达上限，拒绝所有后续工具，强制模型收尾走 Reporter
        if _total_calls(errors) >= _HARD_BUDGET:
            self._emit(request.runtime, "tool.budget_exhausted", {"count": _total_calls(errors), "max": _HARD_BUDGET})
            failure_msg = ToolMessage(
                content=f"⚠️ 工具调用总数已达预算上限（{_HARD_BUDGET}），所有工具已禁用，请立即基于现有证据输出最终报告。",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )
            return Command(update={"messages": [failure_msg]})

        try:
            result = handler(request)
            return self._process_result(request, result, request.runtime, exc=None)
        except Exception as exc:
            return self._process_result(request, None, request.runtime, exc=exc)

    @override
    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")
        state = request.state
        errors = state.get("errors") or [] if isinstance(state, dict) else []

        if _latest_attempt(errors, tool_name) >= _RETRY_BUDGET:
            self._emit(request.runtime, "tool.blocked", {"tool": tool_name, "reason": "retry_budget_exhausted"})
            failure_msg = ToolMessage(
                content=f"⚠️ 工具 {tool_name} 已达重试上限（{_RETRY_BUDGET}），已被禁用，请换方法或收尾。",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )
            return Command(update={"messages": [failure_msg]})

        # F8.5：硬预算短路
        if _total_calls(errors) >= _HARD_BUDGET:
            self._emit(request.runtime, "tool.budget_exhausted", {"count": _total_calls(errors), "max": _HARD_BUDGET})
            failure_msg = ToolMessage(
                content=f"⚠️ 工具调用总数已达预算上限（{_HARD_BUDGET}），所有工具已禁用，请立即基于现有证据输出最终报告。",
                tool_call_id=request.tool_call.get("id", ""),
                status="error",
            )
            return Command(update={"messages": [failure_msg]})

        try:
            result = await handler(request)
            return self._process_result(request, result, request.runtime, exc=None)
        except Exception as exc:
            return self._process_result(request, None, request.runtime, exc=exc)
