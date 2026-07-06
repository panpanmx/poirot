"""merge_governance reducer + token utility 单测。"""

from __future__ import annotations

from poirot.backend.agents.state.reducers import merge_governance
from poirot.backend.agents.context_engineering.utilities import (
    _char_estimate,
    token_counter,
)


# ---------- merge_governance ----------


def test_merge_governance_incoming_none_preserves_current() -> None:
    current = {"externalizer.refs": {"a": "p1"}}
    assert merge_governance(current, None) is current


def test_merge_governance_current_none_returns_copy() -> None:
    incoming = {"compressor.watermark": 5}
    result = merge_governance(None, incoming)
    assert result == incoming
    assert result is not incoming  # copy


def test_merge_governance_deep_merge_nested_dict() -> None:
    current = {"externalizer.refs": {"a": "p1"}}
    incoming = {"externalizer.refs": {"b": "p2"}}
    result = merge_governance(current, incoming)
    assert result == {"externalizer.refs": {"a": "p1", "b": "p2"}}


def test_merge_governance_last_write_wins_scalar() -> None:
    current = {"compressor.watermark": 5}
    incoming = {"compressor.watermark": 10}
    assert merge_governance(current, incoming) == {"compressor.watermark": 10}


def test_merge_governance_different_keys_coexist() -> None:
    current = {"externalizer.refs": {"a": "p1"}}
    incoming = {"compressor.watermark": 5}
    assert merge_governance(current, incoming) == {
        "externalizer.refs": {"a": "p1"},
        "compressor.watermark": 5,
    }


# ---------- token_counter ----------


def test_token_counter_empty() -> None:
    assert token_counter([]) == 0


def test_token_counter_cjk_real_count() -> None:
    # tiktoken 可用时返回实际计数（非 fallback）；至少 > 0
    count = token_counter(["你好世界"])
    assert count > 0


def test_char_estimate_cjk_aware() -> None:
    # 4 CJK + 4 latin("test") → 4 + 4//4 = 5
    assert _char_estimate(["你好世界test"]) == 5


def test_char_estimate_empty() -> None:
    assert _char_estimate([]) == 0
