"""commands — CLI 命令系统（/help /clear /expert /default /report /exit /expand /thinking /tools /model /thread /prompt）。

命令以 / 开头，``handle_command`` 从 ``CommandRegistry`` 查 handler 分发。
返回 True 表示退出 CLI，False 继续循环。

``_cmd_help`` 文案与 ``/`` 补全菜单的 ``display_meta`` 共用同一份 ``CommandSpec.description``，
避免两处维护。``CommandRegistry.register_skill()`` 预留接口见 ``registry.py``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rich.console import Console

from poirot.backend.app.cli.registry import CommandRegistry, CommandSpec
from poirot.backend.app.cli.stream_handler import StreamRenderer


@dataclass
class CommandContext:
    """单次命令调用的上下文——统一 ``_cmd_*`` 函数签名，让 ``handle_command`` 能通过 registry 泛化分发。"""

    console: Console
    renderer: StreamRenderer
    state: dict[str, Any]
    runtime: Any
    arg: str


# ---- handler 函数（签名统一为 ctx → bool | None） ----


def _cmd_help(ctx: CommandContext) -> None:
    ctx.console.print("[bold]Available commands:[/bold]")
    for spec in _registry.list_all():
        ctx.console.print(f"  [cyan]{spec.name}[/cyan]     {spec.description}")


def _cmd_clear(ctx: CommandContext) -> None:
    ctx.console.clear()


def _cmd_expert(ctx: CommandContext) -> None:
    ctx.state["pending_expert_mode"] = True
    ctx.console.print("[green]Mode will switch to expert next round[/green]")


def _cmd_default(ctx: CommandContext) -> None:
    ctx.state["pending_expert_mode"] = False
    ctx.console.print("[green]Mode will switch to default next round[/green]")


def _cmd_report(ctx: CommandContext) -> None:
    """标记 pending_report，主循环检测后调 _trigger_report（避免 commands.py 依赖 main.py）。

    空字符串 "" 表"pending 无 topic"，None 表"未设 pending"——区分避免 sentinel 冲突。
    """
    ctx.state["pending_report"] = ctx.arg.strip()


def _cmd_exit(ctx: CommandContext) -> bool:
    return True


def _cmd_expand(ctx: CommandContext) -> None:
    ctx.renderer.expand_last_round()


def _cmd_thinking(ctx: CommandContext) -> None:
    # 语义：toggle Thought 折叠行（非逐 token 流）——与 stream_handler._render_thinking 联动
    if ctx.arg == "off":
        ctx.renderer.state["thinking_enabled"] = False
        ctx.console.print("[green]Thinking display off[/green]")
    elif ctx.arg == "on":
        ctx.renderer.state["thinking_enabled"] = True
        ctx.console.print("[green]Thinking display on[/green]")
    else:
        current = "on" if ctx.renderer.state["thinking_enabled"] else "off"
        ctx.console.print(f"[yellow]Usage: /thinking on|off (current: {current})[/yellow]")


def _cmd_tools(ctx: CommandContext) -> None:
    try:
        from poirot.backend.agents.agent_tools.available import get_available_tools
        tools = get_available_tools(include_mcp=True)
        ctx.console.print("[bold]Available tools:[/bold]")
        for t in tools:
            ctx.console.print(f"  [cyan]{t.name}[/cyan]")
    except Exception as exc:
        ctx.console.print(f"[red]Failed to list tools: {exc}[/red]")


def _cmd_model(ctx: CommandContext) -> None:
    try:
        from poirot.backend.agents.leader.agent import _resolve_actual_model_name
        name = _resolve_actual_model_name(ctx.runtime.capability_registry)
        ctx.console.print(f"[bold]Model routing:[/bold] [cyan]{name}[/cyan]")
    except Exception as exc:
        ctx.console.print(f"[red]Failed to get model info: {exc}[/red]")


def _cmd_thread(ctx: CommandContext) -> None:
    ctx.console.print(f"[bold]Thread ID:[/bold] [cyan]{ctx.runtime.thread_id}[/cyan]")
    ctx.console.print(f"[bold]Thread dir:[/bold] [dim]{ctx.runtime.thread_dir}[/dim]")
    try:
        import json
        events_path = ctx.runtime.thread_journal.events_path
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
                ctx.console.print("[bold]Recent runs:[/bold]")
                for rid in runs[-5:]:
                    ctx.console.print(f"  [dim]{rid}[/dim]")
    except Exception:
        pass


def _cmd_prompt(ctx: CommandContext) -> None:
    """Prompt 管理命令：/prompt list | /prompt show <cat/name> | /prompt reload"""
    from poirot.backend.agents.prompts import get_prompt_manager

    pm = get_prompt_manager()
    arg = ctx.arg
    if not arg or arg == "list":
        prompts = pm.list_prompts()
        if not prompts:
            ctx.console.print("[dim]No prompts found[/dim]")
            return
        ctx.console.print("[bold]Available prompts:[/bold]")
        for p in prompts:
            text, source = pm.load_raw(p.split("/")[0], p.split("/")[1])
            tag = "[green](user)[/green]" if source == "user" else "[dim](system)[/dim]"
            ctx.console.print(f"  [cyan]{p}[/cyan] {tag}")
        return

    parts = arg.split(maxsplit=1)
    if parts[0] == "show" and len(parts) > 1:
        ref = parts[1].strip()
        if "/" not in ref:
            ctx.console.print("[yellow]Usage: /prompt show <category/name>[/yellow]")
            return
        cat, name = ref.split("/", 1)
        try:
            text, source = pm.load_raw(cat, name)
            tag = f"[green][{source}][/green]" if source == "user" else f"[dim][{source}][/dim]"
            ctx.console.print(f"{tag} [cyan]{cat}/{name}[/cyan]:")
            ctx.console.print(text)
        except FileNotFoundError:
            ctx.console.print(f"[red]Prompt not found: {ref}[/red]")
        return

    if parts[0] == "reload":
        pm.clear_cache()
        ctx.console.print("[green]Prompt cache cleared — next load reads from .md files[/green]")
        return

    ctx.console.print("[yellow]Usage: /prompt list | /prompt show <cat/name> | /prompt reload[/yellow]")


def _cmd_skill(ctx: CommandContext) -> None:
    """Skill 激活命令：/skill <name> | /skill off | /skill list。

    持久 override（每轮生效，直到 /skill off）。设 cli_state["skill_override"]，
    主循环注入 config["configurable"]["skill_override"]，SkillInjectionMiddleware 读取。
    """
    arg = ctx.arg.strip()
    if arg == "list":
        mgr = getattr(ctx.runtime, "skill_manager", None)
        if mgr is None:
            ctx.console.print("[dim]Skill module not enabled[/dim]")
            return
        skills = mgr.list_skills()
        if not skills:
            ctx.console.print("[dim]No skills registered[/dim]")
            return
        ctx.console.print("[bold]Active skills:[/bold]")
        for s in skills:
            tools = ",".join(s["allowed_tools"]) if s["allowed_tools"] else "-"
            ctx.console.print(
                f"  [cyan]{s['name']}[/cyan] eff={s['effective_rate']:.0%} "
                f"sel={s['total_selections']} tools={tools}"
            )
        return
    if arg == "off":
        ctx.state["skill_override"] = []
        ctx.console.print("[green]Skill override cleared[/green]")
        return
    if not arg:
        cur = ctx.state.get("skill_override") or []
        cur_label = ",".join(cur) if cur else "(none)"
        ctx.console.print(
            f"[yellow]Usage: /skill <name> | /skill off | /skill list"
            f"  (current: {cur_label})[/yellow]"
        )
        return
    ctx.state["skill_override"] = [arg]
    ctx.console.print(f"[green]Skill '{arg}' activated[/green]")


# ---- 模块级 registry：注册全部 builtin 命令 ----

_registry = CommandRegistry()
_registry.register(CommandSpec("/help", "Show this help", _cmd_help))
_registry.register(CommandSpec("/clear", "Clear screen", _cmd_clear))
_registry.register(CommandSpec("/expert", "Switch to expert mode (deep research), applies next round", _cmd_expert))
_registry.register(CommandSpec("/default", "Switch to default mode (lightweight chat), applies next round", _cmd_default))
_registry.register(CommandSpec("/report", "Generate report from current thread; optional topic", _cmd_report))
_registry.register(CommandSpec("/exit", "Exit (also /quit)", _cmd_exit))
_registry.register(CommandSpec("/quit", "Exit (alias of /exit)", _cmd_exit))
_registry.register(CommandSpec("/expand", "Expand last round tool results and Thought", _cmd_expand))
_registry.register(CommandSpec("/thinking", "Toggle Thought fold row display (on|off)", _cmd_thinking))
_registry.register(CommandSpec("/tools", "List available tools", _cmd_tools))
_registry.register(CommandSpec("/model", "Show current model routing chain", _cmd_model))
_registry.register(CommandSpec("/thread", "Show thread info", _cmd_thread))
_registry.register(CommandSpec("/prompt", "Prompt management (list|show <cat/name>|reload)", _cmd_prompt))
_registry.register(CommandSpec("/skill", "Skill activation (list|<name>|off)", _cmd_skill))


def get_registry() -> CommandRegistry:
    """供 ``main.py`` 构造 ``SlashCommandCompleter`` 时获取注册表实例。"""
    return _registry


def handle_command(
    cmd: str,
    console: Console,
    renderer: StreamRenderer,
    state: dict[str, Any],
    runtime: Any,
) -> bool:
    """处理 / 命令。返回 True=退出 CLI，False=继续。

    从 ``CommandRegistry.get(name)`` 查 handler，构造 ``CommandContext`` 后调用。
    未命中时打印 ``Unknown command`` 并返回 False。
    """
    parts = cmd.strip().split(maxsplit=1)
    name = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    spec = _registry.get(name)
    if spec is None:
        console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
        return False

    ctx = CommandContext(console=console, renderer=renderer, state=state, runtime=runtime, arg=arg)
    result = spec.handler(ctx)
    return result if isinstance(result, bool) else False
