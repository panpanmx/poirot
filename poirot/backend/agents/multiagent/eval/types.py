"""L3 eval 类型层 — EvalContext（L3 自建，L2 无此类型）.

设计（43 文档 §4.1 + spec.md EvalContext Requirement）:
- EvalContext: L2 调 L3 evaluate 时传的上下文（candidate/baseline/task_sample/eval_method_hint/profile/metadata）
- 复用 L2 自建 EvalTask / EvalResult（import from evolution/promotion_gate.py，不 import skill）
- EvolutionArtifact 复用 L2 Protocol（from evolution/types.py）
- frozen dataclass 不可变（Poirot 值对象原则）
- metadata 用 field(default_factory=dict) 避免 mutable default 共享
"""


from dataclasses import dataclass, field
from typing import Any

from poirot.backend.agents.multiagent.evolution.promotion_gate import EvalTask
from poirot.backend.agents.multiagent.evolution.types import EvolutionArtifact


@dataclass(frozen=True)
class EvalContext:
    """L2 调 L3 evaluate 时传的上下文（L3 自建，L2 无此类型）.

    candidate/baseline: L2 演化产物（EvolutionArtifact Protocol）.
    task_sample: L2 抽样的历史 specialist 调用记录（EvalTask tuple）.
    eval_method_hint: L2 建议的评估方法（非强制，Bridge 可覆盖）.
    profile: specialist profile 名（如 "codex"/"claude"）.
    metadata: 扩展字段（如 task_type="open_ended" 触发 llm_judge）.
    """

    candidate: EvolutionArtifact
    baseline: EvolutionArtifact
    task_sample: tuple[EvalTask, ...]
    eval_method_hint: str | None = None
    profile: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
