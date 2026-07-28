"""默认策略常量（衰减参数 / 阈值 / BM25 权重）。

Layer 1：仅衰减参数 + 检索权重（供 schema 默认值参考 + Layer 2/3 使用）。
Layer 2：遗忘阈值 / 检索权重细化。
Layer 3：BM25 参数。

承接 `Hezao-MemDesign-Docs/poirot/00-long-term-memory-foundation.md` §5.2 + §5.5。
"""

from __future__ import annotations

# 00 §5.2 三类记忆衰减参数（示例值，可调）
DECAY_PARAMS = {
    "episodic": {"base_strength": 0.7, "decay_rate": 0.1},      # 衰减快
    "semantic": {"base_strength": 0.8, "decay_rate": 0.02},     # 衰减慢
    "procedural": {"base_strength": 0.9, "decay_rate": 0.005},  # 几乎不衰减
}

# 00 §5.5 复合检索分数权重
RETRIEVAL_WEIGHTS = {
    "similarity": 0.7,   # 语义相关性占主导
    "strength": 0.3,     # 记忆强度参与排序
}

# 00 §5.5 衰减公式系数
DECAY_COEFFICIENTS = {
    "access_boost": 0.1,        # log(1 + access_count) × 0.1
    "importance_boost": 0.05,   # importance × 0.05
}
