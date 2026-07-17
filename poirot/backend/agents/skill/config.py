"""Skill 配置层 — .env 读取 + frozen dataclass。

INVARIANT:
- POIROT_SKILL_ENABLED 缺省 false（opt-in，与 MCP 一致）→ build_skill_manager 返 None，既有行为不影响
- POIROT_SKILL_DB_PATH 缺省 .poirot/skills.db，相对项目根
- POIROT_SKILL_DIRS 逗号分隔多个扫描目录，缺省 ("skills/",)
- POIROT_SKILL_MAX_INJECT 缺省 3，单轮最多注入 skill 数
- POIROT_SKILL_QUALITY_THRESHOLD 缺省 0.3，quality filter 淘汰阈值
- POIROT_SKILL_MIN_SELECTIONS 缺省 5，淘汰判定最少 selections（anti-loop）
- int/float 转换失败 → 用默认值，不抛
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillConfig:
    """Skill 模块顶层配置。

    enabled: 是否启用 skill 模块（缺省 false，false 时 build_skill_manager 返 None）
    db_path: SQLite 路径（相对项目根）
    skill_dirs: skill 扫描目录元组
    max_inject: 单轮最多注入 skill 数
    quality_threshold: quality filter 淘汰阈值（effective_rate < threshold 且 selections >= min）
    min_selections: 淘汰判定最少 selections（anti-loop，给新 skill 数据积累机会）
    """
    enabled: bool = False
    db_path: str = ".poirot/skills.db"
    skill_dirs: tuple[str, ...] = ("skills/",)
    include_builtin: bool = True
    max_inject: int = 3
    quality_threshold: float = 0.3
    min_selections: int = 5


def load_skill_config() -> SkillConfig:
    """从 os.environ 读 POIROT_SKILL_* + 默认值。

    int/float 转换失败时用默认值，不抛异常。
    """
    enabled = os.environ.get("POIROT_SKILL_ENABLED", "false").lower() == "true"
    db_path = os.environ.get("POIROT_SKILL_DB_PATH", ".poirot/skills.db")
    include_builtin = os.environ.get("POIROT_SKILL_INCLUDE_BUILTIN", "true").lower() == "true"

    dirs_raw = os.environ.get("POIROT_SKILL_DIRS", "")
    if dirs_raw:
        skill_dirs = tuple(d.strip() for d in dirs_raw.split(",") if d.strip())
    else:
        skill_dirs = ("skills/",)

    try:
        max_inject = int(os.environ.get("POIROT_SKILL_MAX_INJECT", "3"))
    except (ValueError, TypeError):
        max_inject = 3

    try:
        quality_threshold = float(os.environ.get("POIROT_SKILL_QUALITY_THRESHOLD", "0.3"))
    except (ValueError, TypeError):
        quality_threshold = 0.3

    try:
        min_selections = int(os.environ.get("POIROT_SKILL_MIN_SELECTIONS", "5"))
    except (ValueError, TypeError):
        min_selections = 5

    return SkillConfig(
        enabled=enabled,
        db_path=db_path,
        skill_dirs=skill_dirs,
        include_builtin=include_builtin,
        max_inject=max_inject,
        quality_threshold=quality_threshold,
        min_selections=min_selections,
    )
