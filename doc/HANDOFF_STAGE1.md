# 新会话交接 Prompt:阶段 1 完成 → 继续练习 2(TimeItMiddleware)

> 用法:新会话开场时,把下面【交接 Prompt】整段粘贴给 Claude Code。或直接说"按 doc/HANDOFF_STAGE1.md 继续阶段 1 的练习 2"。

---

## 【交接 Prompt】

我是 Poirot 源码学习者,已按 doc/LEARNING_PLAN.md 完成阶段 1(主循环 + 中间件框架)的全部讲解,现在要执行阶段 1 的练习 2(写 TimeItMiddleware)。请按以下信息无缝接手,不要重复讲解已完成的内容。

### 我的背景
- Python 零基础,LLM Agent 零基础,目标是"改造级"掌握 Poirot(能加中间件/换记忆策略/扩展技能)
- 学习计划在 doc/LEARNING_PLAN.md(阶段 2 是上下文治理 + 五层记忆,在练习 2 之后)
- 讲解风格要求:先详细讲、后表格总结;专业术语先解释;引用源码标注 文件名:行号;源码引用用 markdown 相对路径链接

### 已理解(已完成,不要重复讲解)
1. **Why**:中间件 vs 写死逻辑;5 钩子(before/after_agent、before/after_model、wrap_tool_call);after 钩子**逆序**执行、wrap 嵌套(洋葱模型);注入全在 before_model、检查全在 after_model(wrap 里注入会破坏 tool_call 配对 → 400);"被调用 ≠ 干活"(提前返回 return None);三层决定(装配层/钩子频率/函数内条件)
2. **sync/async 钩子**:运行时按图执行模式选择版本(ainvoke → a 前缀版),不自动转换;需要 await 的逻辑必须 async,纯数据操作 sync 即可
3. **装配**:make_lead_agent(factory.py:167)组装模型(registry.get_model("researcher"))、工具三来源(available.py 分组 core/deferred + registry.tools + specialist_tools)、21 个中间件(_build_middlewares factory.py:53,条件挂载=参数化行为)、提示词(apply_prompt_template prompts.py:54,条件注入段保护 prompt cache)、checkpointer 单例(checkpointer.py:18)、ThreadState(state/types.py:136,Annotated reducer 决定合并)→ create_agent 编译成图
4. **运行**:LeaderAgent.run(agent.py:77)→ 空 state(create_initial_thread_state thread_state.py:6,实际未传给 ainvoke,是冗余代码)→ config 9 键 → asyncio.run(graph.ainvoke(3 键输入))
5. **图循环**:before_agent(RunJournal 记 agent.started、ToolCall 记 errors 基线+清旧队列)→ before_model 链(治理 3 个→SystemContext→技能 3 个→RunJournal 记 llm.request→Sandbox ContextVar 恢复→Memory 召回注入→MemoryConsolidation no-op→Dangling 补配对→ToolCall drain 失败摘要→Todo 提醒)→ 模型 → after_model 逆序链(RunJournal 记 llm.response→Memory 清 turn_id→MemoryConsolidation 后台沉淀→Stall 卡死暂停→Todo 完成度→Reflection 充分性,共享 _jump_budget ≤3)
6. **wrap 洋葱链**(外→内):RunJournal 打点→HelpRequest 拦 ask_help→ToolCall 账本(短路闸门+失败分类+摘要排队 3/6/9 次)→Orchestration delegate 打点→Evidence 证据双写→Stall 只记失败不暂停→Sandbox 懒加载 acquire→工具本体
7. **收尾**:after_agent 逆序(Report 合成 final_report→Title 设标题→RunJournal 记 agent.finished)→ run() 的 expert/default 分支(expert 取 final_report+存 artifact;default 取 _last_ai_message)→ AgentRunResult
8. **生态现状**:langchain AgentMiddleware 已稳定(2026-03),官方 prebuilt 中间件(Summarization 等);记忆主流是 checkpointer+Store+LangMem,middleware 只是接线层

### 现在要做:练习 2——TimeItMiddleware
要求(LEARNING_PLAN.md 2.4):
1. 新建 poirot/backend/agents/middlewares/timeit_middleware.py,继承 AgentMiddleware(langchain.agents.middleware.types):
   - before_model 记起始时间到实例属性,after_model 算耗时,打印 + 写入 journal(llm.timeit 事件)
   - 纯数据操作 → 写 sync 版钩子即可(可加 async 委托,参考 dangling_tool_call_middleware.py 的写法)
2. 在 leader/factory.py 的 _build_middlewares 挂载(先挂最后,跑完再换位置对比,思考差异)
3. 跑一次对话验证每轮打印耗时
4. 写最小测试 tests/v1/unit/middlewares/test_timeit_middleware.py(参考 test_run_journal_status.py:SimpleNamespace + MagicMock 伪造 runtime,直接调钩子)
5. 验收:每轮打印耗时;能回答挂最前 vs 挂最后(挂最后≈纯模型耗时,挂最前≈整轮端到端开销,因为 after 逆序);有测试

### 关键源码位置速查
- 中间件基类签名:langchain.agents.middleware.types(需先装依赖)
- 钩子契约:context_engineering/contract.py:60-85(GovernanceStrategy,第二层契约)
- 挂载点:leader/factory.py:53-165(_build_middlewares)
- 主循环:leader/agent.py(148 行)
- state 字段表:state/types.py:136-165
- 取 runtime 配置:_get_runtime_value(run_journal_middleware.py:18-65,四路径)
- journal 事件写法:run_journal_middleware.py 全文
- 测试范式:poirot/backend/tests/v1/unit/middlewares/test_run_journal_status.py
- 中间件写法的直接参照:run_journal_middleware.py(同形态)+ dangling_tool_call_middleware.py(sync+async 委托)

### 环境注意事项
- 当前机器两个 Python(anaconda、D:\python)都**没装 langchain**——练习前先按 LEARNING_PLAN.md 附录 C 装环境:python -m venv .venv && .venv/Scripts/activate && pip install -e ".[dev]"
- 装完后:本地可看 langchain 的 AgentMiddleware 源码(site-packages/langchain/agents/middleware/types.py),这是"源码是真相"的最后一环
- 跑测试:pytest poirot/backend/tests/v1/unit/middlewares -k timeit

### 练习 2 完成后的下一步(阶段 2 预告)
读 ANALYSIS_REPORT.md §4.2(172-255 行),按 LEARNING_PLAN.md 阶段 2 学习上下文治理 + 五层记忆(重点:Ebbinghaus 衰减、lazy decay、为什么记忆注入用 HumanMessage、为什么 state 只存索引)。
