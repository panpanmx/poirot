import pytest

from poirot.backend.agents.config.loader import ConfigError, load_config


def test_loads_general_profile_with_defaults() -> None:
    config = load_config(mode="general")

    assert config.runtime.mode == "general"
    assert config.runtime.plan_enabled is True
    assert config.reporting.save_artifact is True
    assert config.runtime.logs_root == ".poirot/logs"
    assert config.models.researcher_model == "fake-researcher"


def test_cli_override_can_change_mode() -> None:
    config = load_config(mode="general", cli_overrides={"mode": "fast"})

    assert config.runtime.mode == "fast"
    assert config.runtime.plan_enabled is False
    assert config.reporting.save_artifact is False


def test_missing_required_model_returns_clear_error() -> None:
    with pytest.raises(ConfigError, match="researcher_model is required"):
        load_config(mode="general", cli_overrides={"researcher_model": ""})


def test_rejects_unknown_mode() -> None:
    with pytest.raises(ConfigError, match="Unsupported mode"):
        load_config(mode="unknown")
