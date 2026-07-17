"""Skill 模块 — 基础层（SkillStore + version DAG + 打点 + 注入）。

公共 API：SkillManager / build_skill_manager。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from poirot.backend.agents.skill.config import SkillConfig, load_skill_config
from poirot.backend.agents.skill.selector import SkillSelector
from poirot.backend.agents.skill.store import SQLiteSkillStore, SkillStore

__all__ = [
    "SkillConfig",
    "SkillStore",
    "SQLiteSkillStore",
    "SkillSelector",
    "SkillManager",
    "build_skill_manager",
]

# 核心系统 skill 目录（随包提交，已验证）。与用户 skill（skills/，gitignore）同机制，
# 均可经 frontmatter enabled:false 或 store 禁用。包相对路径，不依赖 cwd。
_BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin_skills"


class SkillManager:
    """skill 管理门面。聚合 store + selector + injection/metrics middleware。

    INVARIANT:
    - bootstrap 构造一次，随 AppRuntime 生命周期
    - load_startup(llm) discover skill_dirs + sync_from_files + 建 selector/middleware
    - get_injection_middleware / get_metrics_middleware 供 middleware 链注入
    - switch_expert_mode 不重建（store 持久，INV#持久）
    - middleware 类 lazy import（避免 skill→middlewares→skill 循环）
    """

    def __init__(self, config: SkillConfig) -> None:
        self._config = config
        self._store = SQLiteSkillStore(config.db_path)
        self._selector: SkillSelector | None = None
        self._injection: Any = None
        self._metrics: Any = None

    def load_startup(self, llm: Any | None = None) -> None:
        """discover skill_dirs（用户）+ builtin_skills（核心）+ sync + 建 middleware。"""
        dirs = [Path(d) for d in self._config.skill_dirs]
        if self._config.include_builtin and _BUILTIN_SKILLS_DIR.exists():
            dirs.append(_BUILTIN_SKILLS_DIR)
        for rec in self._store.discover(dirs):
            try:
                self._store.register(rec)
            except Exception:
                pass

        self._selector = SkillSelector(
            self._store, llm,
            max_skills=self._config.max_inject,
            quality_threshold=self._config.quality_threshold,
            min_selections=self._config.min_selections,
        )

        # lazy import 避免循环（middlewares 反向 import skill.injector/_ctx）
        from poirot.backend.agents.middlewares.skill_injection_middleware import (
            SkillInjectionMiddleware,
        )
        from poirot.backend.agents.middlewares.skill_metrics_middleware import (
            SkillMetricsMiddleware,
        )
        self._injection = SkillInjectionMiddleware(self._store, self._selector)
        self._metrics = SkillMetricsMiddleware(self._store)

    def get_injection_middleware(self) -> Any:
        return self._injection

    def get_metrics_middleware(self) -> Any:
        return self._metrics

    @property
    def store(self) -> SkillStore:
        return self._store

    def list_skills(self) -> list[dict]:
        """返回 active skills 概览（供 TUI/CLI 展示）。"""
        result: list[dict] = []
        for rec in self._store.list_active():
            result.append({
                "skill_id": rec.skill_id,
                "name": rec.name,
                "description": rec.description,
                "effective_rate": round(rec.effective_rate, 3),
                "total_selections": rec.total_selections,
                "allowed_tools": list(rec.allowed_tools),
            })
        return result


def build_skill_manager() -> SkillManager | None:
    """从 .env 读 POIROT_SKILL_ENABLED + 目录。false 或无目录返 None。"""
    config = load_skill_config()
    if not config.enabled:
        return None
    if not any(Path(d).exists() for d in config.skill_dirs):
        return None
    return SkillManager(config)
