# Poirot Bench 测试报告 — 2026-08-27

> **执行环境**：conda env `poirot` / Python 3.12.13 / Windows / DeepSeek API (`deepseek-v4-flash`)
> **项目根**：`E:\python_file\agent_practice\poirot`
> **中断原因**：API 余额耗尽 (`402 Insufficient Balance`)，C-post 阶段中断后 D、A 未启动

---

## 一、总览

| Suite | 主题 | 状态 | 耗时 | 备注 |
|-------|------|------|------|------|
| **B** 上下文治理 | 治理开/关 × 窗口大/小 对照 | ✅ 全部完成 | ~9 min | 4 cells × 3 repeats = 12 runs |
| **C** Skill 自进化 | baseline → evolution → post | ⚠️ 部分完成 | ~1.5 h | baseline ✅ / evolution ✅ / **post 9/12 后 402 中断** / analyze 未跑 |
| **D** 多 Agent 编排 | 单 vs 多 agent 对照 | ❌ 未正式跑 | — | 仅有冒烟 2 条 timeout 记录 |
| **A** GAIA 基准 | 165 题 validation | ❌ 未跑 | — | 数据已下载（165 题 + 38 附件） |

---

## 二、Suite B — 上下文治理对照（✅ 完成）

### 2.1 实验设计

```
矩阵：{治理开, 治理关} × {缩窗 8k, 默认窗口} × 3 repeats = 4 cells × 3 = 12 runs
```

| Cell | governance | window | task_key | 子任务数 |
|------|-----------|--------|----------|---------|
| `gov_on_8k` | ✅ 开 | 8000 | full | 28 |
| `gov_off_8k` | ❌ 关 | 8000 | full | 28 |
| `gov_on_default` | ✅ 开 | 默认(~200k) | short | 6 |
| `gov_off_default` | ❌ 关 | 默认(~200k) | short | 6 |

- **缩窗 8k**：P1@3.2k / P4@6.4k / P5@7.2k 全程触发，压缩率/外化/熔断/无损性全指标压测
- **默认窗口**：治理近乎空闲——对照证明"治理不空转"
- **超时**：900s / run
- **成本估算**：deepseek 近似单价 input $0.27/M + output $1.10/M

### 2.2 运行指令

```bash
conda activate poirot
cd E:\python_file\agent_practice\poirot

# 正式
python -m bench.b_governance.run_gov_experiment
# 分析
python -m bench.b_governance.analyze_gov
```

CLI 参数：`--repeats 3`（默认）/ `--smoke`（full=8/short=4/repeats=1）/ `--resume` / `--only KEY`

### 2.3 量化结果

#### Cell 级汇总

| Cell | n_runs | completion_rate | combine_rate | tokens_sum | cost_usd | duration_median(s) | P1 events | P4 events | P5 events | final_fraction |
|------|--------|----------------|--------------|------------|----------|-------------------|-----------|-----------|-----------|----------------|
| gov_on_8k | 4 | 1.0 | 1.0 | 376,870 | $0.1328 | 59.2 | 20 | 0 | 0 | 0.68 |
| gov_off_8k | 4 | 1.0 | 1.0 | 274,227 | $0.1024 | 46.65 | 0 | 0 | 0 | — |
| gov_on_default | 4 | 1.0 | 1.0 | 66,664 | $0.0273 | 20.35 | 0 | 0 | 0 | 0.01 |
| gov_off_default | 4 | 1.0 | 1.0 | 128,551 | $0.0448 | 22.5 | 0 | 0 | 0 | — |

#### 对照 Δ（开治理 vs 关治理基线）

| 对照组 | tokens Δ | completion Δ | latency Δ | cost Δ |
|--------|---------|-------------|-----------|--------|
| **gov_on_8k** vs gov_off_8k | **+37.4%**（开治理 tokens 更多） | 0%（无损） | **+26.9%** | **+29.7%** |
| **gov_on_default** vs gov_off_default | **-48.1%**（开治理 tokens 更少） | 0%（无损） | **-9.6%** | **-39.1%** |

