"""C.1 对齐内置核心 skill 的评测任务集。

只测启动时自动激活的 12 个 core skill（BUILTIN origin，load_startup 自动 discover）。
其余 25 个（research/software-development/creative/productivity）需先经 find-skills
搜索激活，不纳入本轮基准（方法论注释：避免 find-skills 流程噪声）。

任务文本内不出现 skill 名（避免污染选择打点）；每任务标注 skill_target 供分析使用。
三类口径（与 SkillMetricsMiddleware 语义一致）：
- tool-covered：任务会驱动模型调用该 skill 的 allowed_tools → applied 可判定
- guidance：skill 无 allowed_tools → applied=None，只打 selections（不归因完成）
- tool-uncovered：skill 有 allowed_tools 但 bench runtime 无对应工具 → applied=False（诚实归因）

用法：
    python bench/c_skill/build_task_set.py [--out tasks.json]
"""

from __future__ import annotations

import argparse
import json

from bench.common.env import PROJECT_ROOT, ensure_project_root

DATA_DIR = PROJECT_ROOT / "bench" / "data" / "c_skill"
FIXTURES = "poirot/bench/c_skill/fixtures"

# 与 12 个 core skill 一一对应（name 与 builtin_skills/core/*/SKILL.md 的 name 一致）
TASKS = [
    {
        "task_id": "task-systematic-debugging",
        "skill_target": "systematic-debugging",
        "text": (
            f"项目文件 {FIXTURES}/buggy_calc.py 中的 average() 和 median() 有 bug。"
            "请用 4 阶段系统化调试流程处理：先读文件、复现错误、定位根因，再修复，"
            "最后运行验证。不要跳步，输出修复后的完整代码。"
            "（可用 read_file 读取文件、bash 运行 python 验证）"
        ),
    },
    {
        "task_id": "task-test-driven-development",
        "skill_target": "test-driven-development",
        "text": (
            f"为 {FIXTURES}/buggy_calc.py 中的 average() 与 median() 采用 TDD 流程："
            "先写测试（覆盖空列表、正常、偶数长度），观察失败，再修复实现到测试全绿。"
            "测试与修复后的代码都保存到沙箱文件。"
        ),
    },
    {
        "task_id": "task-simplify-code",
        "skill_target": "simplify-code",
        "text": (
            "简化下面这段代码（保持行为完全一致），把简化后的版本保存到沙箱文件 "
            "simplified.py：\n"
            "```python\n"
            "def classify(n):\n"
            "    result = ''\n"
            "    if n % 2 == 0:\n"
            "        result = result + 'even'\n"
            "    else:\n"
            "        result = result + 'odd'\n"
            "    if n % 3 == 0:\n"
            "        result = result + '-fizz'\n"
            "    if n % 5 == 0:\n"
            "        result = result + '-buzz'\n"
            "    return result\n"
            "```"
        ),
    },
    {
        "task_id": "task-skill-creator",
        "skill_target": "skill-creator",
        "text": (
            "为「每周销售周报摘要」这个能力创建一个完整的 SKILL.md：包含 frontmatter"
            "（name/description/allowed-tools）、触发条件、工作流程与输出格式，"
            "并保存到沙箱文件 sales-weekly-summary/SKILL.md。"
        ),
    },
    {
        "task_id": "task-skill-authoring",
        "skill_target": "skill-authoring",
        "text": (
            "评审以下 SKILL.md 的质量（结构、frontmatter 完整性、可执行性、防幻觉设计），"
            "逐条给出改进意见，并将修订版保存到沙箱文件 reviewed/SKILL.md：\n"
            "```markdown\n"
            "---\n"
            "name: quick-summary\n"
            "description: Summarize stuff\n"
            "---\n"
            "Summarize the input.\n"
            "```"
        ),
    },
    {
        "task_id": "task-plan",
        "skill_target": "plan",
        "text": (
            "制定一个「从零搭建个人知识库服务」的完整实施计划：目标、技术选型权衡、"
            "分阶段里程碑（每阶段含交付物与验收标准）、风险与回退方案、工作量估算。"
            "按结构化模板输出。"
        ),
    },
    {
        "task_id": "task-github-code-review",
        "skill_target": "github-code-review",
        "text": (
            "对以下代码变更做 code review（按严重性分级输出问题与修改建议，"
            "引用具体行号）：\n"
            "```diff\n"
            "--- a/cart.py\n"
            "+++ b/cart.py\n"
            "@@ -10,7 +10,7 @@ def apply_discount(cart, code):\n"
            "-    if cart.total > 100:\n"
            "+    if cart.total > 100 and code == 'SAVE10':\n"
            "         return cart.total * 0.9\n"
            "     return cart.total\n"
            "```"
        ),
    },
    {
        "task_id": "task-requesting-code-review",
        "skill_target": "requesting-code-review",
        "text": (
            "下面是你要提交的代码，请以「请求评审者」的视角先自我审查一遍，"
            "给出你自己发现的 3 个最值得注意的问题（含理由），并说明希望评审者"
            "重点关注的方面：\n"
            "```python\n"
            "def fetch_and_cache(url, ttl=60):\n"
            "    cache = {}\n"
            "    if url in cache and time.time() - cache[url][0] < ttl:\n"
            "        return cache[url][1]\n"
            "    data = requests.get(url).json()\n"
            "    cache[url] = (time.time(), data)\n"
            "    return data\n"
            "```"
        ),
    },
    {
        "task_id": "task-spike",
        "skill_target": "spike",
        "text": (
            "快速 spike 验证一个技术想法：把下面两个 Python 函数合二为一后，"
            "行为是否完全等价（用不同输入样例验证边界）？给出结论、证据、"
            "以及「可行/不可行」判定与理由：\n"
            "```python\n"
            "def a(x): return x * 2 + 1\n"
            "def b(x): return x + x + 1\n"
            "```"
        ),
    },
    {
        "task_id": "task-source-verification",
        "skill_target": "source-verification",
        "text": (
            "验证以下三条陈述的可信度，标注【可信】【存疑】【不可信】并给出依据；"
            "可使用 web_search 查证，最终按来源强度排序输出：\n"
            "1. Python 3.12 的 f-string 支持嵌套同引号。\n"
            "2. 地球绕太阳公转周期约 365.25 天。\n"
            "3. Vim 的默认退出方式是输入 :wq。"
        ),
    },
    {
        "task_id": "task-find-skills",
        "skill_target": "find-skills",
        "text": (
            "我需要在周会上做一次 20 分钟的「微服务可观测性」分享，想找现成的技能"
            "来辅助资料收集与 PPT 制作。请搜索可用技能，列出最适合的 3 个（名称、"
            "用途、匹配理由）。"
        ),
    },
    {
        "task_id": "task-bootstrap",
        "skill_target": "bootstrap",
        "text": (
            "我刚 clone 一个陌生 Python 后端项目，请按 bootstrap 流程给出：环境准备"
            "检查清单、依赖安装与验证命令、配置文件核对点、以及最小可运行验证路径"
            "（看到什么输出算成功）。按清单输出。"
        ),
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 skill 评测任务集")
    parser.add_argument("--out", default=str(DATA_DIR / "tasks.json"))
    args = parser.parse_args()

    ensure_project_root()
    out = __import__("pathlib").Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"n_tasks": len(TASKS), "tasks": TASKS},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {len(TASKS)} 个任务 → {out}")
    print("[hint] 下一步: python bench/c_skill/run_skill_bench.py")


if __name__ == "__main__":
    main()
