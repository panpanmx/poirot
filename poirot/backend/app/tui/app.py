"""PoirotTUI — 全屏 TUI 应用（textual）。

双状态布局：
- **欢迎态**（``welcome-mode``）：logo 居中 + 副标题 + 居中输入框 + 一行提示。
- **对话态**（``conversation-mode``）：左侧对话列（滚动区 + 底部深灰蒙版输入 box + 细状态行），
  终端足够宽时右侧显示可交互会话信息面板（Context/Compact/MCP/版本）。

首次提交输入时从欢迎态切换到对话态。``poirot`` 启动此 TUI；``poirot cli`` 回退旧 CLI。
"""

from __future__ import annotations

import time
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Input, Static
from textual.binding import Binding

from poirot.backend.app.cli.banner import render_logo
from poirot.backend.app.cli.commands import get_registry, handle_command
from poirot.backend.app.services.stream_service import PoirotStreamClient
from poirot.backend.app.tui import theme
from poirot.backend.app.tui.command_palette import CommandPalette
from poirot.backend.app.tui.conversation import ConversationLog
from poirot.backend.app.tui.side_panel import SidePanel
from poirot.backend.app.tui.status_bar import StatusBar

# 宽屏阈值：>= 此列数时展开右侧会话信息面板（仅全屏/极宽终端触发）。
_WIDE_THRESHOLD = 160


# ---- Widgets ----


class WelcomeView(Container):
    """欢迎页——logo 居中 + 副标题 + 居中输入框 + 一行提示。

    ``#logo``/``#subtitle``/``#tip`` 用 ``width: 100%`` + ``content-align``/
    ``text-align: center`` 居中——它们是纯文本展示，占满整行再居中文字最稳妥。

    ``#welcome-input`` 不能直接放在 WelcomeView 下用父级 ``align: center middle``
    居中：Textual 的 vertical 布局 align 是把"整组子控件"作为一个块居中（块宽度
    取全部子控件里最宽的那个），块内每个子控件仍然是左对齐拼接，不是逐个居中。
    一旦同一层出现 width:100% 的兄弟（logo/subtitle/tip），或子控件宽度互不相同，
    这个块宽度就会被撑到跟父容器一样宽，居中 offset 直接变 0——表现为除最宽的
    那个子控件外，其余子控件全部贴左，输入框就是这么跟丢的。用 ``InputRow``
    单独包一层：InputRow 自己 width:100%（填满 WelcomeView 宽度），组内只有
    唯一子控件 Input，align 单子控件时行为正常，真正把 Input 居中。
    """

    DEFAULT_CSS = f"""
    WelcomeView {{
        align: center middle;
        height: 1fr;
        background: {theme.BG};
        padding: 0 4;
    }}
    WelcomeView > #logo {{
        width: 100%;
        height: auto;
        content-align: center middle;
        margin: 0 0 1 0;
    }}
    WelcomeView > #subtitle {{
        width: 100%;
        text-align: center;
        color: {theme.ACCENT_BRAND};
        margin: 0 0 2 0;
    }}
    WelcomeView > InputRow {{
        width: 100%;
        height: 3;
        align: center middle;
    }}
    WelcomeView > InputRow > #welcome-input {{
        width: 64;
        max-width: 90%;
        height: 3;
        border: tall {theme.BORDER};
        background: {theme.SURFACE};
        color: {theme.TEXT_PRIMARY};
        padding: 0 1;
    }}
    WelcomeView > InputRow > #welcome-input:focus {{
        border: tall {theme.BORDER_FOCUS};
    }}
    WelcomeView > #tip {{
        width: 100%;
        text-align: center;
        color: {theme.TEXT_DIM};
        margin: 1 0 0 0;
    }}
    """


class InputRow(Container):
    """欢迎页输入框的单独居中层——见 ``WelcomeView`` docstring 的对齐说明。"""


class ConversationInput(Input):
    """对话页输入框——无边框，透明底，嵌在 InputBox 里，跟随 InputBox 的深灰底+左竖线。

    Textual Input 组件内置 ``:focus`` 态会自带边框样式，必须显式覆盖为
    ``none``，否则聚焦时会在 InputBox 内部再套一层边框，形成"两层框"且
    因边框吃掉行高导致内容区被挤没、无法正常选中输入。
    """

    DEFAULT_CSS = f"""
    ConversationInput {{
        height: 1;
        border: none;
        background: transparent;
        color: {theme.TEXT_PRIMARY};
        padding: 0;
    }}
    ConversationInput:focus {{
        border: none;
        background: transparent;
    }}
    """

    def _on_mouse_down(self, event) -> None:
        """放行鼠标事件给终端原生选取（避免 textual 捕获导致乱码 + 无法复制）。"""
        event.prevent_default()

    def _on_mouse_up(self, event) -> None:
        event.prevent_default()

    def _on_mouse_move(self, event) -> None:
        event.prevent_default()


