# 续跑指令 — Gemini 换跑手册

> 本文档列出所有未完成测试的精确指令、前置条件和预期产出，
> 供 Gemini（或其他 LLM agent）接手续跑。

---

## 〇、环境准备

```bash
# 1. 激活 conda 环境
conda activate poirot

# 2. 切到项目根（必须！脚本依赖 CWD）
cd E:\python_file\agent_practice\poirot

# 3. 确认 .env 有以下变量：
#    DEEPSEEK_API_KEY=sk-xxx        ← 需充值后有效
#    HF_TOKEN=hf_xxx                ← GAIA 数据集（已下载可跳过）
#    DEEPSEEK_MODEL=deepseek-v4-flash

# 4. (可选) 解决 Windows 编码问题
set PYTHONIOENCODING=utf-8
chcp 65001
```

**注意**：所有命令必须用 `python -m bench.xxx.yyy` 格式运行，不能用 `python bench/xxx/yyy.py`。

---

## 一、C Suite 续跑（~30 min）

### 状态
- ✅ baseline 12/12 完成
- ✅ evolution 完成（0 条记录）
- ⚠️ post 9/12 完成（source-verification 中断，find-skills / bootstrap 未跑）
- ❌ analyze 未跑

### 续跑指令

```bash
# 1. 续跑 post（--resume 跳过已完成的 9 个）
python -m bench.c_skill.run_skill_bench --phase post --resume

# 2. 分析
python -m bench.c_skill.analyze_skill
```

### 预期效果
- `--resume` 会读取 `bench/data/runs/c_skill/runs.jsonl`，跳过已有的 9 条 post 记录
- 只需跑 3 个任务：source-verification、find-skills、bootstrap
- analyze 产出 `bench/data/runs/c_skill/report.json`

### 已完成的 post 数据（在 runs.jsonl 中）

| task_id | status | overall_score |
|---------|--------|--------------|
| post-task-systematic-debugging | ok | 0.110 |
| post-task-test-driven-development | timeout | — |
| post-task-simplify-code | ok | 0.850 |
| post-task-skill-creator | timeout | — |
| post-task-skill-authoring | ok | 0.005 |
| post-task-plan | ok | 0.863 |
| post-task-github-code-review | ok | 0.850 |
| post-task-requesting-code-review | ok | 0.875 |
| post-task-spike | ok | 0.815 |

---

## 二、D Suite 正式跑（~2-4 h）

### 状态
- tasks.json 已生成（12 任务）
- 仅有 2 条冒烟 timeout 记录
- ⚠️ `bench/d_multiagent/fixtures/` 目录下的 4 个文件可能不存在，需检查

### 前置检查

```bash
# 检查 fixtures 是否存在
ls bench/d_multiagent/fixtures/
# 如果不存在，需要创建：
# inventory.txt, notes.txt, errors.txt, todos.txt
# （内容任意，mixed_toolchain 类任务会读取）
```

### 续跑指令

```bash
# 清除冒烟数据（可选，或用 --resume 累加）
# 如果想从头跑，删除旧数据：
# del bench\data\runs\d_multiagent\runs.jsonl

# 正式运行（加大 timeout 到 900s）
python -m bench.d_multiagent.run_multiagent_bench --timeout 900

# 分析
python -m bench.d_multiagent.analyze_multiagent
```

### 参数说明
- `--timeout 900`：每个 run 超时 900s（默认 480s 导致冒烟全部 timeout）
- `--repeats 3`：默认 3 次重复
- `--resume`：断点续跑
- `--only-config multi|single`：只跑某一配置

### 预期规模
- 12 任务 × 2 配置 × 3 repeats = **72 runs**
- 每 run 含 LLM judge 评分调用
- 预计耗时 2-4 小时

### 预期产出
```
bench/data/runs/d_multiagent/
├── runs.jsonl              # 72 行
├── snapshot_multi.json     # 委派计数器 + leaf 探针
├── snapshot_single.json
└── report.json             # 对照分析
```

### 关键指标
- `delegate_calls`：多 agent 配置的委派调用次数
- `judge_score`：TaskQualityJudge 质量分（4 维加权）
- `continuity`：产物跨 agent 连续性引用次数
- 单 vs 多：质量/延迟/成本 Δ%

---

## 三、A Suite — GAIA 基准（~3-8 h）

### 状态
- ✅ 数据已下载（165 题 + 38 附件）
- ❌ 未执行任何 run

### 续跑指令

