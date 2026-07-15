"""McpPanel — Ctrl+M MCP 管理面板（ModalScreen）。

结构化输入 server 配置（Name/Transport/URL-Command/Args/Headers-Env），
调 McpManager.add_server 加载，成功触发 reload_mcp_tools graph 重建。

INVARIANT:
- Ctrl+M 推面板，Esc/Ctrl+M 关
- 显示已加载 server 列表（list_servers）
- 结构化字段转 McpServerConfig
- URL 格式阻断 + Command 存在仅警告 + Name 重名阻断
- 成功：刷新列表 + 提示 + 触发 reload + dismiss
- 失败：保留输入 + 显示错误（脱敏后）+ 可改重试
"""
from __future__ import annotations

import asyncio
import shlex
import shutil
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from rich.text import Text

from poirot.backend.app.tui import theme
from poirot.backend.agents.mcp import McpManager, McpServerConfig


class McpPanel(ModalScreen[None]):
    """Ctrl+M 弹出的 MCP 管理面板。"""

    BINDINGS = [
        Binding("escape", "dismiss_panel", "Close", show=False),
        Binding("ctrl+m", "dismiss_panel", "Close", show=False),
    ]

    DEFAULT_CSS = f"""
    McpPanel {{
        align: center middle;
        background: $background 0%;
    }}
    McpPanel > #mcp-box {{
        width: 70;
        max-width: 90%;
        height: auto;
        max-height: 85%;
        background: {theme.SURFACE};
        border: solid {theme.BORDER};
        padding: 1 2;
    }}
    McpPanel #mcp-title {{
        height: 1;
        margin: 0 0 1 0;
    }}
    McpPanel #mcp-title-right {{
        width: auto;
        height: 1;
        border: solid {theme.BORDER};
        padding: 0 1;
        color: {theme.TEXT_SECONDARY};
    }}
    McpPanel .mcp-section-title {{
        height: 1;
        color: {theme.ACCENT_BRAND};
        margin: 1 0 0 0;
    }}
    McpPanel .mcp-input-row {{
        height: 1;
        margin: 0 0 0 0;
    }}
    McpPanel .mcp-input-label {{
        width: 16;
        height: 1;
        color: {theme.TEXT_SECONDARY};
        padding: 0 1 0 0;
    }}
    McpPanel .mcp-input-field {{
        height: 1;
        border: none;
        background: {theme.SURFACE_ALT};
        color: {theme.TEXT_PRIMARY};
        padding: 0 1;
    }}
    McpPanel .mcp-input-field:focus {{
        border: none;
        background: {theme.SURFACE_ALT};
    }}
    McpPanel .mcp-status {{
        height: auto;
        color: {theme.TEXT_DIM};
        margin: 1 0 0 0;
    }}
    McpPanel .mcp-server-row {{
        height: 1;
    }}
    McpPanel .mcp-button-row {{
        height: 1;
        margin: 1 0 0 0;
    }}
    """

    def __init__(self, mcp_manager: McpManager | None, runtime: Any = None) -> None:
        super().__init__()
        self._mcp_manager = mcp_manager
        self._runtime = runtime

    def compose(self) -> ComposeResult:
        with Container(id="mcp-box"):
            with Horizontal(id="mcp-title"):
                yield Static("MCP 管理", id="mcp-title-left")
                yield Static("esc", id="mcp-title-right")
            yield Static("已加载 server:", classes="mcp-section-title")
            with Vertical(id="mcp-server-list"):
                pass
            yield Static("添加 server", classes="mcp-section-title")
            with Horizontal(classes="mcp-input-row"):
                yield Static("Name:", classes="mcp-input-label")
                yield Input(placeholder="my_tool", id="mcp-name", classes="mcp-input-field")
            with Horizontal(classes="mcp-input-row"):
                yield Static("Transport:", classes="mcp-input-label")
                yield Input(placeholder="stdio / http / sse", id="mcp-transport", classes="mcp-input-field")
            with Horizontal(classes="mcp-input-row"):
                yield Static("URL/Command:", classes="mcp-input-label")
                yield Input(placeholder="https://... 或 npx", id="mcp-url-cmd", classes="mcp-input-field")
            with Horizontal(classes="mcp-input-row"):
                yield Static("Args (stdio):", classes="mcp-input-label")
                yield Input(placeholder="-y @modelcontextprotocol/server-filesystem", id="mcp-args", classes="mcp-input-field")
            with Horizontal(classes="mcp-input-row"):
                yield Static("Headers/Env:", classes="mcp-input-label")
                yield Input(placeholder="Authorization=Bearer xxx", id="mcp-headers-env", classes="mcp-input-field")
            with Horizontal(classes="mcp-button-row"):
                yield Button("添加", id="mcp-add-btn", variant="primary")
                yield Button("取消", id="mcp-cancel-btn")
            yield Static("状态: 等待输入...", id="mcp-status", classes="mcp-status")

    def on_mount(self) -> None:
        self.query_one("#mcp-title-left", Static).styles.color = theme.TEXT_PRIMARY
        self._refresh_server_list()
        self.query_one("#mcp-name", Input).focus()

    def _refresh_server_list(self) -> None:
        """刷新已加载 server 列表。"""
        try:
            server_list = self.query_one("#mcp-server-list", Vertical)
        except Exception:
            return
        server_list.remove_children()
        if self._mcp_manager is None:
            server_list.mount(Static("MCP 未启用", classes="mcp-server-row"))
            return
        servers = self._mcp_manager.list_servers()
        if not servers:
            server_list.mount(Static("（无）", classes="mcp-server-row"))
            return
        for s in servers:
            mark = "●" if s.get("health_state") == "healthy" else "○"
            text = f"  {mark} {s['name']} ({s['transport']})  {s['tool_count']} tools  {s['health_state']}"
            server_list.mount(Static(text, classes="mcp-server-row"))

    def _set_status(self, msg: str) -> None:
        try:
            self.query_one("#mcp-status", Static).update(msg)
        except Exception:
            pass

    def _parse_headers_env(self, raw: str) -> dict[str, str]:
        """解析 key=val,key=val 格式。"""
        result: dict[str, str] = {}
        if not raw.strip():
            return result
        for pair in raw.split(","):
            pair = pair.strip()
            if "=" not in pair:
                continue
            k, _, v = pair.partition("=")
            result[k.strip()] = v.strip()
        return result

    def _validate_and_build_config(self) -> tuple[McpServerConfig | None, str | None]:
        """校验输入并构建 McpServerConfig。返 (config, error)。"""
        name = self.query_one("#mcp-name", Input).value.strip()
        transport = self.query_one("#mcp-transport", Input).value.strip().lower()
        url_cmd = self.query_one("#mcp-url-cmd", Input).value.strip()
        args_raw = self.query_one("#mcp-args", Input).value.strip()
        headers_env_raw = self.query_one("#mcp-headers-env", Input).value.strip()

        if not name:
            return None, "Name 不能为空"
        if transport not in ("stdio", "http", "sse"):
            return None, "Transport 需为 stdio / http / sse"
        if not url_cmd:
            return None, "URL/Command 不能为空"

        # Name 重名检查
        if self._mcp_manager and name in self._mcp_manager._config.servers:
            return None, f"server 名 '{name}' 已存在，请改名"

        kv = self._parse_headers_env(headers_env_raw)

        if transport == "stdio":
            # Command 存在性仅警告
            if not shutil.which(url_cmd.split()[0] if " " in url_cmd else url_cmd):
                self._set_status(f"⚠️ Command '{url_cmd}' 不在 PATH，可能 WSL 路径下有（允许提交）")
            args = shlex.split(args_raw) if args_raw else []
            return McpServerConfig(
                name=name, transport="stdio",
                command=url_cmd, args=args, env=kv,
            ), None
        else:
            # URL 格式阻断
            if not (url_cmd.startswith("http://") or url_cmd.startswith("https://")):
                return None, "URL 需以 http:// 或 https:// 开头"
            return McpServerConfig(
                name=name, transport=transport,
                url=url_cmd, headers=kv,
            ), None

    async def _do_add(self) -> None:
        """执行 add_server + 反馈。"""
        config, error = self._validate_and_build_config()
        if error:
            self._set_status(f"❌ {error}")
            return

        assert config is not None
        if self._mcp_manager is None:
            self._set_status("❌ MCP 未启用")
            return

        self._set_status("connecting...")
        try:
            success = await self._mcp_manager.add_server(config)
        except Exception as exc:
            self._set_status(f"❌ 加载失败: {exc}")
            return

        if success:
            tool_count = sum(
                1 for e in self._mcp_manager.registry._entries.values()
                if e.server_name == config.name
            )
            self._set_status(f"✅ 加载成功，{tool_count} 个工具可用")
            self._refresh_server_list()
            # 触发 graph 重建
            if self._runtime is not None:
                try:
                    self._runtime = self._runtime.reload_mcp_tools()
                except Exception as exc:
                    self._set_status(f"⚠️ 加载成功但 graph 重建失败: {exc}")
                    return
            # 延迟 dismiss 让用户看到成功提示
            self.set_timer(1.0, lambda: self.dismiss(None))
        else:
            self._set_status("❌ 加载失败（连接超时或错误），可改后重试")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mcp-add-btn":
            asyncio.run(self._do_add())
        elif event.button.id == "mcp-cancel-btn":
            self.dismiss(None)

    def on_click(self, event: events.Click) -> None:
        if event.widget is self:
            self.dismiss(None)

    def action_dismiss_panel(self) -> None:
        self.dismiss(None)
