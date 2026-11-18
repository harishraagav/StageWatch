"""Local SQLite history storage."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import RunRecord


class HistoryStore:
    def __init__(self, path: str | Path, max_history: int = 1000) -> None:
        self.path = Path(path).expanduser().resolve()
        self.max_history = max(1, int(max_history))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._session() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                pipeline_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_runs_pipeline_started ON runs(pipeline_name, started_at DESC)")

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection.

        Callers should use :meth:`_session`, which always closes the connection.
        """
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """Commit/rollback a database operation and ALWAYS close its connection.

        The sqlite3 connection context manager alone does not close connections.
        Explicit closure is essential on Windows, where open handles prevent
        temporary directories and SQLite files from being removed.
        """
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, run: RunRecord) -> None:
        payload = json.dumps(run.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._session() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO runs(run_id, pipeline_name, started_at, payload) VALUES (?, ?, ?, ?)",
                (run.run_id, run.pipeline_name, run.started_at, payload),
            )
            connection.execute(
                "DELETE FROM runs WHERE run_id IN (SELECT run_id FROM runs WHERE pipeline_name=? ORDER BY started_at DESC LIMIT -1 OFFSET ?)",
                (run.pipeline_name, self.max_history),
            )

    def get(self, run_id: str) -> RunRecord | None:
        with self._session() as connection:
            row = connection.execute("SELECT payload FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return RunRecord.from_dict(json.loads(row["payload"])) if row else None

    def list(self, pipeline_name: str | None = None, limit: int = 20) -> list[RunRecord]:
        limit = max(1, min(int(limit), 10000))
        with self._session() as connection:
            if pipeline_name:
                rows = connection.execute("SELECT payload FROM runs WHERE pipeline_name=? ORDER BY started_at DESC LIMIT ?", (pipeline_name, limit)).fetchall()
            else:
                rows = connection.execute("SELECT payload FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [RunRecord.from_dict(json.loads(row["payload"])) for row in rows]

    def latest(self, pipeline_name: str | None = None) -> RunRecord | None:
        items = self.list(pipeline_name=pipeline_name, limit=1)
        return items[0] if items else None

    def delete_all(self, pipeline_name: str | None = None) -> int:
        with self._session() as connection:
            if pipeline_name:
                cursor = connection.execute("DELETE FROM runs WHERE pipeline_name=?", (pipeline_name,))
            else:
                cursor = connection.execute("DELETE FROM runs")
            return cursor.rowcount


def load_history(path: str | Path) -> HistoryStore:
    """Open an existing StageWatch database (or initialize an empty one)."""
    return HistoryStore(path)
