"""D.1 多 Agent 对照任务集：3 类"可拆可合"任务 × 4 题 = 12 题。

- parallel_research:   3 个相互独立的子调研方向（委派价值最大，parallel subtasks）
- isolated_compute:    长文档分段处理（隔离计算重活，对比父上下文膨胀）
- mixed_toolchain:     文件操作 + 网络搜索交错（两种不兼容工具链分工）

任务文本只描述任务本身，不含"用 subagent"字样——委派决策完全交给模型
（leader prompts 对 parallel/隔离/分解场景有明确委派指引）。

用法：
    python bench/d_multiagent/build_tasks.py
"""

from __future__ import annotations

import argparse
import json

from bench.common.env import PROJECT_ROOT, ensure_project_root

DATA_DIR = PROJECT_ROOT / "bench" / "data" / "d_multiagent"
FIXTURES = "poirot/bench/d_multiagent/fixtures"

TASKS = [
    # ── 类 1：并行拆分子调研 ─────────────────────────────
    {
        "task_id": "research-plants",
        "cls": "parallel_research",
        "text": (
            "输出一份三方向对比报告《家庭园艺入门》：(A) 三种易养绿植的养护要点，"
            "(B) 土壤与花盆选择建议，(C) 常见病虫害预防。三个方向相互独立、"
            "内容不交叉，请分别充分展开后汇总成报告。"
        ),
    },
    {
        "task_id": "research-frameworks",
        "cls": "parallel_research",
        "text": (
            "对比 3 个 Python Web 框架（FastAPI / Flask / Django）：各框架的适用场景、"
            "学习曲线、生态与性能特点。三者相互独立，分别调研后输出统一格式的对比报告。"
        ),
    },
    {
        "task_id": "research-tourism",
        "cls": "parallel_research",
        "text": (
            "规划一次 7 天旅行方案，三个独立板块：(A) 城市 A 的必去景点与路线，"
            "(B) 城市 B 的美食与住宿建议，(C) 两地间交通与预算估算。"
            "板块相互独立，分别给出结论后汇总为完整行程单。"
        ),
    },
    {
        "task_id": "research-k8s",
        "cls": "parallel_research",
        "text": (
            "写一份 Kubernetes 入门评估：(A) 核心概念清单与图解思路，"
            "(B) 开发环境搭建步骤（minikube 路线），(C) 常见坑与排查要点。"
            "三个主题独立，请分开处理再合成一篇。"
        ),
    },
    # ── 类 2：隔离计算重活 ───────────────────────────────
    {
        "task_id": "compute-logs",
        "cls": "isolated_compute",
        "text": (
            "以下 4 段服务器日志来自同一周，请逐段提取：错误类型、出现次数、"
            "涉及服务名，最后汇总全部 4 段的统计表与结论（总数、Top 错误）。"
            "各段相互独立，可分段处理。\n"
            "【段1】10:02 ERROR api-gateway timeout; 10:15 ERROR api-gateway timeout; "
            "10:31 WARN auth slow\n"
            "【段2】11:00 ERROR payment timeout; 11:12 ERROR payment timeout; "
            "11:40 ERROR payment timeout\n"
            "【段3】09:10 WARN cache miss; 09:33 ERROR db-conn reset; 09:41 WARN cache miss\n"
            "【段4】14:05 ERROR api-gateway timeout; 14:22 WARN auth slow; 14:50 ERROR db-conn reset"
        ),
    },
    {
        "task_id": "compute-invoices",
        "cls": "isolated_compute",
        "text": (
            "处理 4 份发票清单（各份独立），逐份计算：笔数、总金额、最大单笔；"
            "最后汇总 4 份的总笔数、总金额与整体最大单笔，输出表格。\n"
            "【发票1】金额: 120.5, 89, 210.75, 56\n"
            "【发票2】金额: 340, 128.25, 95.5, 412.8\n"
            "【发票3】金额: 67.9, 234, 187.4, 99.99\n"
            "【发票4】金额: 152.25, 78, 301.5, 245.6"
        ),
    },
    {
        "task_id": "compute-reviews",
        "cls": "isolated_compute",
        "text": (
            "以下 4 组用户评分数据分别来自不同门店，逐组统计：评价数、平均分（保留 1 位）、"
            "好评率（≥4 分占比）；最后汇总各店对比表。\n"
            "【店A】5,3,4,5,2,4,5,4\n"
            "【店B】4,4,3,5,5,1,4\n"
            "【店C】2,3,5,4,4,4,3,5,5\n"
            "【店D】5,5,4,3,2,5,5,4,4,3"
        ),
    },
    {
        "task_id": "compute-commits",
        "cls": "isolated_compute",
        "text": (
            "分析 4 个文件的改动统计（各自独立），每文件统计：提交次数、增删行数比、"
            "主要作者；最后合成项目级汇总。\n"
            "【auth.py】12 次提交，+320/-40 行，作者：张/李\n"
            "【db.py】8 次提交，+150/-90 行，作者：王/张\n"
            "【api.py】15 次提交，+210/-130 行，作者：李/赵\n"
            "【ui.py】6 次提交，+480/-20 行，作者：赵/王"
        ),
    },
    # ── 类 3：需要两种不兼容工具链 ───────────────────────
    {
        "task_id": "mixed-tools-1",
        "cls": "mixed_toolchain",
        "text": (
            f"两步任务：第一步读取文件 {FIXTURES}/inventory.txt 并列出其中所有品类与数量；"
            "第二步用 web_search 查一下「2026 年家庭储能市场趋势」的两个要点。"
            "文件内容处理与网络调研互不相干，最后把两步结果合入一份简报。"
        ),
    },
    {
        "task_id": "mixed-tools-2",
        "cls": "mixed_toolchain",
        "text": (
            f"两步任务：第一步用 web_search 找「2026 年端侧大模型」的 2 个关键趋势；"
            "第二步读取文件 {FIXTURES}/notes.txt 并总结要点。"
            "最后输出「趋势 × 笔记」对照结论表。"
        ),
    },
    {
        "task_id": "mixed-tools-3",
        "cls": "mixed_toolchain",
        "text": (
            f"两步任务：第一步读取 {FIXTURES}/errors.txt 中列出的错误码并给出修复建议；"
            "第二步用 web_search 确认「HTTP 429 与 503 的正确处理方式」要点。"
            "两类工作分开处理，最后合成一份运维速查卡。"
        ),
    },
    {
        "task_id": "mixed-tools-4",
        "cls": "mixed_toolchain",
        "text": (
            f"两步任务：第一步读取 {FIXTURES}/todos.txt 并按优先级排序；"
            "第二步用 web_search 查「番茄工作法」的 3 个要点。"
            "两部分相互独立，最后合并为一份效率方案。"
        ),
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成多 agent 对照任务集")
    args = parser.parse_args()
    ensure_project_root()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = DATA_DIR / "tasks.json"
    out.write_text(json.dumps({"n_tasks": len(TASKS), "tasks": TASKS},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {len(TASKS)} 个任务 → {out}")
    print("[hint] 下一步: python bench/d_multiagent/run_multiagent_bench.py")


if __name__ == "__main__":
    main()
