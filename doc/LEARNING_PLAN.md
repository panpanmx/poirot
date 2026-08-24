# Poirot 源码学习计划

> 从 0 到改造级：模块设计思路、设计原因（Why）、源码精读、动手改造
>
> 前置画像：Python 熟练 · LLM Agent 零基础 · 目标=能二次开发（加中间件/换记忆策略/扩展技能）

---

## 0. 总览

### 0.1 学什么、学到什么程度

| 维度 | 目标 |
|------|------|
| 架构层 | 能画出全项目数据流，讲清每个模块为什么存在 |
| 设计层 | 每个核心模块能回答"为什么这样设计、不这样会怎样" |
| 源码层 | 核心路径（中间件框架、记忆、技能、装配）达到精读 |
| 改造层 | 能独立完成：新增中间件、自定义记忆策略、新增技能、加 CLI 命令 |
| 验证层 | 每个改造都有测试支撑（2400+ 测试是你的安全网） |

### 0.2 项目资产地图（三份材料配合使用）

| 材料 | 作用 | 用法 |
|------|------|------|
| `doc/ANALYSIS_REPORT.md`（62KB 架构报告） | **地图**：为什么这样设计、模块叙事线 | 每个模块先读对应章节，再进源码 |
| 源码（非测试 34K 行，测试 35K 行） | **真相**：一切结论的唯一依据 | 按每阶段阅读路径精读 |
| `poirot/backend/tests/v1/` 测试 | **说明书**：模块契约与边界的最精确表达 | 读不懂模块时读它的测试 |

### 0.3 方法论：四步学习闭环（每个模块重复）

```
① 读报告章节（拿 Why 和地图）
   └→ ② 按阅读路径读源码（验证 What/How，标注行号）
        └→ ③ 做动手练习（把理解变成真实改动）
             └→ ④ 输出自检（用"给别人讲一遍"的标准写笔记，回答自检问题）
```

**核心原则：先有 Why 再有 What。** 报告给你"为什么"，源码给你"是什么"，练习证明你真的懂了。跳过报告直接啃源码是效率最低的路径——34K 行里 80% 的代码是某个设计决策的落地细节，先懂决策再看细节，事半功倍。

### 0.4 总时间表（6 周 × 每周 10~12 小时）

| 周 | 阶段 | 模块 | 练习 |
|----|------|------|------|
| 0 | 0.5~1 | 环境 + Agent 前置知识 | 手写最小 ReAct |
| 1 | 1 | 主循环 + 中间件框架（核心） | 写第一个中间件 |
| 2 | 2 | 上下文治理 + 五层记忆 | 改衰减公式 / 自定义策略 |
| 3 | 3 | 三层技能系统 | 写一个 builtin skill |
| 4 | 4 | 多智能体编排 + 进化/评估闭环 | mock 跑通委派 |
| 5 | 5~6 | 沙箱 + MCP + 双 UI 装配 | 配 MCP / 加 CLI 命令 |
| 6 | 7 | 毕业项目（组合改造 + 测试） | 三合一改造 |

---

## 1. 阶段 0.5：Agent 前置知识（3~4 天）

**背景**：Poirot 的中间件体系直接继承 LangChain 的 `AgentMiddleware`（见 `poirot/backend/agents/middlewares/dangling_tool_call_middleware.py:17` 的 `from langchain.agents.middleware.types import AgentMiddleware`），运行时用 LangGraph 的 `Runtime`。所以必须先补最小概念集，否则源码里全是陌生名词。

### 1.1 最小概念清单（按依赖顺序）

| # | 概念 | 学什么 | 为什么必须先学 |
|---|------|--------|---------------|
| 1 | 消息协议 | `SystemMessage / UserMessage / AIMessage / ToolMessage / ToolCall`（`langchain_core.messages`） | 全项目 state 里流动的就是这些对象 |
| 2 | ReAct 循环 | 观察→思考→行动；为什么用原生 tool calling 而不是让模型输出 JSON | Poirot 的内核就是它 |
| 3 | LangGraph 最小集 | `StateGraph / add_node / add_edge / conditional_edges / State / Runtime` | `leader/agent.py` 的图编排 |
| 4 | LangChain AgentMiddleware | 钩子协议：`before/after_agent`、`before/after_model`、`wrap_tool_call` | **Poirot 的 5 个钩子就是它**（`context_engineering/contract.py:69-84`） |
| 5 | ContextVar | 异步请求级状态：`contextvars.ContextVar`、`token` 的 set/reset | 沙箱共享、turn_id 追溯都靠它 |
| 6 | MCP | 一句话概念：把工具做成可远程发现/调用的服务 | `mcp/` 模块的前提 |

