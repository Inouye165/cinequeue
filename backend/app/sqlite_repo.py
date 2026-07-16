"""SQLite-backed watchlist repository."""

import json
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
                    user_id TEXT NOT NULL DEFAULT 'local_test_user',
                    media_type TEXT NOT NULL CHECK(media_type IN ('movie', 'tv')),
                    tmdb_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    poster_path TEXT,
                    release_date TEXT,
                    added_at TEXT NOT NULL,
                    is_owned INTEGER DEFAULT 0,
                    owned_format TEXT,
                    details_cached TEXT,
                    last_updated TEXT,
                    UNIQUE(user_id, media_type, tmdb_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    session_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY(username) REFERENCES admin_users(username)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_approvals (
                    email TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('approved', 'pending', 'revoked')),
                    requested_at TEXT NOT NULL,
                    decided_at TEXT,
                    decided_by TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT
                )
                """
            )
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local_test_user'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN is_owned INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN owned_format TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN details_cached TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN last_updated TEXT")
            except sqlite3.OperationalError:
                pass

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

    def list_items(self, user_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist WHERE user_id = ? ORDER BY added_at DESC",
                (user_id,),
            ).fetchall()
        
        items = []
        for row in rows:
            d = dict(row)
            d["is_owned"] = bool(d.get("is_owned"))
            items.append(d)
        return items

    def add_item(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        title: str,
        poster_path: str | None,
        release_date: str | None,
        is_owned: bool = False,
        owned_format: str | None = None,
    ) -> dict[str, Any]:
        added_at = self.utc_now_iso()
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO watchlist (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, is_owned, owned_format)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, 1 if is_owned else 0, owned_format),
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
            "is_owned": is_owned,
            "owned_format": owned_format,
        }

    def update_item(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        is_owned: bool,
        owned_format: str | None,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            # First check if item exists
            row = conn.execute(
                "SELECT * FROM watchlist WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            ).fetchone()
            if not row:
                return None

            conn.execute(
                """
                UPDATE watchlist
                SET is_owned = ?, owned_format = ?
                WHERE user_id = ? AND media_type = ? AND tmdb_id = ?
                """,
                (1 if is_owned else 0, owned_format, user_id, media_type, tmdb_id),
            )
            
            # Fetch updated item
            updated_row = conn.execute(
                "SELECT * FROM watchlist WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            ).fetchone()
        
        if updated_row:
            d = dict(updated_row)
            d["is_owned"] = bool(d.get("is_owned"))
            return d
        return None

    def update_item_cache(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        details_cached: dict[str, Any],
    ) -> None:
        last_updated = self.utc_now_iso()
        details_json = json.dumps(details_cached)
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE watchlist
                SET details_cached = ?, last_updated = ?
                WHERE user_id = ? AND media_type = ? AND tmdb_id = ?
                """,
                (details_json, last_updated, user_id, media_type, tmdb_id),
            )


    def remove_item(self, user_id: str, media_type: str, tmdb_id: int) -> bool:
        with self._connection() as conn:
            result = conn.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            )
            return result.rowcount > 0

    def clear_all(self, user_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM watchlist WHERE user_id = ?", (user_id,))

    # -- Admin & Auth Methods -------------------------------------------------

    def get_admin_user(self, username: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM admin_users WHERE username = ?", (username,)
            ).fetchone()
        return dict(row) if row else None

    def create_admin_user(self, username: str, password_hash: str, salt: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO admin_users (username, password_hash, salt)
                VALUES (?, ?, ?)
                """,
                (username, password_hash, salt),
            )

    def create_admin_session(self, session_id: str, username: str, expires_at: str) -> None:
        created_at = self.utc_now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO admin_sessions (session_id, username, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, username, created_at, expires_at),
            )

    def get_admin_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM admin_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_admin_session(self, session_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE session_id = ?", (session_id,))

    def get_user_approval(self, email: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_approvals WHERE email = ?", (email,)
            ).fetchone()
        return dict(row) if row else None

    def create_user_approval(self, email: str, status: str, requested_at: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO user_approvals (email, status, requested_at)
                VALUES (?, ?, ?)
                """,
                (email, status, requested_at),
            )

    def update_user_approval(self, email: str, status: str, decided_at: str, decided_by: str) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE user_approvals
                SET status = ?, decided_at = ?, decided_by = ?
                WHERE email = ?
                """,
                (status, decided_at, decided_by, email),
            )

    def list_user_approvals(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM user_approvals ORDER BY requested_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def log_login_attempt(
        self,
        email: str,
        status: str,
        reason: str,
        ip_address: str,
        user_agent: str,
        timestamp: str,
    ) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO login_logs (email, timestamp, status, reason, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (email, timestamp, status, reason, ip_address, user_agent),
            )

    def list_login_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM login_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

