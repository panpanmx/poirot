"""DefaultMemoryManager — 四操作编排（00 §5.3 + 48 Step 5.5 + 49 §4 Step 4）。

四操作：Encode / Associate / Consolidate / Reconsolidate（Retrieve 移至 Retriever）。
核心原则：工具里无 LLM。merged_content / new_content 外部传入。
依赖：MemoryStore Protocol（mock 注入，Layer 3 实现 MarkdownFileStore）。

traceability（48 v3 + 49 v2）：
- A：每操作 append OperationLog（encode/associate/consolidate/reconsolidate/forget）
- B：每操作 emit journal 事件（memory.*），journal callback 注入
- C：actor 字段从 ContextVar `_turn_id_var` 取（Layer 4 Middleware 注入 turn_id）

拍板决策（49 v2-v3）：
- A1：encode strength = base_strength（初始强度）
- B3：reconsolidate 保留原 strength + last_accessed=now（视为一次访问）
- C1：forgotten trace Retriever 过滤（L3 实现，L2 只标记 metadata.forgotten）
- D3：associate LRU 淘汰最弱关联（超 max 时）
- E1：consolidate max=10
- F2：encode id = SHA256(content+type.value)[:16]（同内容同 type 去重）+ batch_update
- 点4：encode get-then-add 幂等（同 id 返回已存在 trace）
"""

from __future__ import annotations

import hashlib
import time
from contextvars import ContextVar
from dataclasses import replace
from typing import Callable

from poirot.backend.agents.memory.config import get_memory_config
from poirot.backend.agents.memory.exceptions import MemoryNotFoundError
from poirot.backend.agents.memory.memory_store import MemoryStore
from poirot.backend.agents.memory.schema import (
    Association,
    MemoryTrace,
    MemoryType,
    OperationLog,
)
from poirot.backend.agents.memory.strategies.default._constants import (
    ASSOCIATE_DEFAULTS,
    CONSOLIDATE_PARAMS,
    DECAY_PARAMS,
)
from poirot.backend.agents.memory.strategies.default.decay import EbbinghausDecayPolicy
from poirot.backend.agents.memory.strategies.default.forget import CompositeForgetPolicy

# ContextVar：Layer 4 MemoryMiddleware before_model 设 turn_id，manager._get_actor() 取
# Layer 2 测试时不设，actor=None
_turn_id_var: ContextVar[str | None] = ContextVar("memory_turn_id", default=None)


def set_turn_id(turn_id: str | None) -> None:
    """Layer 4 MemoryMiddleware 调用，设置当前 turn_id（关联记忆操作到对话轮次）。"""
    _turn_id_var.set(turn_id)


