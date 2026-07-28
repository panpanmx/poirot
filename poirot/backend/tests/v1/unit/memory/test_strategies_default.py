from __future__ import annotations

from pathlib import Path

import pytest

from poirot.backend.agents.memory.strategies.default._constants import (
    DECAY_COEFFICIENTS,
    DECAY_PARAMS,
    RETRIEVAL_WEIGHTS,
)
from poirot.backend.agents.memory.strategies.default.strategy import build_default_provider


class TestBuildDefaultProvider:
    def test_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="Layer 2/3 placeholder"):
            build_default_provider()

    def test_raises_with_args(self) -> None:
        with pytest.raises(NotImplementedError):
            build_default_provider("arg", kwarg="val")

    def test_error_message_mentions_layer_2_3(self) -> None:
        try:
            build_default_provider()
        except NotImplementedError as exc:
            assert "Layer 2/3" in str(exc)


class TestDecayParams:
    def test_has_three_types(self) -> None:
        assert "episodic" in DECAY_PARAMS
        assert "semantic" in DECAY_PARAMS
        assert "procedural" in DECAY_PARAMS

    def test_episodic_values(self) -> None:
        assert DECAY_PARAMS["episodic"] == {"base_strength": 0.7, "decay_rate": 0.1}

    def test_semantic_values(self) -> None:
        assert DECAY_PARAMS["semantic"] == {"base_strength": 0.8, "decay_rate": 0.02}

    def test_procedural_values(self) -> None:
        assert DECAY_PARAMS["procedural"] == {"base_strength": 0.9, "decay_rate": 0.005}


class TestRetrievalWeights:
    def test_similarity_0_7(self) -> None:
        assert RETRIEVAL_WEIGHTS["similarity"] == 0.7

    def test_strength_0_3(self) -> None:
        assert RETRIEVAL_WEIGHTS["strength"] == 0.3

    def test_weights_sum_to_one(self) -> None:
        assert RETRIEVAL_WEIGHTS["similarity"] + RETRIEVAL_WEIGHTS["strength"] == pytest.approx(1.0)


class TestDecayCoefficients:
    def test_access_boost_0_1(self) -> None:
        assert DECAY_COEFFICIENTS["access_boost"] == 0.1

    def test_importance_boost_0_05(self) -> None:
        assert DECAY_COEFFICIENTS["importance_boost"] == 0.05


class TestDirectoryStructureIsomorphic:
    """与 agents/context_engineering/strategies/default/ 同构（48 §2.2）。"""

    def _memory_default_dir(self) -> Path:
        return Path(__file__).resolve().parents[4] / "agents" / "memory" / "strategies" / "default"

    def _context_eng_default_dir(self) -> Path:
        return Path(__file__).resolve().parents[4] / "agents" / "context_engineering" / "strategies" / "default"

    def test_has_strategy_py(self) -> None:
        assert (self._memory_default_dir() / "strategy.py").exists()

    def test_has_constants_py(self) -> None:
        assert (self._memory_default_dir() / "_constants.py").exists()

    def test_has_init_py(self) -> None:
        assert (self._memory_default_dir() / "__init__.py").exists()

    def test_same_structure_as_context_engineering(self) -> None:
        """context_engineering/strategies/default/ 也有 strategy.py + _constants.py + __init__.py。"""
        ce_dir = self._context_eng_default_dir()
        assert (ce_dir / "strategy.py").exists()
        assert (ce_dir / "_constants.py").exists()
        assert (ce_dir / "__init__.py").exists()
