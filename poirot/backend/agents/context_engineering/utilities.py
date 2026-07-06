"""token utility：token_counter + resolve_window_size。

tiktoken 懒加载 + 失败 cooldown 缓存 + CJK-aware char fallback。
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_TIKTOKEN_RETRY_COOLDOWN_S = 600
_DEFAULT_WINDOW = 128_000

_ENCODING_CACHE: dict[str, Any] = {}
_last_failure_ts: float = 0.0
_loading_sentinel = object()

# CJK Unified Ideographs + Extension A + CJK Symbols
_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3000, 0x303F))


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in _CJK_RANGES)


def _extract_text(message: Any) -> str:
    """从 message（str / BaseMessage / dict）提取纯文本。"""
    if isinstance(message, str):
        return message
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        return "".join(parts)
    return str(content) if content is not None else ""


def _char_estimate(messages: list) -> int:
    """CJK-aware char 估算：CJK 字符 ~1 token，非 CJK ~4 字符/token。"""
    cjk = 0
    other = 0
    for msg in messages:
        for ch in _extract_text(msg):
            if _is_cjk(ch):
                cjk += 1
            else:
                other += 1
    return cjk + other // 4


def _get_encoding(model_name: str | None) -> Any | None:
    """tiktoken encoding 懒加载 + 失败 cooldown + 并发 LOADING sentinel。"""
    global _last_failure_ts
    key = model_name or "default"
    if key in _ENCODING_CACHE:
        cached = _ENCODING_CACHE[key]
        return None if cached is _loading_sentinel else cached
    if time.time() - _last_failure_ts < _TIKTOKEN_RETRY_COOLDOWN_S:
        return None
    try:
        import tiktoken  # type: ignore[import-untyped]

        enc = tiktoken.encoding_for_model(key) if model_name else tiktoken.get_encoding("cl100k_base")
    except Exception as exc:
        logger.warning("tiktoken unavailable, fallback to char estimate: %s", exc)
        _last_failure_ts = time.time()
        _ENCODING_CACHE[key] = _loading_sentinel
        return None
    _ENCODING_CACHE[key] = enc
    return enc


def token_counter(messages: list, model_name: str | None = None) -> int:
    """算 messages 总 token。tiktoken 优先，失败 fallback char 估算。"""
    enc = _get_encoding(model_name)
    if enc is None:
        return _char_estimate(messages)
    total = 0
    for msg in messages:
        try:
            total += len(enc.encode(_extract_text(msg)))
        except Exception:
            total += _char_estimate([msg])
    return total


def resolve_window_size(model: Any) -> int:
    """取模型上下文窗口大小。max_tokens/_identifying_params/default 128000。"""
    for attr in ("max_input_tokens", "model_max_tokens", "max_tokens"):
        value = getattr(model, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    params = getattr(model, "_identifying_params", None)
    if callable(params):
        try:
            params = params()
        except Exception:
            params = None
    if isinstance(params, dict):
        for k in ("max_input_tokens", "model_max_tokens", "max_tokens"):
            v = params.get(k)
            if isinstance(v, int) and v > 0:
                return v
    return _DEFAULT_WINDOW
