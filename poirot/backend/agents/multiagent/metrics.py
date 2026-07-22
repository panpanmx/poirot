"""MultiAgentMetricsStore — SQLite metrics for specialist orchestration.

设计（spec.md MultiAgentMetricsStore Requirement + design.md §6）:
- .poirot/multiagent.db SQLite（WAL + busy_timeout + threading.Lock）
- specialist_records 表：name + 4 计数器（selections/invoked/completions/fallbacks）
- specialist_judgments 表：run_id + specialist + success + duration + gap
- health_check：completion_rate < threshold AND invoked >= min → degraded
- 不进 ThreadState（design.md §2 metrics 分离）
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from poirot.backend.agents.journal.events import utc_now_iso

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS specialist_records (
    specialist_name     TEXT PRIMARY KEY,
    total_selections    INTEGER NOT NULL DEFAULT 0,
    total_invoked       INTEGER NOT NULL DEFAULT 0,
    total_completions   INTEGER NOT NULL DEFAULT 0,
    total_fallbacks     INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    last_updated        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS specialist_judgments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL,
    specialist_name     TEXT NOT NULL,
    success             INTEGER NOT NULL DEFAULT 0,
    duration_seconds    REAL NOT NULL DEFAULT 0.0,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    gap_analysis        TEXT NOT NULL DEFAULT '',
    ts                  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sj_name ON specialist_judgments(specialist_name);
CREATE INDEX IF NOT EXISTS idx_sj_run  ON specialist_judgments(run_id);
"""


@dataclass(frozen=True)
class SpecialistMetrics:
    """specialist 聚合指标（从 specialist_records 派生）。"""

    specialist_name: str
    total_selections: int
    total_invoked: int
    total_completions: int
    total_fallbacks: int

    @property
    def completion_rate(self) -> float:
        if self.total_invoked == 0:
            return 0.0
        return self.total_completions / self.total_invoked

    @property
    def fallback_rate(self) -> float:
        if self.total_invoked == 0:
            return 0.0
        return self.total_fallbacks / self.total_invoked


@dataclass(frozen=True)
class SpecialistHealth:
    """specialist 健康状态（health_check 输出）。"""

    specialist_name: str
    completion_rate: float
    total_invoked: int
    degraded: bool


class MultiAgentMetricsStore:
    """SQLite metrics store for multi-agent orchestration.

    INVARIANT:
    - WAL 模式 + busy_timeout=30000 + threading.Lock 保护写
    - PRAGMA user_version 记 schema 版本，首次启动建表
    - 4 计数器 programmatic 打点（record_selection/invoked/completion/fallback）
    - 不进 ThreadState（design.md §2 metrics 分离）
    """

    def __init__(self, db_path: str = ".poirot/multiagent.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version < _SCHEMA_VERSION:
                    conn.executescript(_SCHEMA_SQL)
                    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                    conn.commit()
            finally:
                conn.close()

    def _upsert_counter(self, specialist_name: str, field: str) -> None:
        now = utc_now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    f"""INSERT INTO specialist_records (specialist_name, {field}, created_at, last_updated)
                        VALUES (?, 1, ?, ?)
                        ON CONFLICT(specialist_name) DO UPDATE SET
                            {field} = {field} + 1,
                            last_updated = ?""",
                    (specialist_name, now, now, now),
                )
                conn.commit()
            finally:
                conn.close()

    def record_selection(self, specialist_name: str) -> None:
        self._upsert_counter(specialist_name, "total_selections")

    def record_invoked(self, specialist_name: str) -> None:
        self._upsert_counter(specialist_name, "total_invoked")

    def record_completion(self, specialist_name: str) -> None:
        self._upsert_counter(specialist_name, "total_completions")

    def record_fallback(self, specialist_name: str) -> None:
        self._upsert_counter(specialist_name, "total_fallbacks")

    def record_judgment(
        self,
        run_id: str,
        specialist_name: str,
        success: bool,
        duration_seconds: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        gap_analysis: str = "",
    ) -> None:
        now = utc_now_iso()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO specialist_judgments
                        (run_id, specialist_name, success, duration_seconds,
                         prompt_tokens, completion_tokens, gap_analysis, ts)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id, specialist_name, int(success), duration_seconds,
                        prompt_tokens, completion_tokens, gap_analysis, now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_metrics(self, specialist_name: str) -> SpecialistMetrics | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    """SELECT specialist_name, total_selections, total_invoked,
                              total_completions, total_fallbacks
                        FROM specialist_records WHERE specialist_name = ?""",
                    (specialist_name,),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return SpecialistMetrics(
            specialist_name=row[0],
            total_selections=row[1],
            total_invoked=row[2],
            total_completions=row[3],
            total_fallbacks=row[4],
        )

    def get_top_specialists(self, limit: int = 10) -> list[SpecialistMetrics]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """SELECT specialist_name, total_selections, total_invoked,
                              total_completions, total_fallbacks
                        FROM specialist_records
                        ORDER BY total_invoked DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            finally:
                conn.close()
        return [
            SpecialistMetrics(
                specialist_name=r[0], total_selections=r[1], total_invoked=r[2],
                total_completions=r[3], total_fallbacks=r[4],
            )
            for r in rows
        ]

    def health_check(
        self,
        threshold: float = 0.4,
        min_invoked: int = 5,
    ) -> list[SpecialistHealth]:
        """Return degraded specialists (completion_rate < threshold AND invoked >= min)."""
        all_metrics = self.get_top_specialists(limit=100)
        return [
            SpecialistHealth(
                specialist_name=m.specialist_name,
                completion_rate=m.completion_rate,
                total_invoked=m.total_invoked,
                degraded=(m.completion_rate < threshold and m.total_invoked >= min_invoked),
            )
            for m in all_metrics
        ]