**素材**：LangGraph / LangChain 官方文档只学上面标出的最小面，其他全部跳过。Poirot 源码是"参考答案"，遇到看不懂的先查概念再看代码。

### 1.2 练习 1：手写 30 行最小 ReAct（关键里程碑）

用 langchain 原生 API（不用 Poirot）实现：LLM 带一个 `search` 工具 → 循环直到模型不再要求调用工具 → 打印最终回答。

**验收标准**：
- [ ] 模型能完成"调用一次工具→基于结果回答"的完整链路
- [ ] 你画得出每一步 state 里 messages 的类型变化（AIMessage 带 tool_calls → ToolMessage → 最终 AIMessage）
- [ ] 能回答：为什么不能等模型"自己知道结果"而不是喂给它工具结果？

**通过此练习后**，LangGraph 图、消息协议、tool calling 三个概念就活了。

---

## 2. 阶段 1：主循环 + 中间件框架（第 1 周 · 全项目核心）

> **为什么它是第一站**：21 个中间件是所有横切能力的载体——记忆、技能、沙箱、治理全是挂在钩子上的插件。搞懂这一层，后面每个模块都是在"往钩子上挂东西"。

### 2.1 先读报告

`doc/ANALYSIS_REPORT.md` **§4.1「一条消息如何穿过 24 个中间件」**（约 128-367 行）。重点吸收：
- 洋葱模型 vs 线性管道的选择
- 为什么中间件是 first-class citizen 而非写死在循环里
- `app → agents` 单向依赖意味着什么

### 2.2 源码阅读路径（按此顺序，总 4 个文件 + 3 个精读）

| 顺序 | 文件 | 读什么 |
|------|------|--------|
| 1 | `poirot/backend/agents/leader/agent.py`（148 行） | **全读**。注意它有多薄——这就是中间件架构的证据：主循环本身只剩图编排 |
| 2 | `poirot/backend/agents/leader/factory.py:53-165` | `_build_middlewares`：挂载顺序注释（第 76 行起）+ 条件挂载逻辑（SkillActivation 只在有技能时挂、Sandbox/Memory 的开关） |
| 3 | `poirot/backend/agents/context_engineering/contract.py:69-84` | 5 个钩子协议定义——整个中间件系统的"接口契约" |
| 4 | 精读 3 个代表中间件 | 见下 |

**精读对象**（覆盖三种典型形态）：

| 中间件 | 代表形态 | 重点 |
|--------|---------|------|
| `middlewares/memory_recall_middleware.py` | 纯横向切面 | 如何在 `abefore_model` 里注入 `HumanMessage`；为什么注入消息而非改 system prompt（保护 prompt cache） |
| `middlewares/sandbox_middleware.py` | ContextVar 使用者 | 如何用 `state["sandbox"]` + ContextVar 让子 agent 共享沙箱 |
| `middlewares/dangling_tool_call_middleware.py` | tool 生命周期 | `wrap_tool_call` 钩子的用法；遇到悬挂 tool call 怎么办 |

### 2.3 设计思路精要（理解到能讲的程度）

1. **为什么中间件而非写死逻辑？** 21 个关注点（记忆、技能、治理、沙箱、防循环……）如果写进 agent 循环，循环会变成 2000 行的上帝类；中间件让每个关注点独立成文件、独立测试。看 `leader/agent.py` 只有 148 行，就是证据。
2. **为什么是 5 个钩子？** agent 生命周期的 4 个自然节点（agent 进出 + model 进出）+ 1 个工具调用节点，恰好覆盖所有横切需要。多了是过度设计，少了盖不住需求。
3. **为什么挂载顺序重要？** 中间件按声明顺序执行。治理层必须最先跑（先预算后注入）、记忆注入必须在模型调用前、`ReportMiddleware` 放最后（等全部数据齐了再写报告）。`factory.py:76` 的注释就是挂载哲学。
4. **异步钩子何时用？** 需要 LLM 调用的逻辑（如记忆整合的提取）必须 `async`，否则阻塞主循环；纯数据操作（如注入消息）用同步即可。

