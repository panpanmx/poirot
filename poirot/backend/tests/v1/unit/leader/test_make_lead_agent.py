from poirot.backend.agents.capabilities.registry import CapabilityRegistry
from poirot.backend.agents.leader.factory import make_lead_agent
from poirot.backend.agents.reporting.markdown_reporter import MarkdownReporter
from poirot.backend.agents.tools.base import FakeSearchTool


def test_make_lead_agent_uses_prepared_dependencies() -> None:
    registry = CapabilityRegistry(
        models={},
        tools={"web_search_mcp": FakeSearchTool()},
        reporter=MarkdownReporter(),
        artifact_store=object(),
    )

    agent = make_lead_agent(capability_registry=registry, middleware_manager=None)

    assert agent.capability_registry is registry
