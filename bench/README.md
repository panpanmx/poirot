# Poirot 量化成果评测（bench）

为简历量化的四组 benchmark。**只写评测脚本，零生产代码改动**（import 内部接口驱动，
范式同 `tests/v1/integration/test_minimum_agent_loop.py`）。

## 环境

```bash
conda activate poirot        # 必须——含 langchain_deepseek 等依赖
cd <项目根>                   # compaction.jsonl 相对 CWD 硬编码，必须从项目根跑
pip install huggingface_hub   # 仅 A 需要（GAIA 下载）
```

**必须用 `python -m bench.xxx.yyy` 运行**（不能用 `python bench/xxx/yyy.py`）——
脚本模式会把脚本目录（而非项目根）放进 sys.path[0]，`import bench.common` 会失败。

`.env` 需有 `DEEPSEEK_API_KEY`（已配）。GitHub/HF 走代理 `127.0.0.1:7897`（自动注入，
失败备选 hf-mirror.com）。

**GAIA 是 gated 数据集**：先用 HF 账号在
`https://huggingface.co/datasets/gaia-benchmark/GAIA` 点 "Agree and access" 同意条款，
再到 Settings → Access Tokens 生成 read token，写入 `.env`：`HF_TOKEN=hf_xxx`。

## 四组评测

| 目录 | 主题 | 产出 | 状态 |
|---|---|---|---|
| [a_gaia](a_gaia/) | 业界基准 GAIA validation 165 题 | 准确率/分层/成本/耗时 | 冒烟→全量 |
| [b_governance](b_governance/) | 上下文治理对照 | 压缩率/外化/熔断/无损性 | 待跑 |
| [c_skill](c_skill/) | Skill 自进化 | L1 4 率 / L3 评测 / 进化前后差 | 待跑 |
| [d_multiagent](d_multiagent/) | 多 Agent 编排对照 | 委派率/连续性/单vs多 | 待跑 |

## 运行顺序

```bash
# 0) 冒烟（半天）：验证全链路
python -m bench.a_gaia.download_data           # 一次性：拉数据集+附件
python -m bench.a_gaia.run_gaia --limit 5      # 链路冒烟
python -m bench.a_gaia.judge --no-llm && python -m bench.a_gaia.score_gaia

python -m bench.b_governance.run_gov_experiment --smoke && python -m bench.b_governance.analyze_gov
python -m bench.c_skill.build_task_set && python -m bench.c_skill.run_skill_bench --smoke && python -m bench.c_skill.analyze_skill
python -m bench.d_multiagent.build_tasks && python -m bench.d_multiagent.run_multiagent_bench --smoke && python -m bench.d_multiagent.analyze_multiagent

# 1) 正式（后台并行；A 最长 3-8h）
python -m bench.a_gaia.run_gaia && python -m bench.a_gaia.judge && python -m bench.a_gaia.score_gaia
python -m bench.b_governance.run_gov_experiment && python -m bench.b_governance.analyze_gov
python -m bench.c_skill.build_task_set && python -m bench.c_skill.run_skill_bench --phase baseline
python -m bench.c_skill.run_evolution          # run_cycle + 必要时手动 FIX
python -m bench.c_skill.run_skill_bench --phase post && python -m bench.c_skill.analyze_skill
python -m bench.d_multiagent.build_tasks && python -m bench.d_multiagent.run_multiagent_bench && python -m bench.d_multiagent.analyze_multiagent
```

所有 runner 支持 `--resume`（断点续跑）。产物在 `bench/data/runs/*/`（gitignore）。

## 关键机制与口径（简历引用前必读）

- **GAIA 评分**：双通道 = LLM judge×2 严格多数（deepseek，temperature=0）+ 规则严格匹配
  下界；争议题导出人工复核。准确率以 LLM judge 为主口径，规则通道为可复现背书。
- **治理对照矩阵**：{开,关} × {缩窗 8k, 默认窗口}。缩窗使 P1@3.2k/P4@6.4k/P5@7.2k
  全程触发（成本降 ~20×）；默认窗口（动态解析 200k）组为"治理不空转"对照。
  无损性 = 开/关治理子任务完成率差（TASK 标记自动判定）。
- **Skill 口径**：只测启动自动激活的 12 个 core skill；三类口径——
  tool-covered（allowed_tools 可用，applied 可判定）/ guidance（无 allowed_tools，
  只打 selections）/ tool-uncovered（有 allowed_tools 但 runtime 无对应工具，
  applied=False 诚实归因）。L3 = ResponseContractChecker（规则）+ TaskQualityJudge
  （4 维加权 0.50/0.35/0.05/0.10，deepseek）。
- **多 Agent**：委派计数器来自隔离 `multiagent.db`（POIROT_MULTIAGENT_DB_PATH）；
  leaf 探针验证 subagent 无 delegate 工具（防递归）。委派决策完全交给模型
  （任务文本不含"用 subagent"字样）。
- **成本估算**：deepseek 近似单价 input $0.27/M + output $1.10/M，标注为估算值。

## 简历口径提醒

探索发现"15 个中间件（6+9）"是 MERGE_PLAN 设计目标，代码实测 **22 个中间件**——
简历按实测口径写。