### 2.4 练习 2（改造级第一击）：写一个 TimeItMiddleware

目标：统计每次模型调用的耗时，写入 RunJournal。

步骤：
1. 在 `middlewares/` 下新建 `timeit_middleware.py`，继承 `AgentMiddleware`
2. 实现 `before_model`（记起始时间）和 `after_model`（算耗时并打印/log）
3. 在 `factory.py` 的 `_build_middlewares` 里挂载（挂最前或最后，思考影响）
4. 跑一次对话，验证输出

**验收标准**：
- [ ] 每轮模型调用都打印耗时
- [ ] 能回答：挂最前和挂最后对耗时数据有无影响？为什么？（钩子执行顺序问题）
- [ ] 给中间件写一个最小测试（参考 `tests/v1/unit/middlewares/` 现有测试的写法）

---

## 3. 阶段 2：上下文治理 + 五层记忆（第 2 周）

> **为什么它排第二**：记忆中间件是第一周见过的"钩子使用者"，现在往下一层，看钩子背后的完整系统。上下文治理解决"context 会不会爆"，记忆解决"爆了之后能不能找回来"——是同一枚硬币的两面。

### 3.1 先读报告

`ANALYSIS_REPORT.md` **§4.2「上下文治理 + 五层记忆——先别撑爆，再记住」**（368-450 行）。重点吸收：
- token budget 为什么是一等公民，而不是拍脑袋阈值
- 穿透 `FallbackChatModel` 取真实窗口的意义
- compaction（压缩）vs externalization（外移）的分工
- 五层记忆分层的动机：每一层都可独立测试、独立替换
- Ebbinghaus 衰减、lazy decay（检索时才算强度，无后台任务）
- 为什么记忆注入用 HumanMessage 而不是 system prompt（prompt cache）
- 为什么 state 里只存记忆索引而非全文

### 3.2 源码阅读路径

**上下文治理**（自顶向下）：

| 顺序 | 文件 | 读什么 |
|------|------|--------|
| 1 | `context_engineering/contract.py` | `GovernanceContext / GovernanceResult` 契约 |
| 2 | `context_engineering/strategy_middleware.py` | 把策略翻译成中间件的桥 |
| 3 | `context_engineering/strategies/default/strategy.py` | 主策略：预算计算、窗口穿透、双策略路由 |
| 4 | `strategies/default/budget.py` + `externalizer.py` + `summarizer.py` | 三个子机制 |

**五层记忆**（自顶向下，先看层再进代码）：

| 层 | 文件 | 要点 |
|----|------|------|
| L1 Schema | `memory/types.py`、`memory/schema.py` | `MemoryTrace`（15 字段冻结 dataclass）、5 个原子操作、**工具无 LLM** |
| L2 策略 | `memory/strategies/default/{decay,forget,manager,strategy}.py` | Ebbinghaus 公式、组合遗忘、lazy decay、6 个硬编码决策（A1-F2） |
| L3 存储 | `memory/strategies/default/{store,retriever}.py` | `MarkdownFileStore`（traces.md + `<!-- trace: {id} -->` + YAML frontmatter）、BM25 混合检索、命中回写强化、遗忘过滤 |
| L4 接线 | `memory/{memory_provider,memory_manager,config,worker}.py` + 两个记忆中间件 | 注入、turn_id、bootstrap、`set_memory_config` |
| L5 整合 | `memory/worker.py` + `memory_consolidation_middleware.py` | 非阻塞 `after_model` 提交、daemon 线程 + Queue、错误 log+skip |

### 3.3 练习 3

**3a（必做）**：打开 `memory/strategies/default/_constants.py`，改 Ebbinghaus 衰减参数（如把 decay 调大），跑对话，观察 `traces.md` 里 strength 变化。**再改回来**。

