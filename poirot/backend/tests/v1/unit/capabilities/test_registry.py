import pytest

from poirot.backend.agents.capabilities.registry import (
    CapabilityMissingError,
    CapabilityRegistry,
)
from poirot.backend.agents.capabilities.models.base import FakeModel
from poirot.backend.agents.tools.base import FakeSearchTool


def test_registry_returns_registered_capabilities() -> None:
    registry = CapabilityRegistry(
        models={
            "researcher": FakeModel(name="researcher"),
            "reporter": FakeModel(name="reporter"),
        },
        tools={"web_search_mcp": FakeSearchTool()},
        reporter=object(),
        artifact_store=object(),
    )

    assert registry.get_model("researcher").name == "researcher"
    assert registry.get_tool("web_search_mcp").name == "web_search_mcp"
    assert registry.get_reporter() is not None
    assert registry.get_artifact_store() is not None


def test_registry_missing_capability_error_is_clear() -> None:
    registry = CapabilityRegistry(models={}, tools={}, reporter=None, artifact_store=None)

    with pytest.raises(CapabilityMissingError, match="model not registered: researcher"):
        registry.get_model("researcher")
