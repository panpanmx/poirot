"""Memory 模块 — 长期记忆系统。

承接 `Hezao-MemDesign-Docs/poirot/00-long-term-memory-foundation.md` 奠基（D1-D16 ADR
+ 三层解耦架构）+ `01-poirot-integration-points.md` 介入清单 + `48-memory-l1-base-layer.md`
Layer 1 完整设计。

三层解耦架构（north-star）：
- Layer 1（本模块当前状态）：基础可用性层（Schema + 9 Protocol + 状态接入 + Registry slot）
- Layer 2：记忆管理层（默认策略实现：EbbinghausDecayPolicy / CompositeForgetPolicy / DefaultMemoryManager）
- Layer 3：存储与检索层（MarkdownFileStore / SQLiteShadowStore / HybridRetriever）
- Layer 4：集成层（MemoryMiddleware + bootstrap + 5 处 make_lead_agent 透传）
- Layer 5：演化层（Phase 2 LLM 决策 cron）
- Layer 6：扩展层（adapter 具体实现 + Persona）

依赖方向：`app → agents/memory → (agents/capabilities, agents/state, agents/config)`。
memory 包不反向依赖 `app`；跨层用 Protocol 破循环（boundary §3.1）。

INVARIANT（Layer 1 不变量，16 条）：

1. **MemoryTrace 不可变**：frozen dataclass，strength 等可变字段通过 `with_strength()`
   / `with_operation()` 创建新实例替换（类似 skill version DAG 的 is_active 指针）
2. **四操作无 LLM**：Encode/Associate/Consolidate/Reconsolidate 是纯存储操作，LLM 生成内容
   外部传入（Retrieve 移至 Retriever）
3. **检索是一切基础**：Phase 1 对话与 Phase 2 记忆管理都从 retrieve 开始（00 D4），
   retrieve 统一走 Retriever
4. **lazy decay**：strength 在 retrieve 时按需计算，不跑后台衰减任务（00 §5.5）
5. **Protocol 纯契约**：9 Protocol（7 核心 + 2 adapter）零实现，可 mock 可替换（00 D8）
6. **strategies/default/ 同构**：与 context_engineering/strategies/default/ 同构，策略可插拔
7. **CapabilityRegistry 注册**：memory_provider 作为第 9 个 capability，禁全局单例（00 D11）
8. **CORE_FIELDS 保护**：recalled_memories / memory_updates 加入 CORE_FIELDS，防 metadata 冲突
9. **向后兼容**：memory_provider=None / use="" 时 Poirot 行为不变
10. **import 防火墙**：`agents/memory/` 不反向依赖 `app`（00 D12）
11. **runtime 可切**：enable_recall/extract/token_budget/decay/forget/phase2 通过
    `set_memory_config()` 整替，Provider/Middleware/Retriever 不缓存 config，每次从
    `get_memory_config()` 取最新（参照 deer-flow memory_config.py 模式）
12. **STARTUP_ONLY 仅 4 字段**：use/storage_path/vector_store/graph_store 换需重启
    （重建 Provider/adapter + 重建 derived index）；其余 runtime 可切
13. **叠加非互斥**：Markdown truth（总在）+ optional VectorStore + optional GraphStore
    三层叠加，可同时启用（00 §8.2 derived shadow index），vector_store 与 graph_store 非三选一
14. **adapter 是 Retriever 子组件**：VectorStore/GraphStore 非独立 MemoryProvider，由
    HybridRetriever 组合；adapter 加载失败 → no-op 跳过 + log warning，系统不崩
15. **lifecycle duck-type**：MemoryProvider/adapter 构造即就绪，无强制 initialize()；
    shutdown 走 `hasattr(provider, "shutdown")` 检查，MarkdownFileStore 不实现，
    SQLiteShadowStore/VectorStore 实现（参照 deer-flow SandboxProvider 模式）
16. **operation_log traceability**：MemoryTrace.operation_log 记录操作历史
    （encode/associate/consolidate/reconsolidate/forget），上限 20 条 FIFO；retrieve 不记
    （高频，强化在 strength/access_count 已体现）；actor 字段预留 turn_id（Layer 4 注入）；
    支持 debug 回溯"谁何时对哪条 trace 做了什么"
"""

from __future__ import annotations