**3b（进阶·改造级核心）**：写一个自定义记忆策略：
1. 读 `memory/strategies/__init__.py` 看策略如何注册
2. 实现一个 `SimpleKeywordStrategy`：检索只用关键词精确匹配（不做 BM25 打分）
3. 在 config 里切到它，跑通，写测试

**验收标准**：
- [ ] 3a：能解释 decay 调大后长期不用的记忆为什么更快被遗忘（公式层面）
- [ ] 3b：`Retriever` 接口无感切换，现有中间件零改动——这正是分层设计的红利，写进笔记
- [ ] 能回答：为什么遗忘判定是"检索时懒计算"而不是后台定时任务？

---

## 4. 阶段 3：三层技能系统（第 3 周 · 前 3~4 天）

### 4.1 先读报告

`ANALYSIS_REPORT.md` **§4.3「三层技能系统——唯一会自己改进自己的模块」**（451-508 行）。核心认知：
- **skill = 研究流程知识包（prompt 注入），tool = 可执行函数**——"如何验证一个信源"是技能，"执行一次搜索"是工具
- 三层职责：L1 存储选择注入 → L2 进化（IVEFocuser 诊断 → LLMMutator 变异 → ScoreDeltaGate 门控 → GitRatchet 回滚）→ L3 评估（执行判定/质量打分/契约检查）
- 四计数器：selections / applied / completions / fallbacks

### 4.2 源码阅读路径

| 顺序 | 文件 | 读什么 |
|------|------|--------|
| 1 | `skill/types.py` | Skill 数据模型 |
| 2 | `skill/store.py` | SQLite 存储 + version DAG（为什么技能要有版本图？） |
| 3 | `skill/selector.py` | 质量过滤 + LLM 混合选择 |
| 4 | `skill/injector.py` + `skill/_ctx.py` | 注入中间件怎么把 skill 放进上下文 |
| 5 | `skill/parser.py` | 技能文件解析（frontmatter + 正文？） |
| 6 | `skill/hub/` + `skill/builtin_skills/` | 36 个内置技能，挑 2 个精读（一个 core、一个 creative） |
| 7 | `skill/evolution/` + `skill/eval/` | 进化闭环四个组件 + 三层评估 |

### 4.3 练习 4：写一个 builtin skill

1. 参照 `skill/hub/` 里现有技能的文件格式，写一个"如何验证引用数据可信度"的技能（或任意你研究领域里的流程知识）
2. 让它在 `/skill search` 中可被发现
3. 跑一次对话验证注入生效（看 journal 的 `skill.select` / `skill.apply` 事件）

**验收标准**：
- [ ] 技能能被检索到并注入
- [ ] 能回答：为什么技能要 version DAG 而不是简单覆盖？进化失败时 GitRatchet 怎么做到回滚？

---

## 5. 阶段 4：多智能体编排 + 进化/评估闭环（第 3 周后 3~4 天）

### 5.1 先读报告

`ANALYSIS_REPORT.md` **§4.4「多智能体编排——黑盒委派 + 共享沙箱」** + **§4.5「进化与评估闭环」**（509-620 行）。核心认知：
- **委派（specialist）**：路由到外部 CLI（pi / codex / claude），独立进程 + 独立 LLM，但共享 Docker 沙箱
- **自拷贝（subagent）**：Poirot 自己的副本，不继承消息历史，但通过 ContextVar 复用父沙箱
- 为什么"共享沙箱"是核心突破：artifact 可跨 agent 传递

### 5.2 源码阅读路径

| 顺序 | 文件 | 读什么 |
|------|------|--------|
| 1 | `multiagent/specialist.py` + `specialist_runtime.py` | 委派实现 |
| 2 | `multiagent/subagent.py` | 自拷贝 + ContextVar 沙箱恢复 |
| 3 | `multiagent/middleware.py` + `sandbox_binder.py` | 挂到主循环的钩子 |
| 4 | `multiagent/evolution/` + `eval/` | MetricMonitor → IVEFocuser → LLMMutator → ScoreDeltaGate → GitRatchet；RuntimeTracker 反馈回路 |

