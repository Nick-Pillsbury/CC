"""Bounded SQLite debugging history; database work runs off the event loop."""

import asyncio
from collections import deque
import json
import logging
from pathlib import Path
import sqlite3
import threading

from master_api.models import utc_now

logger = logging.getLogger(__name__)


class Journal:
    def __init__(self, path: str = ":memory:", limit: int = 10000) -> None:
        if limit < 1:
            raise ValueError("History limit must be positive")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.limit = limit
        self.last_error: str | None = None
        self._pending: deque[dict] = deque(maxlen=limit)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=1000")
        self._db.execute("""CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
        )""")
        self._db.execute("CREATE INDEX IF NOT EXISTS history_kind ON history(kind, id)")
        self._db.commit()

    async def record(self, event: str, **fields: object) -> None:
        # Callers supply explicit safe fields, never request bodies or headers.
        await self.append("event", {"event": event, **fields})

    def enqueue(self, event: str, **fields: object) -> None:
        """Record a state change without delaying a hardware stop on disk IO."""
        self._pending.append({"event": event, "occurred_at": utc_now().isoformat(), **fields})

    async def flush(self) -> None:
        while self._pending:
            await self._write("event", self._pending.popleft())

    async def append(self, kind: str, payload: dict) -> None:
        await self.flush()
        await self._write(kind, payload)

    async def _write(self, kind: str, payload: dict) -> None:
        try:
            await asyncio.to_thread(self._append, kind, payload)
            self.last_error = None
        except (sqlite3.Error, OSError):
            # A full disk must not prevent emergency neutralization.
            self.last_error = "history_write_failed"
            logger.error("history_write_failed")

    def _append(self, kind: str, payload: dict) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO history(kind, created_at, payload) VALUES (?, ?, ?)",
                (kind, utc_now().isoformat(), json.dumps(payload)),
            )
            self._db.execute(
                """DELETE FROM history WHERE kind=? AND id <= (
                    SELECT id FROM history WHERE kind=? ORDER BY id DESC LIMIT 1 OFFSET ?
                )""", (kind, kind, self.limit),
            )

    async def read(self, kind: str, after: int = 0, limit: int = 100) -> list[dict]:
        await self.flush()
        return await asyncio.to_thread(self._read, kind, after, limit)

    def _read(self, kind: str, after: int, limit: int) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, created_at, payload FROM history WHERE kind=? AND id>? ORDER BY id LIMIT ?",
                (kind, after, limit),
            ).fetchall()
        return [{"id": row[0], "created_at": row[1], "data": json.loads(row[2])} for row in rows]

    async def close(self) -> None:
        await self.flush()
        await asyncio.to_thread(self._close)

    def _close(self) -> None:
        with self._lock:
            self._db.close()
