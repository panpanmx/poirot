"""Multi-Agent L2 智能编排层 — 演化 ContextSummaryTemplate / SkillInjectionTemplate。

承接 design_docs/41-multi-agent-orchestration-three-layer-foundation.md §13 +
Hezao-MultiAgentDesign-Docs/poirot/42-multi-agent-l2-evolution-layer.md 详细设计。

核心立场（解读 B）：L2 不演化 Router（L1 D3 已定 Router = LLM），
L2 只演化 LLM 能看到但不进 system prompt cache prefix 的 per-call 产物
（ContextSummaryTemplate + SkillInjectionTemplate），hot swap 不破 cache。

L2 INVARIANT 40 条详见 42 文档 §8，本 docstring 待 Batch 14 补完整。
"""
