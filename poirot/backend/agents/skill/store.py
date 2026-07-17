"""SkillStore — SQLite + WAL + version DAG + 4 计数器打点。

INVARIANT:
- 内容/索引分离：只存 path + content_hash，SKILL.md 全文留文件（source of truth）
- WAL 模式 + busy_timeout=30000 + threading.Lock 保护写连接
- PRAGMA user_version 记 schema 版本，启动跑迁移链（from_v → from_v+1 → ... → to_v）
- is_active 单指针：每 name 仅 1 active，回滚切指针不删除（B2 实现）
- 4 计数器 programmatic 打点（B3 实现 record_selection/record_outcome）

本 batch（B1b）仅含 schema + 迁移。CRUD/metrics 在 B2/B3。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

from poirot.backend.agents.journal.events import utc_now_iso
from poirot.backend.agents.skill.types import (
    SkillHealth,
    SkillLineage,
    SkillMetrics,
    SkillRecord,
)

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS skill_records (
    skill_id            TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    path                TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    is_active           INTEGER NOT NULL DEFAULT 1,
    generation          INTEGER NOT NULL DEFAULT 0,
    origin              TEXT NOT NULL DEFAULT 'IMPORTED',
    created_by          TEXT,
    description         TEXT NOT NULL DEFAULT '',
    allowed_tools       TEXT NOT NULL DEFAULT '[]',
    enabled             INTEGER NOT NULL DEFAULT 1,
    total_selections    INTEGER NOT NULL DEFAULT 0,
    total_applied       INTEGER NOT NULL DEFAULT 0,
    total_completions   INTEGER NOT NULL DEFAULT 0,
    total_fallbacks     INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    last_updated        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sr_name   ON skill_records(name);
CREATE INDEX IF NOT EXISTS idx_sr_active ON skill_records(is_active);

CREATE TABLE IF NOT EXISTS skill_lineage_parents (
    skill_id        TEXT NOT NULL,
    parent_skill_id TEXT NOT NULL,
    PRIMARY KEY (skill_id, parent_skill_id)
);

CREATE TABLE IF NOT EXISTS skill_judgments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    skill_id        TEXT NOT NULL,
    applied         INTEGER,
    task_completed  INTEGER NOT NULL DEFAULT 0,
    ts              TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sj_skill ON skill_judgments(skill_id);
CREATE INDEX IF NOT EXISTS idx_sj_run   ON skill_judgments(run_id);
"""


class SkillStore(Protocol):
    """基础层存储接口。实现可选 SQLite / jsonl / Nacos（MVP 用 SQLiteSkillStore）。

    INVARIANT:
    - 内容/索引分离：只存 path + content_hash，SKILL.md 全文留文件
    - is_active 单指针：每 name 仅 1 active，rollback 切指针不删除
    - version DAG：create_version 建 new node + 旧 node deactive + lineage_parents
    """

    # 注册 / 发现
    def register(self, record: SkillRecord) -> str: ...
    def discover(self, dirs: list[Path], origin: str = "IMPORTED") -> list[SkillRecord]: ...
    def get(self, skill_id: str) -> SkillRecord | None: ...
    def get_active(self, name: str) -> SkillRecord | None: ...
    def list_active(self) -> list[SkillRecord]: ...

    # version DAG
    def create_version(self, parent_id: str, record: SkillRecord, origin: str) -> str: ...
    def get_versions(self, name: str) -> list[SkillRecord]: ...
    def rollback(self, skill_id: str) -> None: ...

    # quality metrics 打点（基础层，L2/L3 只读）
    # INVARIANT #5-#9: 4 计数器零 LLM 贯穿，applied 混合，task_completed run 级归因
    def record_selection(self, skill_id: str) -> None: ...
    def record_outcome(
        self,
        skill_id: str,
        run_id: str,
        applied: bool | None,
        task_completed: bool,
        note: str = "",
    ) -> None: ...
    def get_metrics(self, skill_id: str) -> SkillMetrics | None: ...
    def get_top_skills(
        self,
        n: int,
        metric: str = "effective_rate",
        min_selections: int = 5,
    ) -> list[SkillRecord]: ...
    def health_check(
        self,
        threshold: float = 0.4,
        min_selections: int = 5,
    ) -> list[SkillHealth]: ...


