# 新会话交接 Prompt：阶段 2 上下文治理 → 复习串联 + 继续五层记忆

> 用法：新会话开场时把下面【交接 Prompt】整段粘贴给 Claude Code。它包含两部分：① 让新会话用**流程主线**帮我复习串联治理机制（不要列清单）；② 继续阶段 2 的五层记忆。

---

## 【交接 Prompt】

我是 Poirot 源码学习者，**Python 零基础、LLM Agent 零基础**，目标是"改造级"掌握 Poirot（能加中间件/换记忆策略/扩展技能）。我已经通过对话完成阶段 2「上下文治理」的完整讲解（含逐行翻译）。

**本次会话请先做一件事**：用**一条流程主线**（跟着一次 run 的时间线走）帮我**复习并串联**上下文治理的完整机制——不要列清单/堆表格，把每个机制放在"当时为什么介入"的位置上讲，讲完确认我理解无遗漏后，再继续阶段 2 的**五层记忆**（或听我安排）。

### 我的背景与讲解要求
- Python 零基础：必要源码必须**逐行翻译成自然语言**（一行 Python 对应一句人话）
- Agent 零基础：专业术语先解释；**先给代号/概念先导表，再进代码**
- 执行逻辑中标注 **函数名 + 文件名:行号**（每段代码块上方都要标）
- 不遗漏设计机制，包括"报告蓝图 vs 源码实现"的差异
- 先详细讲、后总结；我会深挖机制（迟滞环、镜像防线、状态为何放 state 等），请把机制讲透
- 学习计划：doc/LEARNING_PLAN.md；阶段 1（主循环+中间件框架）已完成，交接在 doc/HANDOFF_STAGE1.md

### 我理解的治理机制（按这条主线复习，查漏补缺）

**为什么有它**：ReAct 循环每轮追加几千 token，LangGraph 不管窗口，满了 API 直接 400、研究任务报废。治理 = 安全阀，三个目标：记账（精确知道占用）、分级处置（由轻到重）、保证不 400（不弄断消息配对）。

**角色与装配**：治理层 = 3 个中间件（TaggedContext 渲染 + MessageNormalizer 合并 system + StrategyMiddleware 策略桥）挂整条链最前（builder.py:33-49）；策略大脑 DefaultStrategy + 4 执行器（BudgetTracker 记账 / Externalizer 外化 / Summarizer 压缩 / Snapshot 快照）；策略经注册表注册（registry.py:18-42，@register_strategy("default")）；所有跨钩子状态装在 ThreadState 的 governance 背包（命名空间 + deep-merge + checkpointer 持久化，reducers.py:183-206）。

**执行主线（一次 run 的旅程）**：
1. **before_agent 立账本**：budget 全零、pending 空、抑制门槛 0、warned false（budget.py:14-24）
2. **每轮 before_model 先体检再还债**：`_ensure_pairing` 例行体检——历史里"有调用没结果"就补 error 占位（防 400，strategy.py:172-187）；然后看债单 pending 处置（"延迟一轮"：账是上一轮记的，保证工具结果已落地）
3. **wrap 洋葱**：TaggedContext 渲染 XML（<goal>/<plan>/<summary>/<date> 上下文块 + <thinking>/<answer> 标签），request-scoped 不持久；MessageNormalizer 合并 system；StrategyMiddleware.wrap_tool_call 是 POST 实时外化——结果一产生就写盘、只留 preview+路径进 state（源头截流，strategy.py:342-351）
4. **after_model 记账**：resolve_window_size 穿透 FallbackChatModel 取真实窗口（5 级解析，utilities.py:164-209）；seen_msgs 增量记账只累计 diff（budget.py:33-45）；fraction = 真实占用÷窗口（tiktoken 优先，CJK 字符估算兜底）；按阈值挂债单（0.40→P1、0.80→P4、0.90→P5）
5. **P1 外部化（fraction≥0.40）**：批量外化旧轮次大结果，两个保护——豁免（近 2 轮+每轮最新 1 条不碰，保住进行中上下文，externalizer.py:81-102）；间隔抑制（外化后门槛=当前 fraction+10%，防"外化→跌→再涨→再外化"的振荡，这是迟滞环，strategy.py:130-143）
6. **P4 压缩（fraction≥0.80，先于 P1 检查）**：先快照（snapshot.py:21-40）→ 切堆（preserve_recent=6）→ 三道手术防线（_snap_to_pairing 切点吸附 / _strip_orphan_tools 孤儿清扫 / _externalize_orphans 孤儿外化——丢之前先保全数据）→ LLM 总结旧堆（内部调用打 internal_llm 标记）→ 历史替换成"摘要+最近6条"→ 摘要进 governance 供 <summary> 渲染（summarizer.py:27-47）
7. **P5 熔断（fraction≥0.90）**：剥未执行的 tool_calls（复用原 id 替换，第四道防线）+ 注入收尾提醒（≥0.99 文案强制）+ jump 回模型 + warned 防死循环（strategy.py:260-281）
8. **after_agent 清场**：清过程状态（budget/pending/warned/p1_*），保留产出（summary/snapshot_path/metrics）跨 run 复用（budget.py:68-74）

**三条底线**：无损优先（外化先于压缩，压缩前必快照+孤儿外化）；配对不 400（四道防线层层递进+下一轮体检兜底）；状态进 state（governance 命名空间，跨钩子/跨轮/跨 run，不用实例属性——checkpointer 持久化/并发串味/可测试性）

**实现真相**（报告 vs 源码）：完整实现只有 P1/P4/P5 三级；P2 阈值无人消费（打标实际每轮无条件做）；P3 不可达预留（触发源没接，启用只需在 budget.py:51-60 加一行）；99% 硬停是 P5 文案分支

### 下一步：五层记忆（学习计划 §3.2）

> 衔接注记：上下文治理已另写成长篇机制详解 doc/STAGE2_CONTEXT_GOVERNANCE.md（第 1-12 章，含全部出处与实现真相）——复习深度机制时按这份文档讲，本页主线只作自检蓝本。
- 阅读路径（自顶向下）：L1 memory/types.py+schema.py（15 字段冻结 dataclass、5 原子操作、工具无 LLM）→ L2 strategies/default/{decay,forget,manager,strategy}.py（Ebbinghaus 公式、lazy decay）→ L3 {store,retriever}.py（MarkdownFileStore + BM25）→ L4 {memory_provider,memory_manager,config,worker}.py+两个记忆中间件 → L5 worker.py+memory_consolidation_middleware.py（daemon 线程+Queue）
- 重点：为什么记忆注入用 HumanMessage（prompt cache）；为什么 state 只存索引；Ebbinghaus 三项设计；lazy decay 是正确性选择而非性能选择
- 讲解时同样逐行翻译、标注行号、对照 ANALYSIS_REPORT.md §4.2 Part B、标注实现真相

### 环境注意事项
- 未装依赖则：python -m venv .venv && .venv/Scripts/activate && pip install -e ".[dev]"
- 跑测试：pytest poirot/backend/tests/v1/unit/context_engineering（治理）/ unit/memory（记忆）
- 调试第一站：.poirot/logs/threads/{tid}/runs/{rid}/compaction.jsonl（治理压缩 trace）
