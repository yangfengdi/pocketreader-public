from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_url TEXT,
                    source_filename TEXT,
                    reader_mode TEXT NOT NULL DEFAULT 'assistant',
                    voice TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    error TEXT,
                    audio_path TEXT,
                    duration_seconds REAL,
                    text_char_count INTEGER NOT NULL DEFAULT 0,
                    playback_position REAL NOT NULL DEFAULT 0,
                    listen_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    generated_at TEXT,
                    first_played_at TEXT,
                    last_played_at TEXT,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS listen_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    position_seconds REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_items_status_created
                    ON items(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_events_item_created
                    ON listen_events(item_id, created_at);
                """
            )

    def requeue_interrupted_items(self) -> int:
        now = utc_now()
        with self.connect() as conn:
            rows = list(
                conn.execute(
                    """
                    SELECT id FROM items
                    WHERE status = 'processing'
                    ORDER BY created_at ASC, id ASC
                    """
                )
            )
            if not rows:
                return 0
            item_ids = [int(row["id"]) for row in rows]
            conn.executemany(
                """
                UPDATE items
                SET status = 'queued', error = NULL, updated_at = ?
                WHERE id = ?
                """,
                [(now, item_id) for item_id in item_ids],
            )
            conn.executemany(
                """
                UPDATE jobs
                SET status = 'interrupted', error = ?, completed_at = ?
                WHERE item_id = ? AND completed_at IS NULL
                """,
                [
                    ("Worker stopped before completing this item; requeued automatically.", now, item_id)
                    for item_id in item_ids
                ],
            )
            conn.executemany(
                """
                INSERT INTO jobs (item_id, status, created_at)
                VALUES (?, 'queued', ?)
                """,
                [(item_id, now) for item_id in item_ids],
            )
            return len(item_ids)

    def create_item(
        self,
        *,
        title: str,
        body: str,
        source_type: str,
        voice: str,
        reader_mode: str,
        source_url: str | None = None,
        source_filename: str | None = None,
        status: str = "queued",
        error: str | None = None,
    ) -> int:
        now = utc_now()
        clean_title = title.strip() or derive_title(body)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO items (
                    title, body, source_type, source_url, source_filename,
                    reader_mode, voice, status, error, text_char_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_title,
                    body.strip(),
                    source_type,
                    source_url,
                    source_filename,
                    reader_mode,
                    voice,
                    status,
                    error,
                    len(body.strip()),
                    now,
                    now,
                ),
            )
            item_id = int(cursor.lastrowid)
            if status == "queued":
                conn.execute(
                    """
                    INSERT INTO jobs (item_id, status, created_at)
                    VALUES (?, 'queued', ?)
                    """,
                    (item_id, now),
                )
            return item_id

    def list_items(self, status: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM items"
        params: tuple[Any, ...] = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY created_at DESC, id DESC"
        with self.connect() as conn:
            return list(conn.execute(sql, params))

    def get_item(self, item_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    def claim_next_item(self) -> sqlite3.Row | None:
        now = utc_now()
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            conn.execute("BEGIN IMMEDIATE")
            item = conn.execute(
                """
                SELECT * FROM items
                WHERE status = 'queued'
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """
            ).fetchone()
            if item is None:
                conn.execute("COMMIT")
                return None
            conn.execute(
                "UPDATE items SET status = 'processing', error = NULL, updated_at = ? WHERE id = ?",
                (now, item["id"]),
            )
            conn.execute(
                """
                UPDATE jobs
                SET status = 'processing', started_at = ?, error = NULL
                WHERE item_id = ? AND completed_at IS NULL
                """,
                (now, item["id"]),
            )
            updated = conn.execute(
                "SELECT * FROM items WHERE id = ?", (item["id"],)
            ).fetchone()
            conn.execute("COMMIT")
            return updated
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def mark_ready(self, item_id: int, audio_path: str, duration_seconds: float) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE items
                SET status = 'ready', audio_path = ?, duration_seconds = ?,
                    generated_at = ?, updated_at = ?, error = NULL
                WHERE id = ?
                """,
                (audio_path, duration_seconds, now, now, item_id),
            )
            conn.execute(
                """
                UPDATE jobs
                SET status = 'done', completed_at = ?, error = NULL
                WHERE item_id = ? AND completed_at IS NULL
                """,
                (now, item_id),
            )

    def mark_error(self, item_id: int, error: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE items
                SET status = 'error', error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error[:2000], now, item_id),
            )
            conn.execute(
                """
                UPDATE jobs
                SET status = 'error', error = ?, completed_at = ?
                WHERE item_id = ? AND completed_at IS NULL
                """,
                (error[:2000], now, item_id),
            )

    def retry_item(self, item_id: int) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE items
                SET status = 'queued', error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, item_id),
            )
            conn.execute(
                "INSERT INTO jobs (item_id, status, created_at) VALUES (?, 'queued', ?)",
                (item_id, now),
            )

    def delete_item(self, item_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))

    def update_title(self, item_id: int, title: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE items SET title = ?, updated_at = ? WHERE id = ?",
                (title.strip(), utc_now(), item_id),
            )

    def record_event(self, item_id: int, event_type: str, position_seconds: float) -> None:
        now = utc_now()
        with self.connect() as conn:
            item = conn.execute(
                "SELECT first_played_at, listen_count FROM items WHERE id = ?",
                (item_id,),
            ).fetchone()
            if item is None:
                return
            first_played_at = item["first_played_at"]
            listen_count = int(item["listen_count"] or 0)
            updates = {
                "playback_position": max(0.0, float(position_seconds)),
                "last_played_at": now,
                "updated_at": now,
            }
            if first_played_at is None and event_type in {"play", "progress"}:
                updates["first_played_at"] = now
                updates["listen_count"] = listen_count + 1
            if event_type == "ended":
                updates["completed_at"] = now
                updates["playback_position"] = 0.0

            assignments = ", ".join(f"{key} = ?" for key in updates)
            conn.execute(
                f"UPDATE items SET {assignments} WHERE id = ?",
                (*updates.values(), item_id),
            )
            conn.execute(
                """
                INSERT INTO listen_events (item_id, event_type, position_seconds, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (item_id, event_type, float(position_seconds), now),
            )

    def ready_items_for_feed(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT * FROM items
                    WHERE status = 'ready' AND audio_path IS NOT NULL
                    ORDER BY created_at DESC, id DESC
                    LIMIT 200
                    """
                )
            )

    def next_ready_item_id(self, item_id: int) -> int | None:
        with self.connect() as conn:
            item = conn.execute(
                "SELECT created_at FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if item is None:
                return None
            next_item = conn.execute(
                """
                SELECT id FROM items
                WHERE status = 'ready'
                  AND completed_at IS NULL
                  AND (created_at < ? OR (created_at = ? AND id < ?))
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (item["created_at"], item["created_at"], item_id),
            ).fetchone()
            if next_item is None:
                next_item = conn.execute(
                    """
                    SELECT id FROM items
                    WHERE status = 'ready' AND completed_at IS NULL AND id != ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (item_id,),
                ).fetchone()
            return int(next_item["id"]) if next_item is not None else None


def derive_title(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("#").strip()
        if line:
            return line[:80]
    return "Untitled"