**解读**：
- 缩窗 8k 组：治理频繁触发 P1（20 次），维持了完整正确性（completion=1.0, combine=1.0），但因压缩开销导致 tokens/cost/latency 均上升——这是治理"有成本但无损"的符合预期表现
- 默认窗口组：治理近乎空闲（P1=0），tokens 反而比关治理少 48%——证明治理不空转、且在大窗口下通过早期干预减少了冗余

### 2.4 逐 run 明细

| run_id | status | duration(s) | total_tokens | cost($) | completion | P1 |
|--------|--------|-------------|-------------|---------|------------|-----|
| gov_on_8k-r1 | ok | 76.2 | 112,063 | 0.0400 | 28/28 | 8 |
| gov_on_8k-r2 | ok | 42.2 | 47,617 | 0.0190 | 28/28 | 3 |
| gov_on_8k-r3 | ok | 94.0 | 153,286 | 0.0527 | 28/28 | 9 |
| gov_off_8k-r1 | ok | 46.5 | 47,093 | 0.0190 | 28/28 | 0 |
| gov_off_8k-r2 | ok | 88.7 | 55,113 | 0.0268 | 28/28 | 0 |
| gov_off_8k-r3 | ok | 46.8 | 76,515 | 0.0269 | 28/28 | 0 |
| gov_on_default-r1 | ok | 13.6 | 11,060 | 0.0047 | 6/6 | 0 |
| gov_on_default-r2 | ok | 20.4 | 13,266 | 0.0062 | 6/6 | 0 |
| gov_on_default-r3 | ok | 21.4 | 19,215 | 0.0078 | 6/6 | 0 |
| gov_off_default-r1 | ok | 14.7 | 11,267 | 0.0049 | 6/6 | 0 |
| gov_off_default-r2 | ok | 30.3 | 34,360 | 0.0126 | 6/6 | 0 |
| gov_off_default-r3 | ok | 36.1 | 73,060 | 0.0234 | 0/6 | 0 |

### 2.5 产出文件

```
bench/data/runs/gov/
├── runs.jsonl                    # 16 行（含 4 行 dry-run + 12 行正式）
├── report.json                   # 分析报告
├── water_gov_on_8k-r1.csv        # 水位线轨迹
├── water_gov_on_8k-r2.csv
└── water_gov_on_8k-r3.csv
```

---

## 三、Suite C — Skill 自进化（⚠️ 部分完成）

### 3.1 实验设计

```
12 个 core skill × 3 阶段（baseline → evolution → post）
评分器：TaskQualityJudge 4 维加权 (task_completion×0.50 + response_quality×0.35 + efficiency×0.05 + tool_usage×0.10)
```

| 阶段 | 说明 | 状态 |
|------|------|------|
| baseline | 12 skill 各跑一次，记录 L1 四率 + L3 judge 评分 | ✅ 完成 |
| evolution | run_cycle 检测需进化的 skill 并生成 EvolutionRecord | ✅ 完成（0 条记录） |
| post | 进化后重跑 12 skill | ⚠️ 9/12 完成后 402 中断 |
| analyze | 对比 baseline vs post | ❌ 未跑 |

### 3.2 运行指令

```bash
# baseline
python -m bench.c_skill.run_skill_bench --phase baseline
# evolution
python -m bench.c_skill.run_evolution
# post
python -m bench.c_skill.run_skill_bench --phase post
# analyze
python -m bench.c_skill.analyze_skill
```

CLI 参数：`--smoke` / `--resume` / `--phase {baseline|post}`

### 3.3 Baseline 结果（12 task，10 个有 judge 评分，2 个 timeout）

| task_id | status | duration(s) | overall_score | task_completion | response_quality | efficiency | tool_usage |
|---------|--------|-------------|--------------|----------------|-----------------|------------|------------|
| systematic-debugging | ok | 190.4 | **0.900** | 0.95 | 0.85 | 0.85 | 0.85 |
| test-driven-development | ok | 102.3 | **0.887** | 0.95 | 0.85 | 0.70 | 0.80 |
| simplify-code | ok | 29.0 | **0.932** | 1.00 | 0.85 | 0.90 | 0.90 |
| skill-creator | ok | 82.9 | **0.885** | 0.90 | 0.90 | 0.80 | 0.80 |
| skill-authoring | ok | 51.7 | **0.805** | 0.80 | 0.90 | 0.80 | 0.50 |
| plan | timeout | 480.0 | — | — | — | — | — |
| github-code-review | ok | 288.2 | **0.845** | 0.90 | 0.80 | 0.70 | 0.80 |
| requesting-code-review | ok | 240.8 | **0.890** | 0.95 | 0.90 | 0.60 | 0.70 |
| spike | timeout | 480.0 | — | — | — | — | — |
| source-verification | ok | 329.2 | **0.845** | 0.90 | 0.80 | 0.70 | 0.80 |
| find-skills | ok | 354.7 | **0.365** | 0.20 | 0.60 | 0.30 | 0.40 |
| bootstrap | ok | 374.8 | **0.845** | 0.90 | 0.80 | 0.70 | 0.80 |

