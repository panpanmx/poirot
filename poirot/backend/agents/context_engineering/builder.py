"""治理 middleware 装配构建器。

按 config ``context_governance.strategy`` 查 StrategyDef，经 registry 实例化策略
impl（未注册回退 NoopCapability + 警告），组装公共 3 固定 + 策略 5 middleware。

挂载顺序（factory 文档化）：
公共 DateInjector → 公共 MessageNormalizer → 公共 BudgetHardStop →
策略 Compressor → 策略 Externalizer → 策略 ToolSchemaFilter →
策略 MemoryInjector → 策略 BudgetGuard。
"""

from __future__ import annotations

import logging
from typing import Any

from poirot.backend.agents.config.schema import ContextGovernanceConfig
from poirot.backend.agents.context_engineering.capabilities.noop import NoopCapability
from poirot.backend.agents.context_engineering.middlewares.budget_guard_middleware import (
    BudgetGuardMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.compressor_middleware import (
    CompressorMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.externalizer_middleware import (
    ExternalizerMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.memory_injector_middleware import (
    MemoryInjectorMiddleware,
)
from poirot.backend.agents.context_engineering.middlewares.tool_schema_filter_middleware import (
    ToolSchemaFilterMiddleware,
)
from poirot.backend.agents.context_engineering.registry import get_capability_impl
from poirot.backend.agents.context_engineering.strategy import get_strategy
from poirot.backend.agents.middlewares.budget_hard_stop_middleware import (
    BudgetHardStopMiddleware,
)
from poirot.backend.agents.middlewares.date_injector_middleware import (
    DateInjectorMiddleware,
)
from poirot.backend.agents.middlewares.message_normalizer_middleware import (
    MessageNormalizerMiddleware,
)

logger = logging.getLogger(__name__)


def _resolve_impl(name: str) -> Any:
    """按注册名实例化策略能力 impl，未注册回退 NoopCapability + 警告。"""
    if name == "noop":
        return NoopCapability()
    try:
        cls = get_capability_impl(name)
    except KeyError:
        logger.warning(
            "capability impl '%s' not registered, fallback NoopCapability", name
        )
        return NoopCapability()
    return cls()


def build_governance_middlewares(config: ContextGovernanceConfig) -> list:
    """组装公共 3 固定 + 策略 5 middleware（按 strategy 查表 + noop 回退）。"""
    strat = get_strategy(config.strategy)
    params = config.params or {}
    return [
        DateInjectorMiddleware(),
        MessageNormalizerMiddleware(),
        BudgetHardStopMiddleware(),
        CompressorMiddleware(_resolve_impl(strat.compressor), params),
        ExternalizerMiddleware(_resolve_impl(strat.externalizer), params),
        ToolSchemaFilterMiddleware(_resolve_impl(strat.tool_schema_filter), params),
        MemoryInjectorMiddleware(_resolve_impl(strat.memory_injector), params),
        BudgetGuardMiddleware(_resolve_impl(strat.budget_guard), params),
    ]
