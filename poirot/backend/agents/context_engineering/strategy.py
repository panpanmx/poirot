"""策略装配定义。

``StrategyDef`` 描述 5 策略 capability 的 impl 注册名选择。``STRATEGIES``
预置名 → StrategyDef 映射。factory 按 config ``context_governance.strategy``
查表，再经 registry 实例化各能力 impl。

S1 骨架仅留 ``minimal``（全 noop）。具体策略由后续设计填入 STRATEGIES。
impl 名（compressor.baseline 等）在 baseline 实现时注册。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyDef:
    """5 策略 capability 的 impl 注册名选择。"""

    name: str
    compressor: str
    externalizer: str
    tool_schema_filter: str
    memory_injector: str
    budget_guard: str


STRATEGIES: dict[str, StrategyDef] = {
    "minimal": StrategyDef(
        name="minimal",
        compressor="noop",
        externalizer="noop",
        tool_schema_filter="noop",
        memory_injector="noop",
        budget_guard="noop",
    ),
}


def get_strategy(name: str) -> StrategyDef:
    """按名查策略定义，未知抛 KeyError。"""
    if name not in STRATEGIES:
        raise KeyError(
            f"unknown context_governance strategy '{name}'. "
            f"available: {sorted(STRATEGIES)}"
        )
    return STRATEGIES[name]

