"""token 成本估算公共层。

生产代码不落盘 usage——从 state messages 的 AIMessage.usage_metadata 汇总
（langchain 标准字段）。缺省时兜底字符估算（len//4，与 token_counter 同口径）。

成本按 DeepSeek 公开定价近似（deepseek-chat 2025 口径：输入 $0.27/M、输出 $1.10/M），
report 中标注"估算"。DEEPSEEK_MODEL=deepseek-v4-flash 的实际单价未知，勿当作精确值。
"""

from __future__ import annotations

from typing import Any

# 近似单价（USD / 1M token），标注口径
PRICING: dict[str, dict[str, float]] = {
    "deepseek": {"input": 0.27, "output": 1.10},  # 近似 deepseek-chat 价，估算
}

_CHAR_ESTIMATE_FALLBACK = True


def usage_from_state(state: dict) -> dict | None:
    """遍历 messages 累加 usage_metadata；全部缺失时兜底字符估算。"""
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    found = False
    for msg in state.get("messages", []) or []:
        meta = getattr(msg, "usage_metadata", None)
        if not meta:
            continue
        found = True
        total["prompt_tokens"] += int(meta.get("input_tokens", 0) or 0)
        total["completion_tokens"] += int(meta.get("output_tokens", 0) or 0)
        total["total_tokens"] += int(meta.get("total_tokens", 0) or 0)
    if found:
        return total
    if _CHAR_ESTIMATE_FALLBACK:
        chars = sum(
            len(_extract_text(getattr(m, "content", "")))
            for m in state.get("messages", []) or []
        )
        return {
            "prompt_tokens": chars // 4,
            "completion_tokens": 0,
            "total_tokens": chars // 4,
            "estimate": True,
        }
    return None


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", ""))
        return "".join(parts)
    return str(content) if content else ""


def estimate_cost_usd(usage: dict | None, provider: str = "deepseek") -> float | None:
    """按近似单价估算 USD 成本。usage 缺失返 None。"""
    if not usage:
        return None
    price = PRICING.get(provider)
    if not price:
        return None
    p = usage.get("prompt_tokens", 0) or 0
    c = usage.get("completion_tokens", 0) or 0
    return (p * price["input"] + c * price["output"]) / 1_000_000
