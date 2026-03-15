from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.contracts import PlanSpec, RunTrace, TaskResult


class SqliteRunStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_connection()
        self.migrate()

    def _init_connection(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row

    def migrate(self) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    request_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    json_payload TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    request_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES runs(request_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    error TEXT,
                    FOREIGN KEY(request_id) REFERENCES runs(request_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES runs(request_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS curated_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(request_id) REFERENCES runs(request_id)
                )
                """
            )
            cursor.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(1, ?)",
                (self._now(),),
            )
            self._conn.commit()

    def save_run(
        self,
        *,
        request_id: str,
        trace_id: str,
        query: str,
        intent: str,
        plan: PlanSpec,
        task_results: list[TaskResult],
        trace: RunTrace,
        answer: str,
        json_payload: dict[str, object] | None,
    ) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO runs(request_id, trace_id, query, intent, answer, json_payload, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    trace_id,
                    query,
                    intent,
                    answer,
                    json.dumps(json_payload) if json_payload is not None else None,
                    self._now(),
                ),
            )
            cursor.execute(
                "INSERT OR REPLACE INTO plans(request_id, plan_id, plan_json) VALUES(?, ?, ?)",
                (request_id, plan.plan_id, json.dumps(plan.model_dump(mode='json'))),
            )
            cursor.execute("DELETE FROM task_results WHERE request_id = ?", (request_id,))
            for result in task_results:
                cursor.execute(
                    """
                    INSERT INTO task_results(request_id, task_id, status, output, citations_json, error)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        result.task_id,
                        result.status,
                        result.output,
                        json.dumps(result.citations),
                        result.error,
                    ),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO traces(trace_id, request_id, trace_json) VALUES(?, ?, ?)",
                (trace_id, request_id, json.dumps(trace.model_dump(mode='json'))),
            )
            self._conn.commit()

    def get_run(self, request_id: str) -> dict[str, object] | None:
        with self._lock:
            cursor = self._conn.cursor()
            run_row = cursor.execute(
                "SELECT * FROM runs WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if run_row is None:
                return None
            plan_row = cursor.execute(
                "SELECT plan_json FROM plans WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            result_rows = cursor.execute(
                "SELECT task_id, status, output, citations_json, error FROM task_results WHERE request_id = ?",
                (request_id,),
            ).fetchall()
            trace_row = cursor.execute(
                "SELECT trace_json FROM traces WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            return {
                'request_id': run_row['request_id'],
                'trace_id': run_row['trace_id'],
                'query': run_row['query'],
                'intent': run_row['intent'],
                'answer': run_row['answer'],
                'json_payload': json.loads(run_row['json_payload']) if run_row['json_payload'] else None,
                'plan': json.loads(plan_row['plan_json']) if plan_row else None,
                'task_results': [
                    {
                        'task_id': row['task_id'],
                        'status': row['status'],
                        'output': row['output'],
                        'citations': json.loads(row['citations_json']),
                        'error': row['error'],
                    }
                    for row in result_rows
                ],
                'trace': json.loads(trace_row['trace_json']) if trace_row else None,
            }

    def insert_curated_memory(
        self,
        *,
        request_id: str,
        memory_key: str,
        content: str,
        citations: list[str],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO curated_memory(request_id, memory_key, content, citations_json, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (request_id, memory_key, content, json.dumps(citations), self._now()),
            )
            self._conn.commit()

    def list_curated_memory(self, limit: int = 50) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT request_id, memory_key, content, citations_json, created_at
                FROM curated_memory ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    'request_id': row['request_id'],
                    'memory_key': row['memory_key'],
                    'content': row['content'],
                    'citations': json.loads(row['citations_json']),
                    'created_at': row['created_at'],
                }
                for row in rows
            ]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