### 5.3 练习 5

读 `tests/v1/unit/multiagent/` 下现有测试（mock 了 specialist），用 pytest 跑通；然后改一个测试的场景参数（如 success_criteria 判定），观察评估结果变化。

**验收标准**：
- [ ] 能画出"委派发起 → 沙箱共享 → 结果回收"的完整时序
- [ ] 能回答：subagent 为什么不继承父消息历史？共享沙箱靠什么机制跨进程/跨 agent 生效？

---

## 6. 阶段 5：沙箱隔离 + MCP 工具生态（第 4 周 · 前 4 天）

### 6.1 先读报告

`ANALYSIS_REPORT.md` **§4.6「沙箱隔离 + MCP 工具生态——执行要安全，安全不能破坏交付」**（621-679 行）。核心认知：
- Local（开发）/ Docker（生产）双 provider 的取舍
- `DockerPathTranslator` 解决什么 bug（容器路径 vs Windows 宿主路径）
- `DockerPathGuard` 为什么必须强制写路径在挂载区（`--rm` 容器内 /tmp 会丢）
- warm pool / idle destroy / 跨进程锁 解决什么运维问题
- MCP 三传输、核心工具启动加载 vs 非核心延迟加载、工具回退链

### 6.2 源码阅读路径

| 顺序 | 文件 | 读什么 |
|------|------|--------|
| 1 | `sandbox/sandbox.py` + `types.py` + `contracts/` | 统一接口 + provider 抽象 |
| 2 | `sandbox/local/` | 最简单实现，先读它建立直觉 |
| 3 | `sandbox/docker/` | 容器生命周期（warm pool / idle destroy / 跨进程锁） |
| 4 | `sandbox/translators/` + `guards/` | 路径翻译 + 写路径白名单 |
| 5 | `mcp/config.py` + `loader.py` + `registry.py` | 配置 → 加载 → 注册 |
| 6 | `mcp/guards/` | credential 脱敏、描述扫描、env 过滤 |

### 6.3 练习 6

1. 读 `.poirot/mcp_servers.yaml`（或 `.env.example` 里的相关配置）理解配置格式
2. 配置一个本地 MCP server（任意可用服务），观察启动日志：核心工具立即加载 vs 非核心工具延迟加载
3. 人为让某工具不可用，观察回退链（如 `web_search` → MCP → 内置 ddg）

**验收标准**：
- [ ] 能在日志中识别三种加载时序
- [ ] 能回答：Docker 模式下不强制写路径白名单会怎样？（试想 `--rm` 容器 + 写在 `/tmp`）

---

## 7. 阶段 6：双 UI 与装配（第 4 周后 3 天）

### 7.1 先读报告

`ANALYSIS_REPORT.md` **§4.7「双 UI 与装配——app → agents 单向依赖的物质化身」**（680 行起）。

### 7.2 源码阅读路径

| 顺序 | 文件 | 读什么 |
|------|------|--------|
| 1 | `app/bootstrap.py` | 装配器：如何把 agents 层组装起来（找"单向依赖"的物理证据） |
| 2 | `app/cli/main.py`（入口，`pyproject.toml:22` 指向它）+ `commands.py` + `registry.py` | 命令注册机制 |
| 3 | `app/tui/app.py` | Textual 全屏 UI 骨架，只看结构 |
| 4 | `app/gateway/` + `services/stream_service.py` | UI 与 agents 之间的流式桥 |

### 7.3 练习 7：给 CLI 加一个 `/stats` 命令

显示当前会话的 token 统计（复用 observability 或 journal 数据）。

**验收标准**：
- [ ] 命令注册、执行、展示全链路跑通
- [ ] 能回答：为什么 UI 层不能直接 import agents 内部模块？单向依赖约束了什么？

---

## 8. 阶段 7：测试策略 + 毕业项目（第 5~6 周）

### 8.1 学会读测试（1 天）

`poirot/backend/tests/v1/` 的目录结构 = 模块结构。选三个看：
- `tests/v1/unit/leader/`（中间件测试怎么 mock 运行时）
- `tests/v1/unit/memory/`（五层记忆测试怎么构造数据）
- `tests/v1/integration/`（端到端怎么跑）