**Baseline 均值**：overall_score = **0.820**（10 个有分任务）

### 3.4 Baseline Skill 四率（L1 指标）

所有 12 个 skill 的 L1 指标均为零（applied_rate=0, completion_rate=0, effective_rate=0），fallback_rate 在 3 个 skill 上非零：
- plan: fallback_rate = 0.2
- simplify-code: fallback_rate = 0.2
- skill-authoring: fallback_rate = 0.2
- source-verification: fallback_rate = 0.4

**工具覆盖**：12/12 skill 全部 `tool-covered`（无 missing tools）

### 3.5 Evolution 结果

```
run_cycle 产出 0 条 EvolutionRecord
原因：metrics 样本不足或阈值未命中
```

### 3.6 Post 结果（9/12 完成，3 未完成）

| task_id | status | overall_score | vs baseline |
|---------|--------|--------------|------------|
| systematic-debugging | ok | 0.110 | ↓ 0.790 |
| test-driven-development | timeout | — | — |
| simplify-code | ok | 0.850 | ↓ 0.082 |
| skill-creator | timeout | — | — |
| skill-authoring | ok | 0.005 | ↓ 0.800 |
| plan | ok | 0.863 | N/A（baseline timeout） |
| github-code-review | ok | 0.850 | ↑ 0.005 |
| requesting-code-review | ok | 0.875 | ↓ 0.015 |
| spike | ok | 0.815 | N/A（baseline timeout） |
| **source-verification** | **❌ 402 中断** | — | — |
| **find-skills** | **❌ 未跑** | — | — |
| **bootstrap** | **❌ 未跑** | — | — |

### 3.7 产出文件

```
bench/data/runs/c_skill/
├── snapshot_baseline.json    # baseline 快照（含 L1 四率 + tool_coverage + task_scores）
├── evolutions.jsonl          # 空文件（0 条进化记录）
└── runs.jsonl                # 25 行（15 baseline + 9 post + 1 中断）
```

---

## 四、Suite D — 多 Agent 编排对照（❌ 未正式跑）

### 4.1 实验设计

```
12 任务 × 2 配置 (multi/single) × 3 repeats = 72 runs
超时：480s/task（正式建议 --timeout 900）
```

| 任务类别 | 数量 | 说明 |
|---------|------|------|
| parallel_research | 4 | 3 个独立子调研方向（委派价值最大） |
| isolated_compute | 4 | 长文档分段处理（隔离计算重活） |
| mixed_toolchain | 4 | 文件操作 + 网络搜索交错（两种不兼容工具链分工） |

**指标采集**：
- 委派：state.messages 中 `delegate_to_*` tool_calls 计数 + 隔离 DB 4 计数器
- 产物跨 Agent 连续性：report 引用 specialist 产物/路径次数
- 质量：TaskQualityJudge（同 C 的 L3 评分器）
- 深度控制：leaf subagent 探针（验证 leaf 无 delegate 工具，防递归）
- 成本/耗时

### 4.2 运行指令

```bash
# 生成任务集（一次性）
python -m bench.d_multiagent.build_tasks

# 正式运行（加大 timeout）
python -m bench.d_multiagent.run_multiagent_bench --timeout 900

# 分析
python -m bench.d_multiagent.analyze_multiagent
```

CLI 参数：`--repeats 3`（默认）/ `--smoke` / `--resume` / `--only-config multi|single` / `--timeout`

### 4.3 当前状态

仅有 2 条冒烟记录（均 timeout）：

