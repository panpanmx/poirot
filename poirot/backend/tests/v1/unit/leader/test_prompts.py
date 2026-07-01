import pytest

from poirot.backend.agents.leader.prompts import apply_prompt_template


def test_fast_mode_prompt() -> None:
    prompt = apply_prompt_template("fast")
    assert "Poirot" in prompt
    assert "fast" in prompt
    assert "<identity>" in prompt
    assert "<constraints>" in prompt
    assert "<mode" in prompt


def test_general_mode_prompt() -> None:
    prompt = apply_prompt_template("general")
    assert "Poirot" in prompt
    assert "general" in prompt
    assert "<constraints>" in prompt


def test_expert_mode_prompt() -> None:
    prompt = apply_prompt_template("expert")
    assert "Poirot" in prompt
    assert "expert" in prompt
    assert "reflection" in prompt


def test_three_modes_are_distinct() -> None:
    prompts = {mode: apply_prompt_template(mode) for mode in ("fast", "general", "expert")}
    assert len(set(prompts.values())) == 3


def test_invalid_mode_raises() -> None:
    with pytest.raises(ValueError, match="unsupported mode"):
        apply_prompt_template("ultra")


def test_context_kwargs_accepted() -> None:
    prompt = apply_prompt_template("general", skills=["a"], deferred_names=["b"])
    assert "general" in prompt


def test_language_constraint_in_prompt() -> None:
    prompt = apply_prompt_template("general")
    assert "语言约束" in prompt or "language" in prompt.lower()
