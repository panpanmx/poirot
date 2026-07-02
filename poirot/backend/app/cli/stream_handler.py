"""stream_handler — StreamEvent → rich 渲染。

消费 PoirotStreamClient 产出的 StreamEvent，用 rich Console 实时渲染：
- thinking：暗灰色逐 token（style="dim"）
- answer：正常色逐 token，done 后 Markdown 整体渲染
- tool_start：Spinner + 工具名 + 参数摘要
- tool_end：停 Spinner，折叠摘要 ✓ tool → N results
- error：红色
- done：换行 + 分隔线
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

from poirot.backend.app.services.stream_service import StreamEvent


def _truncate_args(args: dict | None) -> str:
    if not args:
        return ""
    items = [f"{k}={str(v)[:50]}" for k, v in args.items() if k != "type"]
    return ", ".join(items)[:120]


def _result_summary(result: str | None) -> str:
    if not result:
        return "ok"
    if len(result) <= 80:
        return result
    return result[:77] + "..."


class StreamRenderer:
    """渲染 StreamEvent 到 rich Console。

    state dict 存：
    - full_answer：累积 answer 文本（done 后 Markdown 渲染）
    - tool_results：上一轮工具结果全文（供 /expand）
    - thinking_enabled：是否展示 thinking（/thinking off 关闭）
    - current_spinner：当前 Live spinner（tool_start 时开，tool_end 时停）
    """

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self.state: dict[str, Any] = {
            "full_answer": "",
            "tool_results": [],
            "thinking_enabled": True,
            "_live": None,
        }

    def render(self, event: StreamEvent) -> None:
        etype = event["type"]

        # 新轮首个事件时清上一轮 state（保留 tool_results 供 /expand）
        if not self.state.get("_round_active"):
            self.state["full_answer"] = ""
            self.state["tool_results"] = []
            self.state["_round_active"] = True

        if etype == "thinking":
            self._render_thinking(event)
        elif etype == "answer":
            self._render_answer(event)
        elif etype == "tool_start":
            self._render_tool_start(event)
        elif etype == "tool_end":
            self._render_tool_end(event)
        elif etype == "done":
            self._render_done()
        elif etype == "error":
            self._render_error(event)

    def _render_thinking(self, event: StreamEvent) -> None:
        if not self.state["thinking_enabled"]:
            return
        content = event["content"]
        if content:
            self.console.print(content, style="dim", end="", highlight=False)

    def _render_answer(self, event: StreamEvent) -> None:
        content = event["content"]
        if content:
            # 累积 answer 文本，不立即打印（done 后统一 Markdown 渲染，避免重复输出）
            self.state["full_answer"] += content

    def _render_tool_start(self, event: StreamEvent) -> None:
        tool_name = event["tool_name"] or "unknown"
        args_str = _truncate_args(event["tool_args"])
        spinner_text = f"{tool_name}({args_str})..." if args_str else f"{tool_name}..."

        # 停前一个 spinner（如有）
        self._stop_spinner()

        spinner = Spinner("dots", text=Text(spinner_text, style="cyan"))
        self.state["_live"] = Live(spinner, console=self.console, transient=True)
        self.state["_live"].start()

    def _render_tool_end(self, event: StreamEvent) -> None:
        self._stop_spinner()

        tool_name = event["tool_name"] or "unknown"
        summary = _result_summary(event["tool_result"])
        self.console.print(f"  [green]✓[/green] {tool_name} → {summary}", highlight=False)

        # 存全文供 /expand
        if event["tool_result"]:
            self.state["tool_results"].append({
                "tool": tool_name,
                "result": event["tool_result"],
            })

    def _render_done(self) -> None:
        self._stop_spinner()
        # answer 累积完毕，统一 Markdown 渲染输出一次（不重复纯文本）
        full = self.state["full_answer"].strip()
        if full:
            self.console.print()
            self.console.print(Markdown(full))
        self.state["full_answer"] = ""
        self.state["_round_active"] = False
        self.console.print("\n[dim]" + "─" * 40 + "[/dim]")

    def _render_error(self, event: StreamEvent) -> None:
        self._stop_spinner()
        self.console.print(f"\n[red]✗ {event['content']}[/red]")

    def _stop_spinner(self) -> None:
        live = self.state.get("_live")
        if live is not None:
            live.stop()
            self.state["_live"] = None

    def expand_last_round(self) -> None:
        """展开上一轮工具结果全文（/expand 命令调用）。"""
        results = self.state.get("tool_results", [])
        if not results:
            self.console.print("[dim]无上一轮工具结果[/dim]")
            return
        from rich.panel import Panel
        from rich.text import Text
        for r in results:
            body = Text(r["result"], style="dim")
            self.console.print(Panel(body, title=f"[cyan]{r['tool']}[/cyan]", border_style="dim"))