class InputBox(Container):
    """底部深灰输入框——直角矩形 + 左细竖线，和历史消息卡片同一视觉语言，简约极客。

    内含输入行 + Build·模型 信息行，统一间距。上下留白全部用 InputBox 自身的
    padding 控制（不再额外给子控件加 margin），避免两套间距机制在窗口重绘/
    resize 时相互打架造成错位。
    """

    DEFAULT_CSS = f"""
    InputBox {{
        height: auto;
        background: {theme.SURFACE};
        border-left: solid {theme.ACCENT_USER};
        padding: 1 2 1 2;
        margin: 0 2 0 2;
    }}
    InputBox:focus-within {{
        border-left: solid {theme.BORDER_FOCUS};
    }}
    InputBox > #input-info {{
        height: 1;
        color: {theme.TEXT_SECONDARY};
        padding: 0;
        margin: 0;
    }}
    """


# ---- App ----


class PoirotTUI(App):
    """Poirot 全屏 TUI——双状态布局。"""

    # Textual 内置 ctrl+p 会打开系统自带的 command palette（textual.command
    # .CommandPalette），和自定义的 Ctrl+P 面板抢同一键位、优先级更高会直接
    # 吞掉按键——必须关掉内置的，才能让 action_toggle_command_palette 生效。
    ENABLE_COMMAND_PALETTE = False

    CSS = f"""
    Screen {{
        background: {theme.BG};
    }}

    /* 欢迎态：仅显示 WelcomeView */
    PoirotTUI.welcome-mode WelcomeView {{ display: block; }}
    PoirotTUI.welcome-mode #conv-body {{ display: none; }}

    /* 对话态：显示对话主体 */
    PoirotTUI.conversation-mode WelcomeView {{ display: none; }}
    PoirotTUI.conversation-mode #conv-body {{ display: block; }}

    #conv-body {{
        layout: horizontal;
        height: 1fr;
        padding: 0 0 1 0;
    }}
    #main-col {{
        width: 1fr;
        height: 1fr;
    }}
    #side {{
        width: 44;
        display: none;
    }}
    /* 宽屏才展开右侧会话信息面板 */
    PoirotTUI.wide.conversation-mode #side {{ display: block; }}
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("ctrl+l", "clear_screen", "Clear", show=False),
        Binding("ctrl+p", "toggle_command_palette", "Commands", show=False),
    ]

    def __init__(self, runtime: Any, provider: str | None = None, model: str | None = None) -> None:
        super().__init__()
        self.runtime = runtime
        self.provider = provider
        self.model = model
        self._first_input = True
        self.cli_state: dict[str, Any] = {
            "pending_expert_mode": None,
            "pending_report": None,
            "mode": "expert" if runtime.config.runtime.expert_mode else "default",
            "model": self._resolve_model_name(),
            "provider": provider or "",
            "current_tokens": 0,
            "current_fraction": 0.0,
            "current_window": self._resolve_window(),
            "mcp_count": 0,
            "msg_count": 0,
            "_running": False,
        }
        self.registry = get_registry()

    def _resolve_model_name(self) -> str:
        """Build 信息行展示的模型名——取当前活跃 provider 的真实 model 名
        （如 deepseek-v4-flash），不是 provider 链名（如 openai,qwen,deepseek）。
        与 _resolve_window 用同一模型对象来源，保证两处展示互相一致。
        """
        try:
            model = self.runtime.capability_registry.get_model("researcher")
            from poirot.backend.agents.context_engineering.utilities import resolve_model_name
            name = resolve_model_name(model)
            if name:
                return name
        except Exception:
            pass
        try:
            from poirot.backend.agents.leader.agent import _resolve_actual_model_name
            return _resolve_actual_model_name(self.runtime.capability_registry)
        except Exception:
            return "?"

    def _resolve_window(self) -> int:
        """上下文容量：与治理策略同一来源——registry.get_model("researcher") →
        resolve_window_size 穿透 FallbackChatModel 取活跃 provider 真实窗口。
        首个 budget 事件回流后会用 governance 的 window 覆盖此初始值。"""
        try:
            model = self.runtime.capability_registry.get_model("researcher")
            from poirot.backend.agents.context_engineering.utilities import resolve_window_size
            w = resolve_window_size(model)
            if w > 0:
                return w
        except Exception:
            pass
        return 128000

    def _resolve_mcp_count(self) -> int:
        try:
            from poirot.backend.agents.agent_tools.available import get_available_tools
            from poirot.backend.agents.agent_tools.mcp_metadata import is_mcp_tool
            tools = get_available_tools(include_mcp=True)
            return sum(1 for t in tools if is_mcp_tool(t))
        except Exception:
            return 0

    def _input_info(self) -> str:
        model = self.cli_state["model"]
        provider = self.cli_state.get("provider") or ""
        base = f"■ Build · {model}"
        return f"{base}  {provider}" if provider else base

    def compose(self) -> ComposeResult:
        # 欢迎页（居中 logo + 副标题 + 输入框 + 提示）
        subtitle = f"v1.0.0 · {self.cli_state['mode']} · {self.cli_state['model']}"
        yield WelcomeView(
            Static(render_logo(), id="logo"),
            Static(subtitle, id="subtitle"),
            InputRow(ConversationInput(placeholder='Ask anything...  (输入 / 查看命令)', id="welcome-input")),
            Static("", id="tip"),
        )
        # 对话主体：左对话列 + 右信息面板
        yield Horizontal(
            Vertical(
                ConversationLog(),
                InputBox(
                    ConversationInput(
                        placeholder='Ask anything...  (输入 / 查看命令，Enter 发送)',
                        id="conv-input",
                    ),
                    Static("", id="input-info"),
                ),
                StatusBar(),
                id="main-col",
            ),
            SidePanel(id="side"),
            id="conv-body",
        )

    def on_mount(self) -> None:
        self._apply_markdown_theme()
        self.add_class("welcome-mode")
        self._apply_responsive(self.size.width)
        self._load_mcp_count()
        self.query_one("#welcome-input", Input).focus()

    def _apply_markdown_theme(self) -> None:
        """agent 输出的 Markdown 标题统一改成深橙→橙色（呼应参考设计的标题色），
        不用 Rich Markdown 默认的紫色系。``self.console`` 是 RichLog.write() 实际
        用来渲染的 Console（见 textual RichLog.write 内部用 ``self.app.console``），
        push_theme 覆盖 ``markdown.h1``~``h6`` 的 style 即可全局生效，不用逐处传参。
        """
        from rich.theme import Theme
        heading_style = f"bold {theme.ACCENT_THOUGHT}"
        self.console.push_theme(Theme({
            "markdown.h1": heading_style,
            "markdown.h2": heading_style,
            "markdown.h3": heading_style,
            "markdown.h4": heading_style,
            "markdown.h5": heading_style,
            "markdown.h6": theme.ACCENT_THOUGHT,
        }))

    def on_resize(self, event: Any) -> None:
        self._apply_responsive(event.size.width)

    def _apply_responsive(self, width: int) -> None:
        if width >= _WIDE_THRESHOLD:
            self.add_class("wide")
            self._refresh_side_panel()
        else:
            self.remove_class("wide")

    def _refresh_side_panel(self) -> None:
        try:
            self.query_one(SidePanel).update_state(self.cli_state)
        except Exception:
            pass

    @work(thread=True)
    def _load_mcp_count(self) -> None:
        count = self._resolve_mcp_count()
        self.cli_state["mcp_count"] = count
        self.call_from_thread(self._apply_mcp_count, count)

    def _apply_mcp_count(self, count: int) -> None:
        tip = self.query_one("#tip", Static)
        mcp_hint = f"{count} MCP tools" if count else "no MCP tools"
        tip.update(f"{mcp_hint}  ·  Shift+拖动选取复制  ·  /help 命令  ·  Ctrl+C 退出")
        self._refresh_side_panel()

    def action_clear_screen(self) -> None:
        if self.has_class("conversation-mode"):
            self.query_one(ConversationLog).clear()

    def action_toggle_command_palette(self) -> None:
        """Ctrl+P 弹出/收起命令面板（占位 UI，列表项暂不接实际执行）。"""
        if isinstance(self.screen, CommandPalette):
            self.pop_screen()
        else:
            self.push_screen(CommandPalette())

    def _focus_conv_input(self) -> None:
        """聚焦对话输入框（切换布局/完成一轮后调用，确保可继续输入）。"""
        try:
            if self.has_class("conversation-mode"):
                self.query_one("#conv-input", Input).focus()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        if not text:
            return

        # 首次输入：从欢迎态切换到对话态
        if self._first_input:
            self._first_input = False
            self.remove_class("welcome-mode")
            self.add_class("conversation-mode")
            self.query_one("#input-info", Static).update(self._input_info())
            self.query_one(StatusBar).update_state(self.cli_state)
            self._refresh_side_panel()
            # display 从 none 切到 block 后需等刷新完成再聚焦，否则焦点丢失
            self.call_after_refresh(self._focus_conv_input)

        # / 命令
        if text.startswith("/"):
            self._handle_command(text)
            return

        # 意图识别
        from poirot.backend.agents.intent import default_intent_tree
        intent_tree = default_intent_tree(report_handler=self._handle_report_intent)
        if intent_tree.detect_and_dispatch(text, self.runtime):
            return

        # 研究流
        self._run_research(text)

    def _handle_command(self, cmd: str) -> None:
        """处理 / 命令。"""
        from rich.console import Console
        from io import StringIO

        buf = StringIO()
        temp_console = Console(file=buf, force_terminal=False, width=100)
        conv = self.query_one(ConversationLog)

        class _MockRenderer:
            state = conv.state
            def expand_last_round(self):
                conv.expand_last_round()
            def _stop_spinner(self):
                pass

        should_exit = handle_command(
            cmd, temp_console, _MockRenderer(), self.cli_state, self.runtime,
        )

        output = buf.getvalue().strip()
        if output:
            from rich.text import Text
            conv.write(Text(output))

        if should_exit:
            self.exit()

        pending = self.cli_state.get("pending_expert_mode")
        if pending is not None:
            self.runtime = self.runtime.switch_expert_mode(expert_mode=pending)
            self.cli_state["pending_expert_mode"] = None
            self.cli_state["mode"] = "expert" if pending else "default"
            self.cli_state["model"] = self._resolve_model_name()
            self.query_one("#input-info", Static).update(self._input_info())
            self.query_one(StatusBar).update_state(self.cli_state)
            self._refresh_side_panel()

        pending_report = self.cli_state.get("pending_report")
        if pending_report is not None:
            self.cli_state["pending_report"] = None
            self._trigger_report(pending_report)

    def _handle_report_intent(self, intent: Any, rt: Any) -> bool:
        self.cli_state["pending_report"] = ""
        return True

    def _trigger_report(self, topic: str) -> None:
        conv = self.query_one(ConversationLog)
        from rich.text import Text
        conv.write(Text(f"Generating report{' on: ' + topic if topic else ''}...", style="cyan"))
        try:
            self.runtime.generate_report(topic=topic or None)
            conv.write(Text("Report generated.", style="green"))
        except Exception as exc:
            conv.write(Text(f"Report failed: {exc}", style="red"))

    @work(exclusive=True, group="research")
    async def _run_research(self, question: str) -> None:
        """流式研究——PoirotStreamClient → ConversationLog + StatusBar + SidePanel。"""
        conv = self.query_one(ConversationLog)
        status = self.query_one(StatusBar)

        conv.render_user_input(question)
        conv.state["round_t0"] = time.monotonic()
        conv.state["model"] = self.cli_state["model"]

        self.cli_state["_running"] = True
        status.update_state(self.cli_state)

        try:
            ctx = self.runtime.run_manager.create_run(
                thread_id=self.runtime.thread_id,
                user_id="default-user",
                run_id=None,
                model_name=self.runtime.researcher_model_name,
                thread_dir=self.runtime.thread_dir,
            )
            self.runtime.run_manager.mark_running(ctx.run_id)
            config = self._build_stream_config(ctx)
            client = PoirotStreamClient(graph=self.runtime.leader_agent.graph, config=config)

            async for event in client.stream(question):
                budget = event.get("budget")
                if budget:
                    self.cli_state["current_tokens"] = budget.get("total", 0)
                    win = budget.get("window") or self.cli_state["current_window"]
                    self.cli_state["current_window"] = win
                    frac = budget.get("fraction")
                    if not frac and win:
                        frac = self.cli_state["current_tokens"] / win
                    self.cli_state["current_fraction"] = frac or 0.0
                    status.update_state(self.cli_state)
                    self._refresh_side_panel()
                conv.render_event(event)

            self.runtime.run_manager.mark_success(ctx.run_id)

        except Exception as exc:
            from rich.text import Text
            conv.write(Text(f"✗ {exc}", style=theme.ACCENT_WARN))
            try:
                self.runtime.run_manager.mark_failed(ctx.run_id, str(exc))
            except Exception:
                pass
        finally:
            self.cli_state["_running"] = False
            status.update_state(self.cli_state)
            self._refresh_side_panel()
            # 每轮结束后重新聚焦输入框，保证用户可继续输入
            self._focus_conv_input()

    def _build_stream_config(self, ctx: Any) -> dict:
        from poirot.backend.app.cli.main import _build_stream_config
        return _build_stream_config(self.runtime, ctx)