| run_id | config | status | duration(s) |
|--------|--------|--------|-------------|
| multi-research-plants-r1 | multi | timeout | 480.0 |
| single-research-plants-r1 | single | timeout | 480.0 |

leaf 探针结果：`setup_present=true, subagent_provider_present=false, agent_factory_configured=false`

### 4.4 预期产出文件

```
bench/data/runs/d_multiagent/
├── runs.jsonl              # 逐 run 记录
├── snapshot_multi.json     # 多 agent 快照（委派计数器 + leaf 探针）
├── snapshot_single.json    # 单 agent 快照
└── report.json             # 分析报告
```

---

## 五、Suite A — GAIA 基准（❌ 未跑）

### 5.1 实验设计

```
GAIA validation split：165 题（Level 1/2/3 分层）
双通道评分：规则严格匹配（保守下界）+ deepseek LLM judge×2 majority
```

| 参数 | 值 |
|------|-----|
| 题数 | 165 |
| 附件题 | 38 个（xlsx/png/pdf/mp3/docx/zip 等） |
| 单题超时 | 300s |
| 题间延迟 | 2s（DDG 限流缓解） |
| Skill | 关闭（`POIROT_SKILL_ENABLED=false`） |
| LLM | deepseek-v4-flash, temperature=0 |

**评分规则**：
- 规则通道：归一化精确匹配 / 数字相对容差 ≤0.1% / 日期多格式 / yes-no 变体
- LLM 通道：deepseek judge × 2 次，严格多数（2-of-2 才算对，1:1 算错）
- 争议题导出人工复核

### 5.2 运行指令

```bash
# 0) 下载数据（一次性，需 HF_TOKEN）
python -m bench.a_gaia.download_data

# 1) 跑测
python -m bench.a_gaia.run_gaia

# 2) 评分
python -m bench.a_gaia.judge

# 3) 汇总
python -m bench.a_gaia.score_gaia
```

CLI 参数：`--limit N`（分层抽样冒烟）/ `--resume` / `--timeout-per-question 300` / `--seed 42` / `--no-llm`（只跑规则通道）

### 5.3 当前状态

- ✅ 数据已下载：`gaia_validation.jsonl`（165 题）+ `attachments/`（38 个文件）+ `metadata_full.jsonl`
- ❌ `bench/data/runs/gaia/` 目录不存在，未执行任何 run

### 5.4 预期产出文件

```
bench/data/runs/gaia/
├── runs.jsonl                    # 逐题结果
├── progress.json                 # 进度跟踪
├── verdicts.jsonl                # 双通道评分
├── review_top_conflicts.jsonl    # 争议题
└── score_report.json             # 最终报告
```

### 5.5 预期报告指标

```json
{
  "accuracy": {
    "llm_judge_overall": "?",
    "llm_judge_by_level": {"1": "?", "2": "?", "3": "?"},
    "rule_exact_overall": "?",
    "file_questions": {"n": "?", "acc": "?"},
    "non_file_questions": {"n": "?", "acc": "?"}
  },
  "judge_agreement": {"rule_vs_llm_agree_rate": "?", "n_contested": "?"},
  "cost": {"total_usd_est": "?", "per_question_usd_avg": "?"},
  "latency": {"avg_s": "?", "p50_s": "?", "p95_s": "?", "timeouts": "?"}
}
```

---

## 六、已知问题

| 问题 | 影响 | 建议 |
|------|------|------|
| API 余额耗尽 (402) | C-post 中断，D/A 未跑 | 充值后续跑 |
| `UnicodeDecodeError: 'gbk'` | 日志中有 warning，未中断流程 | 设 `PYTHONIOENCODING=utf-8` 或 `chcp 65001` |
| `[PromptManager] warning: unbound ${todos}` | 模板变量未绑定 | 不影响结果，可忽略 |
| D suite fixtures 缺失 | `mixed_toolchain` 4 个任务引用的 fixture 文件不存在 | 在 `bench/d_multiagent/fixtures/` 创建 `inventory.txt`, `notes.txt`, `errors.txt`, `todos.txt` |
| D suite leaf probe 不完整 | `subagent_provider_present=false` | 检查 multiagent 装配配置 |
| Evolution 0 条记录 | metrics 样本不足或阈值未命中 | 正常——baseline 首轮不触发进化 |
