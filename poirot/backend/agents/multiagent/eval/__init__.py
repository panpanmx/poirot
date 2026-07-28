"""L3 eval 编排评估层 — 可插拔评估方法库 + 健康监控 + 跨 run 学习.

设计（43 文档 §1 + spec.md multiagent-l3-eval-layer）:
- L3 不演化（EvalAdapter 是可插拔库，新增/替换由人工 + L2 触发，避免无限递归到 L4）
- L2 调 L3 唯一入口：OrchestrationBridge.evaluate(ctx) → EvalResult（fail-closed）
- sync only（与 L1 D10 一致）
- L3 不进 L1 graph（与 L2 一致）
- 复用 L2 daemon thread pattern（独立 thread，不嵌套）
- 复用 L2 MetricsView Protocol（扩展加 get_specialist_l2_events）
- 复用 L2 自建 EvalTask / EvalResult（import from evolution/promotion_gate.py）
- 复用 L2 _wilson_ci（import from evolution/promotion_gate.py）
- L3 metrics 复用 l2_metrics 表（event_type 加 l3_ 前缀）
- L3 默认 enabled=false（数据驱动触发后才实现）

L3 INVARIANT 21 条待 Batch 15 补（OrchestrationBridge Protocol / L2 调 L3 唯一入口 / sync only /
fail-closed / L2 收 success=False reject / L3 自建 Protocol / task_sample 由 L2 传 / L3 不演化 /
3 adapter Bridge 自动选 / SpecialistRuntimeTracker 自建 / degraded_specialists enqueue L2 cron queue /
L3 不进 L1 graph / L3 复用 L2 daemon thread / L3 复用 L2 MetricsView / L3 启用时 L2 改调 Bridge /
decision log 异步写 / decision log 不进 prompt / decision log 90 天 + 归档 /
L3 metrics 复用 l2_metrics / L3 CLI 暂不实现 / L3 默认 enabled=false）.
"""
