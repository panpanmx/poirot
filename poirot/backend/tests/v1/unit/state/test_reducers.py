import pytest

from poirot.backend.agents.state.reducers import ReducerConflictError, merge_thread_state
from poirot.backend.agents.state.types import (
    Artifact,
    Citation,
    ReflectionItem,
    Source,
)


def test_sources_are_deduplicated_by_source_id_or_url() -> None:
    state = {"sources": [Source(source_id="s1", url="https://a.test", title="A")]}
    patch = {
        "sources": [
            Source(source_id="s1", url="https://a.test/updated", title="A2"),
            Source(source_id="s2", url="https://a.test", title="A3"),
            Source(source_id="s3", url="https://b.test", title="B"),
        ]
    }

    merged = merge_thread_state(state, patch)

    assert [source.source_id for source in merged["sources"]] == ["s1", "s3"]
    assert merged["sources"][0].title == "A2"


def test_citations_artifacts_and_reflections_merge_by_identity() -> None:
    state = {
        "citations": [
            Citation(citation_id="c1", source_id="s1", quote="Q", claim="C")
        ],
        "artifacts": [
            Artifact(artifact_id="a1", artifact_type="markdown", title="Draft", path="x")
        ],
        "reflection_items": [
            ReflectionItem(
                item_id="r1",
                scope="run",
                kind="evidence_gap",
                question="Need source?",
                status="open",
            )
        ],
    }
    patch = {
        "citations": [
            Citation(citation_id="c1", source_id="s1", quote="Q2", claim="C2")
        ],
        "artifacts": [
            Artifact(
                artifact_id="a1",
                artifact_type="markdown",
                title="Final",
                path="final.md",
            )
        ],
        "reflection_items": [
            ReflectionItem(
                item_id="r1",
                scope="run",
                kind="evidence_gap",
                question="Need source?",
                status="addressed",
            )
        ],
    }

    merged = merge_thread_state(state, patch)

    assert merged["citations"][0].quote == "Q2"
    assert merged["artifacts"][0].path == "final.md"
    assert merged["reflection_items"][0].status == "addressed"


def test_metadata_cannot_override_core_field_semantics() -> None:
    with pytest.raises(ReducerConflictError, match="metadata cannot contain core field"):
        merge_thread_state({}, {"metadata": {"plan": "hidden"}})


def test_final_report_conflict_fails_closed() -> None:
    with pytest.raises(ReducerConflictError, match="final_report conflict"):
        merge_thread_state({"final_report": "A"}, {"final_report": "B"})


def test_errors_are_appended_and_limited() -> None:
    state = {"errors": [{"error_id": f"e{i}", "message": str(i)} for i in range(95)]}
    patch = {"errors": [{"error_id": f"e{i}", "message": str(i)} for i in range(95, 110)]}

    merged = merge_thread_state(state, patch)

    assert len(merged["errors"]) == 100
    assert merged["errors"][0]["error_id"] == "e10"
    assert merged["errors"][-1]["error_id"] == "e109"