```bash
# 1. 跑测（165 题，每题最多 300s）
python -m bench.a_gaia.run_gaia

# 2. 双通道评分
python -m bench.a_gaia.judge

# 3. 汇总报告
python -m bench.a_gaia.score_gaia
```

### 参数说明
- `--limit N`：分层抽样 N 题（冒烟用，如 `--limit 5`）
- `--resume`：断点续跑（**强烈建议**，GAIA 165 题跑到一半中断可续）
- `--timeout-per-question 300`：单题超时（默认 300s）
- `--delay-between 2`：题间延迟（DDG 限流缓解）
- `--no-llm`：只跑规则通道（零成本，调试用）

### 预期规模
- 165 题 × 300s 上限 ≈ **最长 13.75 h**（实际 3-8 h，多数题不到 300s）
- 每题 1 次 LLM 调用 + judge 阶段 2 次额外调用
- 估计总 API 成本 ~$2-5

### 预期产出
```
bench/data/runs/gaia/
├── runs.jsonl                    # 165 行
├── progress.json                 # 进度
├── verdicts.jsonl                # 双通道评分
├── review_top_conflicts.jsonl    # 争议题
└── score_report.json             # 最终报告
```

### 关键指标
- `llm_judge_overall`：LLM judge 总准确率（**主报告口径**）
- `llm_judge_by_level`：Level 1/2/3 分层准确率
- `rule_exact_overall`：规则严格匹配下界（可复现背书）
- `rule_vs_llm_agree_rate`：双通道一致率
- `per_question_usd_avg`：每题平均成本

---

## 四、推荐执行顺序

```bash
# 1. 先跑最快的 C 续跑（~30 min）
python -m bench.c_skill.run_skill_bench --phase post --resume
python -m bench.c_skill.analyze_skill

# 2. 再跑 D 正式（~2-4 h）
python -m bench.d_multiagent.run_multiagent_bench --timeout 900
python -m bench.d_multiagent.analyze_multiagent

# 3. 最后跑 A GAIA（~3-8 h）
python -m bench.a_gaia.run_gaia --resume
python -m bench.a_gaia.judge
python -m bench.a_gaia.score_gaia
```

### 一键脚本（Windows bat）

```bat
@echo off
chcp 65001 >nul
set PYTHON=E:\software\anaconda\envs\poirot\python.exe
set PYTHONIOENCODING=utf-8

echo === C Suite resume ===
"%PYTHON%" -m bench.c_skill.run_skill_bench --phase post --resume
"%PYTHON%" -m bench.c_skill.analyze_skill

echo === D Suite ===
"%PYTHON%" -m bench.d_multiagent.run_multiagent_bench --timeout 900
"%PYTHON%" -m bench.d_multiagent.analyze_multiagent

echo === A Suite (GAIA) ===
"%PYTHON%" -m bench.a_gaia.run_gaia --resume
"%PYTHON%" -m bench.a_gaia.judge
"%PYTHON%" -m bench.a_gaia.score_gaia

echo === ALL DONE ===
pause
```

---

## 五、API 成本估算

| Suite | 预计 token 消耗 | 预计成本 (deepseek) |
|-------|----------------|-------------------|
| C post 续跑（3 task） | ~2-5M tokens | ~$0.5-2 |
| D 正式（72 runs） | ~50-100M tokens | ~$5-15 |
| A GAIA（165 题） | ~100-200M tokens | ~$10-30 |
| **合计** | | **~$15-50** |

> 成本按 deepseek-chat 近似单价：input $0.27/M + output $1.10/M
> 实际成本取决于每个 run 的 token 消耗量变化

---

## 六、故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `402 Insufficient Balance` | API 余额不足 | 充值后重跑（加 `--resume`） |
| `UnicodeDecodeError: 'gbk'` | Windows 默认 GBK 编码 | `set PYTHONIOENCODING=utf-8` + `chcp 65001` |
| `ModuleNotFoundError: bench.common` | 没用 `-m` 方式运行 | 改用 `python -m bench.xxx.yyy` |
| 全部 timeout | timeout 太短 | 加 `--timeout 900` 或更大 |
| `[error] 缺任务集` | 未生成 tasks.json | 先跑 `python -m bench.d_multiagent.build_tasks` |
| GAIA `HF_TOKEN` 缺失 | 未配置 HF token | `.env` 加 `HF_TOKEN=hf_xxx` |
| fixtures 文件不存在 | D suite mixed_toolchain 任务需要的文件 | 在 `bench/d_multiagent/fixtures/` 创建 4 个 txt 文件 |