class DefaultMemoryManager:
    """默认记忆管理器（四操作，00 §5.3 + 49 §4 Step 4）。

    依赖注入：store + decay_policy + forget_policy + journal（策略组合 + traceability）。
    无 LLM：merged_content / new_content 外部传入。
    frozen 语义：所有操作返回新 MemoryTrace 实例 + with_operation append 日志。
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        decay_policy: EbbinghausDecayPolicy | None = None,
        forget_policy: CompositeForgetPolicy | None = None,
        journal: Callable[[str, dict], None] | None = None,
    ) -> None:
        """初始化。

        Args:
            store: 持久化后端（MemoryStore Protocol，Layer 3 实现 / Layer 2 mock）
            decay_policy: 衰减策略（None 时默认 EbbinghausDecayPolicy）
            forget_policy: 遗忘策略（None 时默认 CompositeForgetPolicy，内部用 decay_policy）
            journal: 事件回调（traceability B），None 时不发事件；Layer 4 注入 RunJournal
        """
        self._store = store
        self._decay_policy = decay_policy or EbbinghausDecayPolicy()
        self._forget_policy = forget_policy or CompositeForgetPolicy(self._decay_policy)
        self._journal = journal

    @staticmethod
    def _compute_trace_id(content: str, type: MemoryType) -> str:
        """F2：id = SHA256(content + type.value) 前 16 位。

        同 content + 同 type → 同 id → store.add 冲突 → encode 幂等返回旧 trace。
        """
        type_key = type.value if isinstance(type, MemoryType) else str(type)
        raw = f"{content}\x00{type_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _add_association_with_lru(
        trace: MemoryTrace,
        new_assoc: Association,
        max_assocs: int,
    ) -> MemoryTrace:
        """D3：加关联，超 max 时 LRU 淘汰 strength 最低的。

        Args:
            trace: 原 trace（不修改）
            new_assoc: 待加的关联
            max_assocs: 单 trace 最大关联数

        Returns:
            新 trace（associations 更新后）
        """
        current = trace.associations
        if len(current) >= max_assocs:
            # D3：淘汰 strength 最低的关联（排序后保留 max_assocs-1 条 + 新关联）
            sorted_assocs = sorted(current, key=lambda a: a.strength, reverse=True)
            kept = tuple(sorted_assocs[: max_assocs - 1]) + (new_assoc,)
            return replace(trace, associations=kept)
        return replace(trace, associations=current + (new_assoc,))

    def _get_actor(self) -> str | None:
        """C：取当前 turn_id（Layer 4 MemoryMiddleware 注入 ContextVar）。"""
        return _turn_id_var.get()

    def _emit_journal(self, event: str, payload: dict) -> None:
        """B：emit journal 事件（Layer 4 注入 RunJournal，Layer 2 测试用 mock）。"""
        if self._journal is not None:
            self._journal(event, payload)

    def _get_decay_params(self, type: MemoryType) -> dict:
        """取衰减参数（runtime config 优先，缺省回退 _constants）。"""
        config = get_memory_config()
        type_key = type.value if isinstance(type, MemoryType) else str(type)
        if hasattr(config, "decay") and type_key in config.decay:
            return config.decay[type_key]
        return DECAY_PARAMS[type_key]

    def _get_associate_defaults(self) -> dict:
        return ASSOCIATE_DEFAULTS

    def _get_consolidate_params(self) -> dict:
        return CONSOLIDATE_PARAMS

    def encode(
        self,
        content: str,
        type: MemoryType,
        *,
        importance: float = 0.5,
        source: str | None = None,
        metadata: dict | None = None,
    ) -> MemoryTrace:
        """Encode（编码）：创建新记忆（00 §5.3）。

        F2：id = SHA256(content + type.value) 前 16 位（同内容同 type 去重）。
        点4：get-then-add 幂等 — 同 id 已存在则返回旧 trace（不抛错）。
        A1：strength = base_strength（初始强度）。

        Args:
            content: 记忆内容（自然语言，外部传入）
            type: 记忆类型（episodic/semantic/procedural）
            importance: 语义重要性 0.0~1.0（默认 0.5，Phase 2 LLM 评估后传入）
            source: 来源（thread_id / run_id / user_input）
            metadata: 扩展（tags / project / specialist_id）

        Returns:
            MemoryTrace（新建 或 已存在，幂等）
        """
        # F2：id = content hash（同内容同 type 去重）
        trace_id = self._compute_trace_id(content, type)

        # 点4：get-then-add 幂等
        existing = self._store.get(trace_id)
        if existing is not None:
            # 同内容已存在，返回旧 trace（幂等，不重复 add）
            self._emit_journal("memory.encode.duplicate", {
                "trace_id": trace_id, "type": type.value,
                "content_preview": content[:100],
            })
            return existing

        # A1：strength = base_strength
        now = time.time()
        params = self._get_decay_params(type)
        actor = self._get_actor()
        trace = MemoryTrace(
            id=trace_id,
            content=content,
            type=type,
            strength=params["base_strength"],
            base_strength=params["base_strength"],
            decay_rate=params["decay_rate"],
            access_count=0,
            last_accessed=now,
            importance=importance,
            associations=(),
            embedding=None,
            source=source,
            created_at=now,
            metadata=metadata or {},
            operation_log=(OperationLog(
                timestamp=now,
                operation="encode",
                actor=actor,
                diff={"content": (None, content[:200]), "type": (None, type.value)},
            ),),
        )
        self._store.add(trace)
        self._emit_journal("memory.encode", {
            "trace_id": trace_id, "type": type.value,
            "content_preview": content[:100], "timestamp": now, "actor": actor,
        })
        return trace

    def associate(
        self,
        trace_id_a: str,
        trace_id_b: str,
        *,
        strength: float | None = None,
        type: str | None = None,
    ) -> None:
        """Associate（关联）：建立两条记忆的关联（00 §5.3，双向）。

        D3：超 max_associations_per_trace 时 LRU 淘汰 strength 最低的关联（非静默跳过）。

        Args:
            trace_id_a: 记忆 A 的 id
            trace_id_b: 记忆 B 的 id
            strength: 关联强度（默认 ASSOCIATE_DEFAULTS["default_strength"]）
            type: 关联类型（默认 ASSOCIATE_DEFAULTS["default_type"]）

        Raises:
            MemoryNotFoundError: trace_id_a 或 trace_id_b 不存在
        """
        defaults = self._get_associate_defaults()
        assoc_strength = strength if strength is not None else defaults["default_strength"]
        assoc_type = type if type is not None else defaults["default_type"]
        max_assocs = defaults["max_associations_per_trace"]

        trace_a = self._store.get(trace_id_a)
        if trace_a is None:
            raise MemoryNotFoundError(trace_id_a)
        trace_b = self._store.get(trace_id_b)
        if trace_b is None:
            raise MemoryNotFoundError(trace_id_b)

        now = time.time()
        actor = self._get_actor()
        new_assoc_a = Association(target_id=trace_id_b, strength=assoc_strength, type=assoc_type)
        new_assoc_b = Association(target_id=trace_id_a, strength=assoc_strength, type=assoc_type)

        # D3：LRU 淘汰最弱关联（超 max 时淘汰 strength 最低的，腾位给新关联）
        updated_a = self._add_association_with_lru(trace_a, new_assoc_a, max_assocs)
        updated_b = self._add_association_with_lru(trace_b, new_assoc_b, max_assocs)

        # append operation_log（traceability A）
        updated_a = updated_a.with_operation(OperationLog(
            timestamp=now, operation="associate", actor=actor,
            diff={"target": trace_id_b, "strength": assoc_strength, "type": assoc_type},
        ))
        updated_b = updated_b.with_operation(OperationLog(
            timestamp=now, operation="associate", actor=actor,
            diff={"target": trace_id_a, "strength": assoc_strength, "type": assoc_type},
        ))

        self._store.update(updated_a)
        self._store.update(updated_b)
        self._emit_journal("memory.associate", {
            "trace_id_a": trace_id_a, "trace_id_b": trace_id_b,
            "strength": assoc_strength, "type": assoc_type,
            "timestamp": now, "actor": actor,
        })
