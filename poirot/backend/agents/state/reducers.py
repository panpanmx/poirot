from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from typing import Any, Iterable

CORE_FIELDS = {
    "messages",
    "user_input",
    "intent",
    "research_question",
    "plan",
    "current_step_id",
    "observations",
    "sources",
    "citations",
    "artifacts",
    "reflection_items",
    "final_report",
    "errors",
}

MAX_ERRORS = 100


class ReducerConflictError(ValueError):
    """Raised when a state patch would hide or corrupt core state."""


def merge_thread_state(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(state)
    for key, value in patch.items():
        if key == "sources":
            merged[key] = _merge_sources(merged.get(key, []), value)
        elif key in {"citations", "artifacts"}:
            merged[key] = _merge_by_attr(merged.get(key, []), value, f"{key[:-1]}_id")
        elif key == "reflection_items":
            merged[key] = _merge_by_attr(merged.get(key, []), value, "item_id")
        elif key == "errors":
            merged[key] = (list(merged.get(key, [])) + list(value))[-MAX_ERRORS:]
        elif key == "metadata":
            merged[key] = _merge_metadata(merged.get(key, {}), value)
        elif key == "final_report":
            merged[key] = _merge_final_report(merged.get(key), value)
        else:
            merged[key] = value
    return merged


def _merge_sources(current: Iterable[Any], incoming: Iterable[Any]) -> list[Any]:
    result = list(current)
    seen_urls = {_field(item, "url") for item in result}
    for item in incoming:
        item_id = _field(item, "source_id")
        url = _field(item, "url")
        replaced = False
        for index, existing in enumerate(result):
            if _field(existing, "source_id") == item_id or _field(existing, "url") == url:
                if _field(existing, "source_id") == item_id:
                    result[index] = item
                    seen_urls.add(url)
                replaced = True
                break
        if not replaced and url not in seen_urls:
            result.append(item)
            seen_urls.add(url)
    return result


def _merge_by_attr(current: Iterable[Any], incoming: Iterable[Any], attr: str) -> list[Any]:
    result = list(current)
    positions = {_field(item, attr): index for index, item in enumerate(result)}
    for item in incoming:
        item_id = _field(item, attr)
        if item_id in positions:
            existing = result[positions[item_id]]
            result[positions[item_id]] = _update_same_type(existing, item)
        else:
            positions[item_id] = len(result)
            result.append(item)
    return result


def _merge_metadata(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    forbidden = CORE_FIELDS.intersection(incoming)
    if forbidden:
        field = sorted(forbidden)[0]
        raise ReducerConflictError(f"metadata cannot contain core field: {field}")
    merged = dict(current)
    merged.update(incoming)
    return merged


def _merge_final_report(current: str | None, incoming: str | None) -> str | None:
    if current and incoming and current != incoming:
        raise ReducerConflictError("final_report conflict")
    return incoming if incoming is not None else current


def _field(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name)


def _update_same_type(existing: Any, incoming: Any) -> Any:
    if type(existing) is not type(incoming):
        return incoming
    if is_dataclass(existing):
        return replace(existing, **asdict(incoming))
    return incoming


# ---------------------------------------------------------------------------
# Public field-level reducers for Annotated[type, reducer] in ThreadState.
# Used by LangGraph graph-internal state merge. merge_thread_state (above)
# remains for LeaderAgent outer-layer patch merging (design D7).
# ---------------------------------------------------------------------------


def merge_sources(current: list | None, incoming: list | None) -> list:
    if incoming is None:
        return list(current or [])
    return _merge_sources(current or [], incoming)


def merge_citations(current: list | None, incoming: list | None) -> list:
    if incoming is None:
        return list(current or [])
    return _merge_by_attr(current or [], incoming, "citation_id")


def merge_artifacts(current: list | None, incoming: list | None) -> list:
    if incoming is None:
        return list(current or [])
    return _merge_by_attr(current or [], incoming, "artifact_id")


def merge_reflection_items(current: list | None, incoming: list | None) -> list:
    if incoming is None:
        return list(current or [])
    return _merge_by_attr(current or [], incoming, "item_id")


def merge_observations(current: list | None, incoming: list | None) -> list:
    if incoming is None:
        return list(current or [])
    return list(current or []) + list(incoming)


def merge_errors(current: list | None, incoming: list | None) -> list:
    if incoming is None:
        return list(current or [])
    return (list(current or []) + list(incoming))[-MAX_ERRORS:]


def merge_metadata(current: dict | None, incoming: dict | None) -> dict:
    if incoming is None:
        return dict(current or {})
    return _merge_metadata(current or {}, incoming)


def merge_final_report(current: str | None, incoming: str | None) -> str | None:
    return _merge_final_report(current, incoming)


def merge_todos(existing: list | None, new: list | None) -> list | None:
    """Reducer for todos list.

    Semantics:
    - new is None (node didn't touch todos) → preserve existing.
    - new is provided (even empty list) → full replacement (explicit update wins).
    """
    if new is None:
        return existing
    return new


def merge_governance(current: dict | None, incoming: dict | None) -> dict | None:
    """Reducer for ThreadState.governance — deep-merge, last-write-wins per leaf key.

    - incoming None → preserve current.
    - current None → return copy of incoming.
    - both dict → recursive deep-merge: dict values merged recursively,
      non-dict (scalar/list) last-write-wins.

    策略 bundle 自管命名空间 ``governance.<strategy_name>.*``，deep-merge 并存，
    同 key last-write-wins。跨轮经 checkpointer 持久化。
    """
    if incoming is None:
        return current
    if current is None:
        return dict(incoming)
    if not isinstance(current, dict) or not isinstance(incoming, dict):
        return incoming
    merged = dict(current)
    for key, value in incoming.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_governance(merged[key], value)
        else:
            merged[key] = value
    return merged