**收获**：测试是模块契约的最精确文档——哪个函数什么输入给什么输出，测试比注释可信。

### 8.2 毕业项目（改造级三合一 + 测试）

把三个阶段练习组合成一次完整改造：

1. **新中间件**：在练习 2 的 TimeItMiddleware 基础上，把耗时统计写入 RunJournal 事件（复用 `journal/events.py`）
2. **新记忆策略**：练习 3b 的 `SimpleKeywordStrategy`，接上统计——检索命中率回传（复用技能模块的 RuntimeTracker 思路）
3. **新技能**：练习 4 的技能，加上"effective_rate 低于阈值时触发进化"的链路（复用 `skill/evolution/`）
4. 为每个改动写测试；跑相关模块全部测试，确认 2400+ 全绿（或只跑改动模块的 subset）

**答辩问题（能讲清就毕业）**：
- 你的中间件为什么用同步钩子而不是异步？挂载顺序为什么选那个位置？
- 你的记忆策略如何与现有注入/遗忘机制协作？lazy decay 对你的策略成立吗？
- 技能进化链路里，哪个组件会调用你的新技能，数据从哪来回哪去？

---

## 附录 A：模块 → 关键文件速查表

| 模块 | 入口/核心文件 | 配套测试目录 |
|------|--------------|-------------|
| 主循环 | `leader/agent.py`（148 行） | `tests/v1/unit/leader/` |
| 中间件装配 | `leader/factory.py:53-165` | `tests/v1/unit/middlewares/` |
| 钩子契约 | `context_engineering/contract.py:69-84` | — |
| 上下文治理 | `context_engineering/strategy_middleware.py` + `strategies/default/` | `tests/v1/unit/context_engineering/` |
| 五层记忆 | `memory/strategies/default/` + `memory/worker.py` | `tests/v1/unit/memory/` |
| 技能 | `skill/{store,selector,injector}.py` | `tests/v1/unit/skill/` |
| 技能进化 | `skill/evolution/` | `tests/v1/unit/skill/evolution/` |
| 技能评估 | `skill/eval/` | `tests/v1/unit/skill/eval/` |
| 多智能体 | `multiagent/{specialist,subagent,middleware}.py` | `tests/v1/unit/multiagent/` |
| 沙箱 | `sandbox/{sandbox.py,local/,docker/}` | `tests/v1/unit/sandbox/` |
| MCP | `mcp/{loader,registry,config}.py` | `tests/v1/unit/mcp/` |
| UI/装配 | `app/bootstrap.py` + `app/cli/` + `app/tui/` | `tests/v1/unit/cli/`、`tests/v1/unit/tui/` |
| 可观测性 | `journal/` + `observability/` | `tests/v1/unit/journal/` |

## 附录 B：调试技巧

| 技巧 | 用法 |
|------|------|
| `/expand` 命令 | 展开上一轮的完整 Thought 文本和工具结果（UI 内置） |
| RunJournal | 线程目录下的结构化事件（`skill.select`、`memory.encode` 等），调试记忆/技能问题第一站 |
| `pytest -k` 定向 | `pytest tests/v1/unit/middlewares -k timeit` 只跑目标测试 |
| 断点 | 中间件是纯 Python 类，在钩子函数里直接 `breakpoint()` |
| 环境变量 | `.env.example` 里有全部配置；`POIROT_SANDBOX_IDLE_TIMEOUT` 这类开关可调可读 |

## 附录 C：环境搭建（第 0 阶段）

```bash
# 1. 虚拟环境（Python 3.12+）
python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"           # 基础 + 测试
pip install -e ".[docker]"        # 需要 Docker 沙箱时

# 2. 配置
cp .env.example .env              # 填 LLM API key（DeepSeek 打底）

# 3. 跑起来（最小验证）
poirot cli                        # CLI 模式（TUI 依赖终端尺寸）
```

**验证成功的标志**：一次完整对话中，日志出现 `skill.select`、`memory.encode`（或 `memory.consolidate`）事件；`.poirot/` 目录出现 `traces.md` 和线程目录。
