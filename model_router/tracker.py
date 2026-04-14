"""Usage tracker -- records every API call to SQLite and serves stats."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from pathlib import Path

from model_router.models import ExecutionRecord

DB_PATH = Path(__file__).parent.parent / "data" / "usage.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_calls (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    model            TEXT NOT NULL,
    task_type        TEXT NOT NULL,
    input_tokens     INTEGER DEFAULT 0,
    output_tokens    INTEGER DEFAULT 0,
    cost_usd         REAL DEFAULT 0.0,
    latency_ms       INTEGER DEFAULT 0,
    timestamp        REAL NOT NULL,
    complexity_score REAL DEFAULT 0.0,
    decomposed       INTEGER DEFAULT 0,
    subtask_index    INTEGER DEFAULT -1,
    success          INTEGER DEFAULT 1,
    error            TEXT
);
CREATE INDEX IF NOT EXISTS idx_timestamp ON api_calls(timestamp);
CREATE INDEX IF NOT EXISTS idx_model     ON api_calls(model);
CREATE INDEX IF NOT EXISTS idx_session   ON api_calls(session_id);
"""


class UsageTracker:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._session_id = str(uuid.uuid4())
        self._init_db()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def record(self, rec: ExecutionRecord) -> None:
        if not rec.session_id:
            rec.session_id = self._session_id
        await asyncio.to_thread(self._sync_insert, rec)

    def _sync_insert(self, rec: ExecutionRecord) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO api_calls
                   (id, session_id, model, task_type, input_tokens, output_tokens,
                    cost_usd, latency_ms, timestamp, complexity_score, decomposed,
                    subtask_index, success, error)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec.record_id, rec.session_id, rec.model, rec.task_type,
                    rec.input_tokens, rec.output_tokens, rec.cost_usd, rec.latency_ms,
                    rec.timestamp, rec.complexity_score, int(rec.decomposed),
                    rec.subtask_index, int(rec.success), rec.error,
                ),
            )

    # ------------------------------------------------------------------
    # Read -- all queries run in thread pool to avoid blocking
    # ------------------------------------------------------------------

    async def get_live_totals(self) -> dict:
        return await asyncio.to_thread(self._sync_live_totals)

    def _sync_live_totals(self) -> dict:
        today_start = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT SUM(cost_usd) as cost, SUM(input_tokens+output_tokens) as tokens, "
                "COUNT(*) as calls FROM api_calls WHERE timestamp >= ?",
                (today_start,),
            ).fetchone()
            by_model = conn.execute(
                "SELECT model, COUNT(*) as calls, SUM(cost_usd) as cost "
                "FROM api_calls WHERE timestamp >= ? GROUP BY model",
                (today_start,),
            ).fetchall()
            session_row = conn.execute(
                "SELECT SUM(cost_usd) as cost, SUM(input_tokens+output_tokens) as tokens "
                "FROM api_calls WHERE session_id = ?",
                (self._session_id,),
            ).fetchone()

        return {
            "today_cost_usd": round(row["cost"] or 0.0, 6),
            "today_tokens": row["tokens"] or 0,
            "today_calls": row["calls"] or 0,
            "session_cost_usd": round(session_row["cost"] or 0.0, 6),
            "session_tokens": session_row["tokens"] or 0,
            "calls_per_model": {
                r["model"]: {"calls": r["calls"], "cost": round(r["cost"] or 0.0, 6)}
                for r in by_model
            },
        }

    async def get_cost_by_model(self, since_ts: float | None = None) -> list[dict]:
        return await asyncio.to_thread(self._sync_cost_by_model, since_ts)

    def _sync_cost_by_model(self, since_ts: float | None) -> list[dict]:
        since = since_ts or 0.0
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT model, COUNT(*) as calls, "
                "SUM(input_tokens) as input_t, SUM(output_tokens) as output_t, "
                "SUM(cost_usd) as cost, AVG(latency_ms) as avg_latency "
                "FROM api_calls WHERE timestamp >= ? GROUP BY model ORDER BY cost DESC",
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]

    async def get_task_history(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return await asyncio.to_thread(self._sync_task_history, limit, offset)

    def _sync_task_history(self, limit: int, offset: int) -> list[dict]:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM api_calls ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    async def get_session_stats(self) -> dict:
        return await asyncio.to_thread(self._sync_session_stats)

    def _sync_session_stats(self) -> dict:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT COUNT(*) as calls, SUM(cost_usd) as cost, "
                "SUM(input_tokens) as input_t, SUM(output_tokens) as output_t, "
                "AVG(latency_ms) as avg_latency, MIN(timestamp) as started "
                "FROM api_calls WHERE session_id = ?",
                (self._session_id,),
            ).fetchone()
        return {
            "session_id": self._session_id,
            "calls": row["calls"] or 0,
            "cost_usd": round(row["cost"] or 0.0, 6),
            "input_tokens": row["input_t"] or 0,
            "output_tokens": row["output_t"] or 0,
            "avg_latency_ms": round(row["avg_latency"] or 0, 1),
            "started_at": row["started"],
        }

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)

    @property
    def session_id(self) -> str:
        return self._session_id
