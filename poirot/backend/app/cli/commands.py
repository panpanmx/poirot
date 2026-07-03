"""commands — CLI 命令系统（/help /clear /mode /exit /expand /thinking /tools /model /thread）。

命令以 / 开头，handle_command 分发。返回 True 表示退出 CLI，False 继续循环。
"""

from __future__ import annotations

from typing import Any

from rich.console import Console

from poirot.backend.app.cli.stream_handler import StreamRenderer


def handle_command(
    cmd: str,
    console: Console,
    renderer: StreamRenderer,
    state: dict[str, Any],
    runtime: Any,
) -> bool:
    """处理 / 命令。返回 True=退出 CLI，False=继续。"""
    parts = cmd.strip().split(maxsplit=1)
    name = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    handlers = {
        "/help": lambda: _cmd_help(console),
        "/clear": lambda: _cmd_clear(console),
        "/expert": lambda: _cmd_expert(console, state),
        "/default": lambda: _cmd_default(console, state),
        "/report": lambda: _cmd_report(arg, console, state),
        "/exit": lambda: True,
        "/quit": lambda: True,
        "/expand": lambda: _cmd_expand(renderer),
        "/thinking": lambda: _cmd_thinking(arg, console, renderer),
        "/tools": lambda: _cmd_tools(console, runtime),
        "/model": lambda: _cmd_model(console, runtime),
        "/thread": lambda: _cmd_thread(console, runtime),
        "/prompt": lambda: _cmd_prompt(arg, console),
    }

    handler = handlers.get(name)
    if handler is None:
        console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
        return False

    result = handler()
    return result if isinstance(result, bool) else False


def _cmd_help(console: Console) -> None:
    console.print("[bold]Available commands:[/bold]")
    console.print("  [cyan]/help[/cyan]     Show this help")
    console.print("  [cyan]/clear[/cyan]    Clear screen")
    console.print("  [cyan]/expert[/cyan]    Switch to expert mode (deep research), applies next round")
    console.print("  [cyan]/default[/cyan]   Switch to default mode (lightweight chat), applies next round")
    console.print("  [cyan]/report[/cyan]    Generate report from current thread (default mode); optional topic")
    console.print("  [cyan]/expand[/cyan]   Expand last round tool results")
    console.print("  [cyan]/thinking[/cyan] Toggle thinking display (on|off)")
    console.print("  [cyan]/tools[/cyan]    List available tools")
    console.print("  [cyan]/model[/cyan]    Show current model routing chain")
    console.print("  [cyan]/thread[/cyan]   Show thread info")
    console.print("  [cyan]/prompt[/cyan]   Prompt management (list|show <cat/name>|reload)")
    console.print("  [cyan]/exit[/cyan]     Exit (also /quit)")


def _cmd_clear(console: Console) -> None:
    console.clear()


def _cmd_expert(console: Console, state: dict[str, Any]) -> None:
    state["pending_expert_mode"] = True
    console.print("[green]Mode will switch to expert next round[/green]")


def _cmd_default(console: Console, state: dict[str, Any]) -> None:
    state["pending_expert_mode"] = False
    console.print("[green]Mode will switch to default next round[/green]")


def _cmd_report(arg: str, console: Console, state: dict[str, Any]) -> None:
    """标记 pending_report，主循环检测后调 _trigger_report（避免 commands.py 依赖 main.py）。

    空字符串 "" 表"pending 无 topic"，None 表"未设 pending"——区分避免 sentinel 冲突。
    """
    state["pending_report"] = arg.strip()


def _cmd_expand(renderer: StreamRenderer) -> None:
    renderer.expand_last_round()


def _cmd_thinking(arg: str, console: Console, renderer: StreamRenderer) -> None:
    if arg == "off":
        renderer.state["thinking_enabled"] = False
        console.print("[green]Thinking display off[/green]")
    elif arg == "on":
        renderer.state["thinking_enabled"] = True
        console.print("[green]Thinking display on[/green]")
    else:
        current = "on" if renderer.state["thinking_enabled"] else "off"
        console.print(f"[yellow]Usage: /thinking on|off (current: {current})[/yellow]")


def _cmd_tools(console: Console, runtime: Any) -> None:
    try:
        from poirot.backend.agents.agent_tools.available import get_available_tools
        tools = get_available_tools(include_mcp=True)
        console.print("[bold]Available tools:[/bold]")
        for t in tools:
            console.print(f"  [cyan]{t.name}[/cyan]")
    except Exception as exc:
        console.print(f"[red]Failed to list tools: {exc}[/red]")


def _cmd_model(console: Console, runtime: Any) -> None:
    try:
        from poirot.backend.agents.leader.agent import _resolve_actual_model_name
        name = _resolve_actual_model_name(runtime.capability_registry)
        console.print(f"[bold]Model routing:[/bold] [cyan]{name}[/cyan]")
    except Exception as exc:
        console.print(f"[red]Failed to get model info: {exc}[/red]")


def _cmd_thread(console: Console, runtime: Any) -> None:
    console.print(f"[bold]Thread ID:[/bold] [cyan]{runtime.thread_id}[/cyan]")
    console.print(f"[bold]Thread dir:[/bold] [dim]{runtime.thread_dir}[/dim]")
    try:
        import json
        events_path = runtime.thread_journal.events_path
        if events_path.exists():
            lines = events_path.read_text(encoding="utf-8").strip().split("\n\n")
            runs = []
            for block in lines[-10:]:
                if block.strip():
                    try:
                        evt = json.loads(block.split("\n")[0] if "\n" in block else block)
                        if evt.get("event_type") == "run.started":
                            runs.append(evt.get("run_id", "?"))
                    except Exception:
                        pass
            if runs:
                console.print("[bold]Recent runs:[/bold]")
                for rid in runs[-5:]:
                    console.print(f"  [dim]{rid}[/dim]")
    except Exception:
        pass


def _cmd_prompt(arg: str, console: Console) -> None:
    """Prompt 管理命令：/prompt list | /prompt show <cat/name> | /prompt reload"""
    from poirot.backend.agents.prompts import get_prompt_manager

    pm = get_prompt_manager()
    if not arg or arg == "list":
        prompts = pm.list_prompts()
        if not prompts:
            console.print("[dim]No prompts found[/dim]")
            return
        console.print("[bold]Available prompts:[/bold]")
        for p in prompts:
            text, source = pm.load_raw(p.split("/")[0], p.split("/")[1])
            tag = "[green](user)[/green]" if source == "user" else "[dim](system)[/dim]"
            console.print(f"  [cyan]{p}[/cyan] {tag}")
        return

    parts = arg.split(maxsplit=1)
    if parts[0] == "show" and len(parts) > 1:
        ref = parts[1].strip()
        if "/" not in ref:
            console.print("[yellow]Usage: /prompt show <category/name>[/yellow]")
            return
        cat, name = ref.split("/", 1)
        try:
            text, source = pm.load_raw(cat, name)
            tag = f"[green][{source}][/green]" if source == "user" else f"[dim][{source}][/dim]"
            console.print(f"{tag} [cyan]{cat}/{name}[/cyan]:")
            console.print(text)
        except FileNotFoundError:
            console.print(f"[red]Prompt not found: {ref}[/red]")
        return

    if parts[0] == "reload":
        pm.clear_cache()
        console.print("[green]Prompt cache cleared — next load reads from .md files[/green]")
        return

    console.print("[yellow]Usage: /prompt list | /prompt show <cat/name> | /prompt reload[/yellow]")
