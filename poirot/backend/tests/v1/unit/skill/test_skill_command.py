"""B11 /skill 命令单测 — 激活/清除/list/usage + handle_command 分发。"""
from __future__ import annotations

from io import StringIO

from rich.console import Console

from poirot.backend.app.cli.commands import CommandContext, _cmd_skill, handle_command


def _ctx(state: dict, arg: str, runtime=None) -> CommandContext:
    return CommandContext(
        console=Console(file=StringIO(), force_terminal=False),
        renderer=None,
        state=state,
        runtime=runtime,
        arg=arg,
    )


def test_skill_activate_sets_override():
    state: dict = {}
    _cmd_skill(_ctx(state, "source-verification"))
    assert state["skill_override"] == ["source-verification"]


def test_skill_off_clears_override():
    state = {"skill_override": ["source-verification"]}
    _cmd_skill(_ctx(state, "off"))
    assert state["skill_override"] == []


def test_skill_no_arg_shows_usage_no_crash():
    state = {"skill_override": ["x"]}
    _cmd_skill(_ctx(state, ""))  # 不抛，打印 usage + current


def test_skill_list_no_manager_no_crash():
    state: dict = {}
    rt = type("R", (), {"skill_manager": None})()
    _cmd_skill(_ctx(state, "list", runtime=rt))  # 打印 "not enabled"


def test_skill_list_with_manager_shows_skills():
    state: dict = {}
    mgr = type("M", (), {
        "list_skills": lambda self: [{
            "name": "source-verification",
            "effective_rate": 0.5,
            "total_selections": 4,
            "allowed_tools": ["web_search", "browse_page"],
        }],
    })()
    rt = type("R", (), {"skill_manager": mgr})()
    _cmd_skill(_ctx(state, "list", runtime=rt))  # 打印 skill，不抛


def test_handle_command_dispatches_skill_activate():
    state: dict = {}
    console = Console(file=StringIO(), force_terminal=False)
    handle_command("/skill my-skill", console, None, state, None)
    assert state["skill_override"] == ["my-skill"]


def test_handle_command_dispatches_skill_off():
    state = {"skill_override": ["x"]}
    console = Console(file=StringIO(), force_terminal=False)
    handle_command("/skill off", console, None, state, None)
    assert state["skill_override"] == []


def test_skill_override_persists_across_activations():
    state: dict = {}
    _cmd_skill(_ctx(state, "a"))
    assert state["skill_override"] == ["a"]
    _cmd_skill(_ctx(state, "b"))  # 覆盖前一个
    assert state["skill_override"] == ["b"]
