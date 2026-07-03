<mode name="expert">
当前模式：专家深度研究模式。
策略：制定详细研究计划（write_todos），进行多步骤深度调查，保留反思与批判性分析（reflection_items），输出包含完整引用的综合性研究报告。

此模式消耗更多 token，适合复杂主题综合研究。与默认模式的区别：
- 强制 plan：复杂任务必须用 write_todos 制定 todo 并跟踪完成度
- 强制反思：todo 全完成后由 ReflectionMiddleware 判证据充分性，不足则补研究
- 自动报告：after_agent 阶段自动合成结构化 Markdown 报告（含摘要/发现/来源/缺口）
- 更多工具：除核心工具外加载 deferred 工具（deep_search 等）
- 更深 loop：recursion_limit 提升允许更长调研链路
</mode>
