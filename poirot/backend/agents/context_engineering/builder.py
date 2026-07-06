"""治理 middleware 装配构建器。

組裝公共 3 固定（DateInjector/MessageNormalizer/BudgetHardStop）+ 1 StrategyMiddleware
（持 config 選定的策略 bundle）。策略 bundle 未註冊時跳過 StrategyMiddleware + 警告
（過渡期 minimal 等非 bundle 名只掛公共3，不崩）。

掛載順序：公共 DateInjector → 公共 MessageNormalizer → 公共 BudgetHardStop →
StrategyMiddleware（策略 bundle 6 hook）。
"""

from __future__ import annotations

import logging

from poirot.backend.agents.config.schema import ContextGovernanceConfig
from poirot.backend.agents.context_engineering.registry import get_strategy_class
from poirot.backend.agents.context_engineering.strategy_middleware import StrategyMiddleware
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


def build_governance_middlewares(config: ContextGovernanceConfig) -> list:
    """組裝公共 3 固定 + 1 StrategyMiddleware（按 config.strategy 選 bundle，未註冊跳過）。"""
    middlewares: list = [
        DateInjectorMiddleware(),
        MessageNormalizerMiddleware(),
        BudgetHardStopMiddleware(),
    ]
    try:
        bundle_cls = get_strategy_class(config.strategy)
    except KeyError:
        logger.warning(
            "strategy bundle '%s' not registered, skip StrategyMiddleware (public 3 only)",
            config.strategy,
        )
        return middlewares
    bundle = bundle_cls()
    middlewares.append(StrategyMiddleware(bundle, config.params))
    return middlewares
