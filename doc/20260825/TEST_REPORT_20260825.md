# poirot 全量测试执行报告（2026-08-25）

## 1. 执行概要

| 项目 | 内容 |
|---|---|
| 执行日期 | 2026-08-25（两次全量，结果一致） |
| 环境 | conda env `poirot`（E:\software\anaconda\envs\poirot，Python 3.12.13） |
| 工作目录 | e:\python_file\agent_practice\poirot（项目根） |
| 命令 | `python -m pytest -q --tb=short`（另跑一次 `--durations=10 -rs` 采样） |
| 测试收集 | 2720 个（unit 2685 / integration 35） |
| 执行结果 | **2704 通过 / 4 跳过 / 14 失败** |
| 总耗时 | 49.68s / 52.20s（两次） |

## 2. 总体结果

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 收集 2720 │ → │ 通过 2704 │ → │ 跳过 4   │ → │ 失败 14  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
    99.4%          0.15%          0.51%
```

**结论：仓库当前非绿（14 失败），但失败全部为已知类型（环境伪影 / 仓库断言过期 / 顺序污染），无业务代码缺陷暴露；与 2026-08-24 基线（2704/4/14）完全一致，无新增失败。**

## 3. 失败明细（14 个，分 4 类）

### 3.1 断言过期（仓库遗留，2 个）

| 用例 | 断言 | 实际 | 根因 |
|---|---|---|---|
| config/test_config_loader.py::test_expert_mode_true_activates_profile | `max_loop_steps == 8` | **100** | 代码 EXPERT_PROFILE 已改 100，测试未跟随；profiles/*.yaml 为废弃遗留 |
| sandbox/test_merge_sandbox.py::test_initial_state_field_count | state 字段集合 | 多出 `memory_updates`、`recalled_memories` | 代码新增记忆字段，断言未跟随 |

### 3.2 模板语言漂移（1 个）

| 用例 | 断言 | 实际 | 根因 |
|---|---|---|---|
| context_engineering/test_default_strategy.py::test_call_llm_uses_prompt_template | 模板含"对话历史" | 模板已英文化（"Conversation to Compress"） | 模板语言改动后断言未同步 |

### 3.3 会话环境伪影（6 个）

| 用例 | 根因 |
|---|---|
| multiagent/test_claude_credential.py × 6（oauth future/expired/access_token/empty/invalid_json/non_dict） | Claude Code 会向子进程注入 `ANTHROPIC_AUTH_TOKEN` 环境变量，6 个用例未清理该变量导致失败；普通终端（无该变量）下 18/18 通过 |

### 3.4 顺序依赖污染（5 个）

| 用例 | 根因 |
|---|---|
| multiagent/test_pi_installer.py × 4（install_in_background/status_done/ignore_scripts/global_flag） | 依赖前面测试的残留状态；隔离运行通过 |
| sandbox/test_stage3_integration.py::test_bash_output_truncation | 同上（`SandboxCommandError: command failed with exit code 1`，全量中触发） |

> 修复指引：全部属于「修测试」范畴，不触碰业务代码，对应 TEST_IMPROVEMENT_PLAN §4 P0-1（P0-1 产出即本次失败明细存档）。

## 4. 跳过项（4 个）

| 用例 | 原因 |
|---|---|
| sandbox/test_stage5_integration.py:10、test_stage6_integration.py:13 | `docker CLI not available`（本机未装 Docker，环境前置） |
| multiagent/test_pi_specialist.py:262、:267 | TUI banner 功能本批次未实现 |

## 5. 最慢 10 个测试

| 耗时 | 用例 | 说明 |
|---|---|---|
| 1.79s | integration/test_default_strategy_e2e.py::test_p4_summarize_real | 真实 LLM 摘要（需 key，日常跳过） |
| 1.11s | unit/multiagent/evolution/test_worker.py::test_per_profile_serial_by_daemon_thread | 守护线程 |
| 1.08s | unit/multiagent/evolution/test_bootstrap.py::test_setup_multiagent_l2_enabled_starts_daemon | 守护线程启动 |
| 1.04s | unit/multiagent/evolution/test_worker.py::test_daemon_thread_consumes_queue | 队列消费 |
| 1.02s | unit/multiagent/evolution/test_bootstrap.py::test_setup_l2_worker_start_stop | 线程生命周期 |
| 1.02s | unit/memory/test_memory_worker.py::test_shutdown_stops_thread | 线程关闭 |
| 1.01s | unit/memory/test_memory_worker.py::test_start_launches_daemon_thread | 线程启动 |
| 1.01s | unit/multiagent/evolution/test_worker.py::test_start_stop_daemon_thread | 线程生命周期 |
| 1.01s | unit/memory/test_bootstrap_worker.py::test_returns_instance_when_started | teardown |
| 1.01s | unit/memory/test_memory_worker.py::test_start_idempotent | 幂等启动 |

> 观察：最慢项均为线程/守护线程生命周期用例（~1s 级），无性能异常；全量 2720 个在 ~50s 内完成，套件整体轻量。

## 6. 测试目录分布

| 层级 | 用例数 | 占比 |
|---|---|---|
| unit | 2685 | 98.7% |
| integration | 35 | 1.3% |
| **合计** | **2720** | 100% |

> 金字塔倒置（单测占 98.7%、集成 1.3%、真实 E2E 趋近 0）——与 TEST_IMPROVEMENT_PLAN §1 记录一致，P1 层级的核心矛盾。

## 7. 与基线对照

| 维度 | 2026-08-24 基线 | 2026-08-25 本次 | 变化 |
|---|---|---|---|
| 通过 | 2704 | 2704 | 0 |
| 跳过 | 4 | 4 | 0 |
| 失败 | 14 | 14 | 0（分类完全一致，见 §3） |
| 总耗时 | — | 49.68s / 52.20s | 新增基线 |

## 8. 数据出处

| 数据 | 来源 |
|---|---|
| 全量结果 / 失败明细 | `.poirot/logs/test_reports/pytest_full_20260825.log`（`pytest -q --tb=short`） |
| 慢测试 / 跳过原因 | `.poirot/logs/test_reports/pytest_durations_20260825.log`（`pytest -q --durations=10 -rs --tb=no`） |
| 目录分布 | 当日 `pytest --collect-only -q` 统计 |
| 失败分类依据 | TEST_IMPROVEMENT_PLAN.md §4 P0-1（2026-08-25） |
| 2026-08-24 基线 | memory: poirot-env-setup |

---

*报告生成：2026-08-25，由全量 pytest 三次运行（全量×2 + collect-only）汇总，日志留存于 `.poirot/logs/test_reports/`。*
