from __future__ import annotations

from typing import Any

from poirot.backend.agents.prompts import get_prompt_manager


def apply_prompt_template(expert_mode: bool = False, **context: Any) -> str:
    """Render the system prompt based on expert_mode flag.

    mode 枚举废弃后改为 expert_mode: bool 参数化：
    - default (expert_mode=False): identity + constraints + decision_guidance
    - expert  (expert_mode=True):  identity + constraints + decision_guidance + mode_expert

    从 PromptManager 加载各段 .md 文件拼装。

    Sections (in order):
    - <identity>            : agent role and capabilities
    - <constraints>         : language, content, format, scope rules
    - <decision_guidance>   : default 模式引导模型自判深度
    - <mode_expert>         : expert 模式追加深度研究策略（仅 expert_mode=True）
    """
    pm = get_prompt_manager()
    parts = [
        pm.load("leader", "identity"),
        pm.load("leader", "constraints"),
        pm.load("leader", "decision_guidance"),
    ]
    if expert_mode:
        parts.append(pm.load("leader", "mode_expert"))
    return "\n\n".join(parts)
