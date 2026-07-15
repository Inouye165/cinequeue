"""SQLite-backed watchlist repository."""

import sqlite3
from contextlib import contextmanager
from typing import Any

from app.config import DATA_DIR, DB_PATH
from app.repository import DuplicateItemError, WatchlistRepository


class SqliteWatchlistRepository(WatchlistRepository):
    """Watchlist repository backed by a local SQLite database."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_type TEXT NOT NULL CHECK(media_type IN ('movie', 'tv')),
                    tmdb_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    poster_path TEXT,
                    release_date TEXT,
                    added_at TEXT NOT NULL,
                    UNIQUE(media_type, tmdb_id)
                )
                """
            )

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- Repository interface --------------------------------------------------

    def list_items(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist ORDER BY added_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_item(
        self,
        media_type: str,
        tmdb_id: int,
        title: str,
        poster_path: str | None,
        release_date: str | None,
    ) -> dict[str, Any]:
        added_at = self.utc_now_iso()
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO watchlist (media_type, tmdb_id, title, poster_path, release_date, added_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (media_type, tmdb_id, title, poster_path, release_date, added_at),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateItemError(
                f"Item {media_type}/{tmdb_id} already exists"
            ) from exc

        return {
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "poster_path": poster_path,
            "release_date": release_date,
            "added_at": added_at,
        }

    def remove_item(self, media_type: str, tmdb_id: int) -> bool:
        with self._connection() as conn:
            result = conn.execute(
                "DELETE FROM watchlist WHERE media_type = ? AND tmdb_id = ?",
                (media_type, tmdb_id),
            )
            return result.rowcount > 0

    def clear_all(self) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM watchlist")
