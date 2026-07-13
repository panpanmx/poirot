"""command_completer — ``/`` 命令模糊补全菜单。

消费 ``CommandRegistry.list_all()``，仅在输入以 ``/`` 开头时触发，子串匹配命令名，
产出 ``Completion(text, display_meta=description)``。配合 ``PromptSession(completer=...)``
+ ``complete_while_typing=True`` 实现参考截图里的下拉菜单效果。

选中行/未选中行配色由 ``main.py`` 的 ``PromptSession`` ``Style`` 配置：
``completion-menu.completion.current: bg:#6A5ACD fg:#ffffff``（紫底白字，选中行）。
"""

from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from poirot.backend.app.cli.registry import CommandRegistry


class SlashCommandCompleter(Completer):
    """``/`` 命令补全——仅在 ``word_before_cursor`` 以 ``/`` 开头时触发。

    匹配策略：子串匹配（大小写不敏感）。命令名完整保留 ``/`` 前缀，
    ``start_position`` 设为 ``-len(word_before_cursor)`` 让 prompt_toolkit 替换整个词。
    """

    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    def get_completions(self, document: Document, complete_event):  # type: ignore[no-untyped-def]
        word = document.get_word_before_cursor(WORD=True)

        # 仅在输入以 / 开头时触发补全（普通对话文本不弹菜单）
        if not word.startswith("/"):
            return

        word_lower = word.lower()
        for spec in self._registry.list_all():
            # 子串匹配（大小写不敏感）
            if word_lower in spec.name.lower():
                yield Completion(
                    text=spec.name,
                    start_position=-len(word),
                    display=spec.name,
                    display_meta=spec.description,
                )
