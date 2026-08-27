"""SQLite 只读查询：skills.db / multiagent.db。

直接 sqlite3 读取（不 import store 类，避免触发副作用），表结构先探测再查。
两库均可能 0 行（探索确认当前 0 行）——所有函数对空库返回空列表。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def _connect(db_path: str | Path) -> sqlite3.Connection | None:
    p = Path(db_path)
    if not p.exists():
        return None
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def _tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return [r["name"] for r in rows]


def _query_all(conn: sqlite3.Connection, table: str, limit: int = 10000) -> list[dict]:
    try:
        rows = conn.execute(f"SELECT * FROM {table} LIMIT {limit}").fetchall()
    except sqlite3.Error:
        return []
    return [dict(r) for r in rows]


def read_skill_records(db_path: str | Path) -> list[dict]:
    """skill_records 全量（含 4 计数器；4 率由 store.get_metrics 公式现算）。"""
    conn = _connect(db_path)
    if conn is None or "skill_records" not in _tables(conn):
        return []
    return _query_all(conn, "skill_records")


def read_skill_evolutions(db_path: str | Path) -> list[dict]:
    """skill_evolutions 全量（进化记录：gate_decision/eval_score/created_version_id…）。"""
    conn = _connect(db_path)
    if conn is None or "skill_evolutions" not in _tables(conn):
        return []
    return _query_all(conn, "skill_evolutions")


def read_task_quality_scores(db_path: str | Path) -> list[dict]:
    conn = _connect(db_path)
    if conn is None or "task_quality_scores" not in _tables(conn):
        return []
    return _query_all(conn, "task_quality_scores")


def read_skill_judgments(db_path: str | Path) -> list[dict]:
    conn = _connect(db_path)
    if conn is None or "skill_judgments" not in _tables(conn):
        return []
    return _query_all(conn, "skill_judgments")


def read_multiagent_records(db_path: str | Path) -> list[dict]:
    """multiagent.db 全表读取（表名自动探测，返回 {table: rows}）。"""
    conn = _connect(db_path)
    if conn is None:
        return []
    return {t: _query_all(conn, t) for t in _tables(conn)}


def summarize_multiagent(db_path: str | Path) -> dict[str, Any]:
    """multiagent.db 精简汇总：每表行数 + 带 invoked/completed 计数的表。"""
    conn = _connect(db_path)
    if conn is None:
        return {"tables": {}, "delegation": None}
    result: dict[str, Any] = {"tables": {}, "delegation": None}
    for t in _tables(conn):
        rows = _query_all(conn, t)
        result["tables"][t] = len(rows)
        if rows and any(k in rows[0] for k in ("invoked", "completions", "fallbacks")):
            agg = {k: 0 for k in ("selections", "invoked", "completions", "fallbacks")}
            for r in rows:
                for k in agg:
                    agg[k] += int(r.get(k, 0) or 0)
            agg["success_rate"] = round(agg["completions"] / agg["invoked"], 4) if agg["invoked"] else None
            result["delegation"] = agg
    return result
