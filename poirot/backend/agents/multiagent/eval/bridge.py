"""L3 EvalBridge Protocol — L2 调 L3 的唯一入口契约（L3 自建，不共享 skill）.

设计（43 文档 §4.1 + §11.1 L3-2.5 + spec.md EvalBridge Requirement）:
- runtime_checkable Protocol（Poirot 既有 pattern，与 L2 MetricsView/EvolutionArtifact 一致）
- 不共享 skill EvalBridge（skill 用 SkillRecord 专属类型不能跨模块共享，L3-2.5 决策 c）
- OrchestrationBridge + MultiagentProgrammaticFacade 实现此 Protocol
- evaluate(ctx) → EvalResult 同步调用（与 L1 D10 sync only 一致，L3-2.3 决策 a）
- fail-closed（异常返 EvalResult(success=False)，不抛异常，L3-2.4 决策 a）
- list_available_methods() 返已注册 adapter 方法名 tuple
- health_check() 返 registry 非空时 True
- 复用 L2 自建 EvalResult（import from evolution/promotion_gate.py）
"""


from typing import Protocol, runtime_checkable

from poirot.backend.agents.multiagent.eval.types import EvalContext
from poirot.backend.agents.multiagent.evolution.promotion_gate import EvalResult


@runtime_checkable
class EvalBridge(Protocol):
    """L3 EvalBridge Protocol（L3 自建，不共享 skill EvalBridge）.

    skill EvalBridge 用 SkillRecord 专属类型不能跨模块共享（L3-2.5 决策 c）.
    OrchestrationBridge（L3 启用时）+ MultiagentProgrammaticFacade（L3 未启用时）实现此 Protocol.
    L2 PromotionGate.bridge 参数类型即此 Protocol.
    """

    def evaluate(self, ctx: EvalContext) -> EvalResult:
        """同步阻塞调用（与 L1 D10 sync only 一致）.

        fail-closed: 异常时返 EvalResult(success=False, failure_reason=...)，不抛异常.
        """
        ...

    def list_available_methods(self) -> tuple[str, ...]:
        """返已注册 EvalAdapter 方法名 tuple（如 ('programmatic', 'llm_judge', 'longitudinal_pairs')）."""
        ...

    def health_check(self) -> bool:
        """registry 非空时 True（至少 1 个 adapter 注册）."""
        ...