class SQLiteSkillStore:
    """skill 基础层存储。SQLite + WAL + version DAG + 4 计数器打点。

    INVARIANT:
    - 内容/索引分离：只存 path + content_hash（SKILL.md 全文留文件）
    - WAL + busy_timeout=30000，threading.Lock 保护写连接
    - PRAGMA user_version 记 schema 版本，启动跑迁移链
    - B1b 仅 schema + 迁移；CRUD/metrics 在 B2/B3
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._mu = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """建表 + WAL + user_version 迁移。构造时持锁。"""
        with self._mu:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._conn.executescript(_SCHEMA_SQL)
            current = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if current < _SCHEMA_VERSION:
                self._migrate(current, _SCHEMA_VERSION)
                self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            self._conn.commit()

    def _migrate(self, from_v: int, to_v: int) -> None:
        """schema 版本链迁移。from_v → from_v+1 → ... → to_v。

        当前 _SCHEMA_VERSION=1，executescript 已建初始表，无历史迁移步骤。
        新增版本时在 migrations 注册 (v, v+1) 迁移函数。
        """
        migrations: dict[tuple[int, int], Any] = {
            # (0, 1): 初始 schema（executescript 已完成，无需额外操作）
        }
        v = from_v
        while v < to_v:
            step = migrations.get((v, v + 1))
            if step is not None:
                step(self._conn)
            v += 1

    # ── 注册 / 发现 ──────────────────────────────────────────

    def register(self, record: SkillRecord) -> str:
        """幂等注册。INSERT OR IGNORE；已存在 skill_id 返回现有不覆盖。

        INVARIANT: 同 skill_id 二次 register 不覆盖、不报错。
        计数器（total_selections 等）由 schema DEFAULT 0 初始化，record 携带的
        metrics 值不写入（register 只注册元数据 + path + content_hash）。
        """
        with self._mu:
            self._conn.execute(
                """INSERT OR IGNORE INTO skill_records
                     (skill_id, name, path, content_hash, is_active,
                      generation, origin, created_by, description,
                      allowed_tools, enabled, created_at, last_updated)
                   VALUES (?,?,?,?,1,?,?,?,?,?,?,?,?)""",
                (record.skill_id, record.name, record.path, record.content_hash,
                 record.lineage.generation, record.lineage.origin,
                 record.lineage.created_by, record.description,
                 json.dumps(list(record.allowed_tools)),
                 1 if record.enabled else 0,
                 utc_now_iso(), utc_now_iso()),
            )
            if record.lineage.parent_skill_ids:
                for pid in record.lineage.parent_skill_ids:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO skill_lineage_parents VALUES (?,?)",
                        (record.skill_id, pid),
                    )
            self._conn.commit()
            return record.skill_id

    def get(self, skill_id: str) -> SkillRecord | None:
        """查单条。还原 allowed_tools tuple + lineage parent_skill_ids。"""
        with self._mu:
            row = self._conn.execute(
                "SELECT * FROM skill_records WHERE skill_id=?", (skill_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def get_active(self, name: str) -> SkillRecord | None:
        """查 name 的 active 版本（is_active=1）。"""
        with self._mu:
            row = self._conn.execute(
                "SELECT * FROM skill_records WHERE name=? AND is_active=1", (name,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def list_active(self) -> list[SkillRecord]:
        """所有 is_active=1 的 skill。"""
        with self._mu:
            rows = self._conn.execute(
                "SELECT * FROM skill_records WHERE is_active=1"
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def discover(self, dirs: list[Path], origin: str = "IMPORTED") -> list[SkillRecord]:
        """扫描 dirs 找 SKILL.md，parse（origin）→ upsert → 返回列表。

        INVARIANT: lazy import parser（避免循环依赖）。
        origin: IMPORTED（用户 skill，sidecar）| BUILTIN（核心 skill，确定性 id）。
        skill_id 已存在时同步文件变更（path/content_hash/description/
        allowed_tools/enabled），保证 discover 后索引不过期。
        """
        from poirot.backend.agents.skill.parser import parse_skill_file

        results: list[SkillRecord] = []
        for d in dirs:
            for skill_md in Path(d).rglob("SKILL.md"):
                record = parse_skill_file(skill_md, origin=origin)
                self._upsert_record(record)
                results.append(record)
        return results

    def _upsert_record(self, record: SkillRecord) -> None:
        """INSERT OR IGNORE；已存在则 UPDATE 同步文件变更。持锁。"""
        with self._mu:
            cur = self._conn.execute(
                """INSERT OR IGNORE INTO skill_records
                     (skill_id, name, path, content_hash, is_active,
                      generation, origin, created_by, description,
                      allowed_tools, enabled, created_at, last_updated)
                   VALUES (?,?,?,?,1,?,?,?,?,?,?,?,?)""",
                (record.skill_id, record.name, record.path, record.content_hash,
                 record.lineage.generation, record.lineage.origin,
                 record.lineage.created_by, record.description,
                 json.dumps(list(record.allowed_tools)),
                 1 if record.enabled else 0,
                 utc_now_iso(), utc_now_iso()),
            )
            if cur.rowcount == 0:
                # 已存在，同步文件变更
                self._conn.execute(
                    """UPDATE skill_records
                         SET path=?, content_hash=?, description=?,
                             allowed_tools=?, enabled=?, last_updated=?
                       WHERE skill_id=?""",
                    (record.path, record.content_hash, record.description,
                     json.dumps(list(record.allowed_tools)),
                     1 if record.enabled else 0,
                     utc_now_iso(), record.skill_id),
                )
            if record.lineage.parent_skill_ids:
                for pid in record.lineage.parent_skill_ids:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO skill_lineage_parents VALUES (?,?)",
                        (record.skill_id, pid),
                    )
            self._conn.commit()

    # ── version DAG ──────────────────────────────────────────

    def create_version(self, parent_id: str, record: SkillRecord, origin: str) -> str:
        """建新 version node。新 is_active=1 + 同名旧 is_active=0 + lineage_parents。

        INVARIANT: 新 skill_id 由调用方传入 record.skill_id（不在此生成）。
        重复 skill_id 抛 ValueError（保护 is_active 单指针不变量）。
        """
        with self._mu:
            ts = utc_now_iso()
            cur = self._conn.execute(
                """INSERT OR IGNORE INTO skill_records
                     (skill_id, name, path, content_hash, is_active,
                      generation, origin, created_by, description,
                      allowed_tools, enabled, created_at, last_updated)
                   VALUES (?,?,?,?,1,?,?,?,?,?,?,?,?)""",
                (record.skill_id, record.name, record.path, record.content_hash,
                 record.lineage.generation, origin, record.lineage.created_by,
                 record.description, json.dumps(list(record.allowed_tools)),
                 1 if record.enabled else 0, ts, ts),
            )
            if cur.rowcount == 0:
                raise ValueError(f"skill_id already exists: {record.skill_id}")
            # deactivate 同名除 new 外（new 的 is_active=1 由 schema DEFAULT 保证）
            self._conn.execute(
                "UPDATE skill_records SET is_active=0 WHERE name=? AND skill_id<>?",
                (record.name, record.skill_id),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO skill_lineage_parents VALUES (?,?)",
                (record.skill_id, parent_id),
            )
            self._conn.commit()
            return record.skill_id

    def get_versions(self, name: str) -> list[SkillRecord]:
        """返回 name 所有版本，ORDER BY generation ASC。"""
        with self._mu:
            rows = self._conn.execute(
                "SELECT * FROM skill_records WHERE name=? ORDER BY generation ASC",
                (name,),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]

    def rollback(self, skill_id: str) -> None:
        """激活指定 node + 同名其他 node deactive。不删除任何行。

        INVARIANT: 切 is_active 指针，旧 node 仍存在。
        """
        with self._mu:
            row = self._conn.execute(
                "SELECT name FROM skill_records WHERE skill_id=?", (skill_id,)
            ).fetchone()
            if row is None:
                return
            name = row["name"]
            self._conn.execute(
                "UPDATE skill_records SET is_active=1 WHERE skill_id=?", (skill_id,)
            )
            self._conn.execute(
                "UPDATE skill_records SET is_active=0 WHERE name=? AND skill_id<>?",
                (name, skill_id),
            )
            self._conn.commit()

    # ── quality metrics 打点 / 查询 ──────────────────────────

    def record_selection(self, skill_id: str) -> None:
        """total_selections += 1。持锁 + commit。

        INVARIANT #6: selections 在 before_model 注入时打（确定）。
        skill_id 不存在时静默（UPDATE 0 行，不抛）。
        """
        with self._mu:
            self._conn.execute(
                "UPDATE skill_records SET total_selections = total_selections + 1, "
                "last_updated = ? WHERE skill_id = ?",
                (utc_now_iso(), skill_id),
            )
            self._conn.commit()

    def record_outcome(
        self,
        skill_id: str,
        run_id: str,
        applied: bool | None,
        task_completed: bool,
        note: str = "",
    ) -> None:
        """归因打点：applied 混合 + task_completed run 级。原子事务。

        INVARIANT #7-#9:
        - applied True → total_applied += 1
        - applied True AND task_completed → total_completions += 1
        - applied False AND NOT task_completed → total_fallbacks += 1
        - applied None（guidance-skill）→ 三计数器均不变，只插 judgment
        skill_id 不存在时静默跳过（避免孤立 judgment）。
        """
        with self._mu:
            # 先验存在，不存在则跳过（避免孤立 judgment 行）
            exists = self._conn.execute(
                "SELECT 1 FROM skill_records WHERE skill_id=?", (skill_id,)
            ).fetchone()
            if exists is None:
                return

            inc_applied = 1 if applied is True else 0
            inc_completion = 1 if (applied is True and task_completed) else 0
            inc_fallback = 1 if (applied is False and not task_completed) else 0

            self._conn.execute(
                "UPDATE skill_records SET "
                "total_applied = total_applied + ?, "
                "total_completions = total_completions + ?, "
                "total_fallbacks = total_fallbacks + ?, "
                "last_updated = ? WHERE skill_id = ?",
                (inc_applied, inc_completion, inc_fallback,
                 utc_now_iso(), skill_id),
            )
            self._conn.execute(
                "INSERT INTO skill_judgments "
                "(run_id, skill_id, applied, task_completed, ts, note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, skill_id,
                 None if applied is None else (1 if applied else 0),
                 1 if task_completed else 0, utc_now_iso(), note),
            )
            self._conn.commit()

    def get_metrics(self, skill_id: str) -> SkillMetrics | None:
        """读 4 计数器，算 4 rate（零除保护）。不存在返 None。"""
        with self._mu:
            row = self._conn.execute(
                "SELECT total_selections, total_applied, total_completions, "
                "total_fallbacks FROM skill_records WHERE skill_id=?",
                (skill_id,),
            ).fetchone()
            if row is None:
                return None
            sel = row["total_selections"]
            app = row["total_applied"]
            comp = row["total_completions"]
            fb = row["total_fallbacks"]
            return SkillMetrics(
                skill_id=skill_id,
                selections=sel,
                applied=app,
                completions=comp,
                fallbacks=fb,
                applied_rate=app / sel if sel else 0.0,
                completion_rate=comp / app if app else 0.0,
                effective_rate=comp / sel if sel else 0.0,
                fallback_rate=fb / sel if sel else 0.0,
            )

    def get_top_skills(
        self,
        n: int,
        metric: str = "effective_rate",
        min_selections: int = 5,
    ) -> list[SkillRecord]:
        """按 metric 降序返 top n active skill。

        INVARIANT #12: total_selections < min_selections 不参与排序
        （anti-loop，给新 skill 数据积累）。
        metric ∈ {effective_rate, applied_rate, completion_rate, fallback_rate}。
        统一降序，调用方解释含义。
        """
        with self._mu:
            rows = self._conn.execute(
                "SELECT * FROM skill_records WHERE is_active=1 "
                "AND total_selections >= ?",
                (min_selections,),
            ).fetchall()
            records = [self._row_to_record(r) for r in rows]
            records.sort(key=lambda r: getattr(r, metric), reverse=True)
            return records[:n]

    def health_check(
        self,
        threshold: float = 0.4,
        min_selections: int = 5,
    ) -> list[SkillHealth]:
        """标 degraded = effective_rate < threshold AND selections >= min。

        INVARIANT #12: selections < min → degraded=False（数据不足不判）。
        """
        results: list[SkillHealth] = []
        for rec in self.list_active():
            degraded = (
                rec.total_selections >= min_selections
                and rec.effective_rate < threshold
            )
            results.append(SkillHealth(
                skill_id=rec.skill_id,
                name=rec.name,
                effective_rate=rec.effective_rate,
                fallback_rate=rec.fallback_rate,
                total_selections=rec.total_selections,
                degraded=degraded,
            ))
        return results

    # ── helpers ──────────────────────────────────────────────

    # TODO(perf): list_active/get_versions hot path 批量取 lineage（当前 N+1，skill<20 可接受）
    def _row_to_record(self, row: sqlite3.Row) -> SkillRecord:
        """sqlite Row → SkillRecord。还原 allowed_tools tuple + lineage。"""
        parent_rows = self._conn.execute(
            "SELECT parent_skill_id FROM skill_lineage_parents WHERE skill_id=?",
            (row["skill_id"],),
        ).fetchall()
        parents = tuple(r["parent_skill_id"] for r in parent_rows)
        lineage = SkillLineage(
            parent_skill_ids=parents,
            generation=row["generation"],
            origin=row["origin"],
            version_hash=row["content_hash"],
            created_by=row["created_by"],
        )
        return SkillRecord(
            skill_id=row["skill_id"],
            name=row["name"],
            path=row["path"],
            content_hash=row["content_hash"],
            is_active=bool(row["is_active"]),
            lineage=lineage,
            description=row["description"],
            allowed_tools=tuple(json.loads(row["allowed_tools"])),
            enabled=bool(row["enabled"]),
            total_selections=row["total_selections"],
            total_applied=row["total_applied"],
            total_completions=row["total_completions"],
            total_fallbacks=row["total_fallbacks"],
            created_at=row["created_at"],
            last_updated=row["last_updated"],
        )

    def close(self) -> None:
        with self._mu:
            self._conn.close()
            self._conn = None
