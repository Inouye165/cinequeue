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
                    status TEXT DEFAULT 'queue',
                    watch_free_streaming INTEGER DEFAULT 0,
                    watch_on_sale_buy INTEGER DEFAULT 0,
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
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN status TEXT DEFAULT 'queue'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN watch_free_streaming INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN watch_on_sale_buy INTEGER DEFAULT 0")
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
            d["status"] = d.get("status") or "queue"
            d["watch_free_streaming"] = bool(d.get("watch_free_streaming"))
            d["watch_on_sale_buy"] = bool(d.get("watch_on_sale_buy"))
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
        status: str = "queue",
        watch_free_streaming: bool = False,
        watch_on_sale_buy: bool = False,
    ) -> dict[str, Any]:
        added_at = self.utc_now_iso()
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO watchlist (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, is_owned, owned_format, status, watch_free_streaming, watch_on_sale_buy)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, 1 if is_owned else 0, owned_format, status, 1 if watch_free_streaming else 0, 1 if watch_on_sale_buy else 0),
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
            "status": status,
            "watch_free_streaming": watch_free_streaming,
            "watch_on_sale_buy": watch_on_sale_buy,
        }

    def update_item(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        is_owned: bool | None = None,
        owned_format: str | None = None,
        status: str | None = None,
        watch_free_streaming: bool | None = None,
        watch_on_sale_buy: bool | None = None,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            # First check if item exists
            row = conn.execute(
                "SELECT * FROM watchlist WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            ).fetchone()
            if not row:
                return None

            current_is_owned = bool(row["is_owned"]) if is_owned is None else is_owned
            current_owned_format = row["owned_format"] if is_owned is None else owned_format
            if current_is_owned is False:
                current_owned_format = None
            current_status = row["status"] if status is None else status
            current_watch_free = bool(row["watch_free_streaming"]) if watch_free_streaming is None else watch_free_streaming
            current_watch_sale = bool(row["watch_on_sale_buy"]) if watch_on_sale_buy is None else watch_on_sale_buy

            conn.execute(
                """
                UPDATE watchlist
                SET is_owned = ?, owned_format = ?, status = ?, watch_free_streaming = ?, watch_on_sale_buy = ?
                WHERE user_id = ? AND media_type = ? AND tmdb_id = ?
                """,
                (1 if current_is_owned else 0, current_owned_format, current_status, 1 if current_watch_free else 0, 1 if current_watch_sale else 0, user_id, media_type, tmdb_id),
            )
            
            # Fetch updated item
            updated_row = conn.execute(
                "SELECT * FROM watchlist WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            ).fetchone()
        
        if updated_row:
            d = dict(updated_row)
            d["is_owned"] = bool(d.get("is_owned"))
            d["status"] = d.get("status") or "queue"
            d["watch_free_streaming"] = bool(d.get("watch_free_streaming"))
            d["watch_on_sale_buy"] = bool(d.get("watch_on_sale_buy"))
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
        username_normalized = username.strip().lower()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM admin_users WHERE LOWER(username) = ?", (username_normalized,)
            ).fetchone()
        return dict(row) if row else None

    def create_admin_user(self, username: str, password_hash: str, salt: str) -> None:
        username_normalized = username.strip().lower()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO admin_users (username, password_hash, salt)
                VALUES (?, ?, ?)
                """,
                (username_normalized, password_hash, salt),
            )

    def list_admin_users(self) -> list[str]:
        with self._connection() as conn:
            rows = conn.execute("SELECT username FROM admin_users ORDER BY username").fetchall()
        return [row["username"] for row in rows]

    def delete_admin_user(self, username: str) -> bool:
        username_normalized = username.strip().lower()
        with self._connection() as conn:
            conn.execute("DELETE FROM admin_sessions WHERE LOWER(username) = ?", (username_normalized,))
            result = conn.execute("DELETE FROM admin_users WHERE LOWER(username) = ?", (username_normalized,))
            return result.rowcount > 0

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

