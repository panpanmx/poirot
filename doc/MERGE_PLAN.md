# 中间件合并计划（22 → 15）

> **状态**：设计文档，未落地代码（当前代码保持 22 个中间件不动）。目标：按"关注点"合并，纯结构收敛，运行时行为零变化。

## 一、背景

装配点 `poirot/backend/agents/leader/factory.py`（`_build_middlewares`）源码核实：全功能开启共 **22 个中间件**（11 个无条件挂载的骨架 + 11 个参数开关挂载的扩展），横切 5 个生命周期钩子（before/after_agent、before/after_model、wrap_tool_call）。

22 个中间件职责两两不重叠（各对应一个独立关注点），但存在"**同一关注点拆成多个中间件**"的拆分，代价：

- 装配链长，顺序纪律靠 factory.py 一处人工维护（无机器保障，见 ANALYSIS_REPORT §5.2）；
- 同关注点逻辑散落多个文件，一次改动跨文件。

**目标**：按关注点合并 5 组，22 → 15，不改变任何运行时行为。

## 二、现状清单（22）

| 组 | 中间件 | 挂载方式 | 出处 |
|---|---|---|---|
| 骨架（无条件 11） | SystemContext · Title · RunJournal · HelpRequest · DanglingToolCall · ToolCall · Evidence · Stall · Todo · Reflection · Report | 无条件 extend | [factory.py:87-164](poirot/backend/agents/leader/factory.py#L87-L164) |
| 扩展·治理（3） | TaggedContext · MessageNormalizer · StrategyMiddleware | `context_governance` 非空 | [builder.py:33-49](poirot/backend/agents/context_engineering/builder.py#L33-L49) |
| 扩展·技能（3） | SkillInjection · SkillMetrics · SkillActivation | `skill_*` 非空 | [factory.py:90-100](poirot/backend/agents/leader/factory.py#L90-L100) |
| 扩展·记忆（2） | MemoryRecall · MemoryConsolidation | `memory_provider/worker` 非空 | [factory.py:120-141](poirot/backend/agents/leader/factory.py#L120-L141) |
| 扩展·执行（3） | Sandbox · Orchestration · MCP Audit | 各自开关 | [factory.py:105-118](poirot/backend/agents/leader/factory.py#L105-L118) |

## 三、合并方案（M1–M5）

### M1 Title → Report（-1）

TitleMiddleware 全文 17 行，只做一件事：after_agent 写 `metadata.title`（截断 60）[title_middleware.py:12-14](poirot/backend/agents/middlewares/title_middleware.py#L12-L14)。与 ReportMiddleware 同属"run 收尾产物链"（title → evidence → final_report），并入后由 Report 合成时一并写 title。删 `title_middleware.py`。

### M2 HelpRequest + DanglingToolCall → ToolCall（-2）

三者同属"**消息配对维护**"关注点，各自守一个时机：

| 中间件 | hook | 职责 | 配对防线 |
|---|---|---|---|
| ToolCallMiddleware | wrap_tool_call | 工具失败合成 error ToolMessage | 防线③ |
| DanglingToolCallMiddleware | before_model | 扫描历史补悬挂占位 | 防线① |
| HelpRequestMiddleware | wrap_tool_call | 拦截 ask_help 特例（goto=END 暂停 + 格式化） | — |

合并后 ToolCallMiddleware 增加：before_model 悬挂扫描 hook + wrap_tool_call 内 ask_help 分支。**依赖链保留**：暂停（HelpRequest/Stall goto=END）→ 恢复 → 悬挂修补，仍闭环。

### M3 SkillActivation → SkillInjection（-1）

两者挂载开关相同（都跟 `skill_injection_middleware is not None` 绑定，[factory.py:90-100](poirot/backend/agents/leader/factory.py#L90-L100)），同属"技能注入"关注点：SkillActivation before_model 关键词建议（零 LLM）[skill_activation_middleware.py:49-63](poirot/backend/agents/middlewares/skill_activation_middleware.py#L49-L63)，SkillInjection 注入提示词。合并后一个中间件内两个 hook。

### M4 MemoryConsolidation → MemoryRecall（-1）

同属"记忆"关注点：MemoryRecall before_model 召回注入，MemoryConsolidation aafter_model 后台沉淀（daemon 线程 + Queue）。合并后按 `memory_worker` 有无降级（worker 为空则不启动沉淀），挂载开关统一收敛到 memory 配置。

### M5 Stall + Todo + Reflection → ExitGateMiddleware（-2）

三退出闸门本就共享 `_jump_budget`（跳转预算 ≤3），是"组合级治理"的一家人。合并为一个 ExitGateMiddleware，内部保留三个策略对象（参照 ReflectionMiddleware 的 LightReflectionStrategy / SufficiencyStrategy 双策略模式 [reflection_middleware.py:84-125](poirot/backend/agents/middlewares/reflection_middleware.py#L84-L125)）：

- **StallStrategy**：卡死三信号（能力耗尽 / 错误重复 / Todo 停滞）+ 暂停与强制收尾
- **TodoStrategy**：完成度强制 + Nag 双阈值
- **ReflectionStrategy**：充分性判定（default 恒放行 / expert 充分性）

## 四、合并后清单（15）

| 组 | 中间件 | 数量 |
|---|---|---|
| 骨架（无条件） | SystemContext · RunJournal · **ToolCall(+HelpRequest+Dangling)** · Evidence · **ExitGate(Stall+Todo+Reflection)** · **Report(+Title)** | 6 |
| 扩展·治理 | TaggedContext · MessageNormalizer · StrategyMiddleware | 3 |
| 扩展·技能 | **SkillInjection(+Activation)** · SkillMetrics | 2 |
| 扩展·记忆 | **Memory(+Consolidation)** | 1 |
| 扩展·执行 | Sandbox · Orchestration · MCP Audit | 3 |

**15 = 6 必须 + 9 可选。**

## 五、取舍与风险

| 取舍 | 说明 | 缓解 |
|---|---|---|
| 失去"一中间件一文件"的独立测试粒度 | 测试文件需合并，2400+ 用例分组调整 | 类内策略对象拆分（M5），测试按策略分组保留 |
| 失去部分独立摘除能力 | 合并后同文件内策略仍可开关 | 策略对象构造参数化（对齐 expert_mode 参数化传统） |
| 顺序纪律仍无机器保障 | 装配项 22→15，人工维护面变小但未根除 | 另案：中间件依赖声明 + 拓扑排序（ANALYSIS_REPORT §6.1 P1-7） |
| 行为零变化要求 | 合并是结构收敛，任何行为漂移 = 失败 | 验收：全量测试 + 一次真实对话对照 |

## 六、验收

1. `pytest` 全量 2400+ 用例全绿（行为不变）
2. factory.py 装配点从 22 项收敛为 15 项，diff 可审
3. 一次真实研究对话前后对照：标题 / 报告 / 暂停恢复 / 退出闸门行为一致

## 出处

- 装配点：[factory.py:53-164](poirot/backend/agents/leader/factory.py#L53-L164)
- 治理层组装：[builder.py:33-49](poirot/backend/agents/context_engineering/builder.py#L33-L49)
- Title：[title_middleware.py:12-14](poirot/backend/agents/middlewares/title_middleware.py#L12-L14)
- HelpRequest 拦截：[help_request_middleware.py:49-53](poirot/backend/agents/middlewares/help_request_middleware.py#L49-L53)
- Dangling 修补：[dangling_tool_call_middleware.py:52-79](poirot/backend/agents/middlewares/dangling_tool_call_middleware.py#L52-L79)
- SkillActivation 开关：[factory.py:94-100](poirot/backend/agents/leader/factory.py#L94-L100)
- 记忆双挂载：[factory.py:120-141](poirot/backend/agents/leader/factory.py#L120-L141)
- 三闸门装配：[factory.py:155-160](poirot/backend/agents/leader/factory.py#L155-L160)
- 双策略模式：[reflection_middleware.py:84-125](poirot/backend/agents/middlewares/reflection_middleware.py#L84-L125)
- 顺序纪律无机器保障：[doc/ANALYSIS_REPORT.md §5.2](doc/ANALYSIS_REPORT.md)
