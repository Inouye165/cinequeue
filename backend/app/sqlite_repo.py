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
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN target_rental_price REAL")
            except sqlite3.OperationalError:
                pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_settings (
                    user_id TEXT PRIMARY KEY,
                    personality_preset TEXT NOT NULL DEFAULT 'cinephile',
                    custom_prompt TEXT,
                    location TEXT DEFAULT '',
                    notify_on_login INTEGER DEFAULT 1,
                    auto_add_mentioned INTEGER DEFAULT 1,
                    track_price_drops INTEGER DEFAULT 1,
                    updated_at TEXT NOT NULL
                )
                """
            )
            try:
                conn.execute("ALTER TABLE agent_settings ADD COLUMN location TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    actions TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_query_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    title TEXT NOT NULL,
                    media_type TEXT,
                    tmdb_id INTEGER,
                    asked_at TEXT NOT NULL,
                    UNIQUE(user_id, title)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS briefing_presentations (
                    user_id TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    title_id TEXT,
                    source_id TEXT,
                    content_fingerprint TEXT NOT NULL,
                    first_discovered_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    first_presented_at TEXT NOT NULL,
                    last_presented_at TEXT NOT NULL,
                    presentation_count INTEGER DEFAULT 1,
                    importance INTEGER DEFAULT 3,
                    PRIMARY KEY (user_id, item_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_sessions (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    briefing_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, session_id)
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
            d["target_rental_price"] = d.get("target_rental_price")
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
        target_rental_price: float | None = None,
    ) -> dict[str, Any]:
        added_at = self.utc_now_iso()
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO watchlist (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, is_owned, owned_format, status, watch_free_streaming, watch_on_sale_buy, target_rental_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, 1 if is_owned else 0, owned_format, status, 1 if watch_free_streaming else 0, 1 if watch_on_sale_buy else 0, target_rental_price),
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
            "target_rental_price": target_rental_price,
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
        target_rental_price: float | None = None,
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
            current_target_price = row["target_rental_price"] if target_rental_price is None else target_rental_price

            conn.execute(
                """
                UPDATE watchlist
                SET is_owned = ?, owned_format = ?, status = ?, watch_free_streaming = ?, watch_on_sale_buy = ?, target_rental_price = ?
                WHERE user_id = ? AND media_type = ? AND tmdb_id = ?
                """,
                (1 if current_is_owned else 0, current_owned_format, current_status, 1 if current_watch_free else 0, 1 if current_watch_sale else 0, current_target_price, user_id, media_type, tmdb_id),
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
            d["target_rental_price"] = d.get("target_rental_price")
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

    def get_agent_settings(self, user_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return {
                "user_id": user_id,
                "personality_preset": "cinephile",
                "custom_prompt": "",
                "location": "",
                "notify_on_login": True,
                "auto_add_mentioned": True,
                "track_price_drops": True,
                "updated_at": self.utc_now_iso(),
            }
        keys = row.keys()
        return {
            "user_id": row["user_id"],
            "personality_preset": row["personality_preset"],
            "custom_prompt": row["custom_prompt"] or "",
            "location": row["location"] if ("location" in keys and row["location"]) else "",
            "notify_on_login": bool(row["notify_on_login"]),
            "auto_add_mentioned": bool(row["auto_add_mentioned"]),
            "track_price_drops": bool(row["track_price_drops"]),
            "updated_at": row["updated_at"],
        }

    def save_agent_settings(self, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        preset = settings.get("personality_preset", "cinephile")
        custom_prompt = settings.get("custom_prompt", "")
        location = settings.get("location", "").strip()
        notify_on_login = 1 if settings.get("notify_on_login", True) else 0
        auto_add_mentioned = 1 if settings.get("auto_add_mentioned", True) else 0
        track_price_drops = 1 if settings.get("track_price_drops", True) else 0

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_settings (user_id, personality_preset, custom_prompt, location, notify_on_login, auto_add_mentioned, track_price_drops, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    personality_preset = excluded.personality_preset,
                    custom_prompt = excluded.custom_prompt,
                    location = excluded.location,
                    notify_on_login = excluded.notify_on_login,
                    auto_add_mentioned = excluded.auto_add_mentioned,
                    track_price_drops = excluded.track_price_drops,
                    updated_at = excluded.updated_at
                """,
                (user_id, preset, custom_prompt, location, notify_on_login, auto_add_mentioned, track_price_drops, now),
            )
        return self.get_agent_settings(user_id)

    def update_agent_last_login(self, user_id: str, timestamp: str) -> None:
        now = self.utc_now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_settings (user_id, updated_at)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (user_id, now),
            )

    def list_chat_messages(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_conversations
                WHERE user_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("actions"):
                try:
                    d["actions"] = json.loads(d["actions"])
                except Exception:
                    d["actions"] = []
            else:
                d["actions"] = []
            result.append(d)
        return result

    def add_chat_message(
        self,
        user_id: str,
        role: str,
        content: str,
        actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = self.utc_now_iso()
        actions_json = json.dumps(actions) if actions else None
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_conversations (user_id, role, content, actions, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, role, content, actions_json, now),
            )
            msg_id = cursor.lastrowid
        return {
            "id": msg_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "actions": actions or [],
            "created_at": now,
        }

    def clear_chat_messages(self, user_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM agent_conversations WHERE user_id = ?", (user_id,))

    def add_query_memory(
        self,
        user_id: str,
        query_text: str,
        tmdb_id: int | None = None,
        media_type: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        now = self.utc_now_iso()
        item_title = title or query_text
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_query_memory (user_id, query_text, title, media_type, tmdb_id, asked_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, title) DO UPDATE SET
                    query_text = excluded.query_text,
                    asked_at = excluded.asked_at,
                    tmdb_id = COALESCE(excluded.tmdb_id, agent_query_memory.tmdb_id),
                    media_type = COALESCE(excluded.media_type, agent_query_memory.media_type)
                """,
                (user_id, query_text, item_title, media_type, tmdb_id, now),
            )
            row = conn.execute(
                "SELECT * FROM agent_query_memory WHERE user_id = ? AND title = ?",
                (user_id, item_title),
            ).fetchone()
        return dict(row) if row else {"user_id": user_id, "title": item_title, "asked_at": now}

    def list_query_memories(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM agent_query_memory
                WHERE user_id = ?
                ORDER BY asked_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def remove_query_memory(self, user_id: str, memory_id: Any) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_query_memory WHERE user_id = ? AND (id = ? OR title = ?)",
                (user_id, memory_id, str(memory_id)),
            )
            return cursor.rowcount > 0

    def record_briefing_presentations(self, user_id: str, items: list[dict[str, Any]]) -> None:
        now = self.utc_now_iso()
        with self._connection() as conn:
            for item in items:
                item_key = item["item_key"]
                item_type = item.get("type", "unknown")
                title_id = str(item.get("title_id") or "")
                source_id = str(item.get("source_id") or "")
                content_fp = str(item.get("content_fingerprint") or "")
                importance = int(item.get("urgency", 3))

                conn.execute(
                    """
                    INSERT INTO briefing_presentations (
                        user_id, item_key, item_type, title_id, source_id,
                        content_fingerprint, first_discovered_at, last_updated_at,
                        first_presented_at, last_presented_at, presentation_count, importance
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(user_id, item_key) DO UPDATE SET
                        content_fingerprint = excluded.content_fingerprint,
                        last_updated_at = excluded.last_updated_at,
                        last_presented_at = excluded.last_presented_at,
                        presentation_count = briefing_presentations.presentation_count + 1,
                        importance = excluded.importance
                    """,
                    (
                        user_id, item_key, item_type, title_id, source_id,
                        content_fp, now, now, now, now, importance
                    ),
                )

    def get_presented_briefing_keys(self, user_id: str) -> dict[str, dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM briefing_presentations WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {r["item_key"]: dict(r) for r in rows}

    def get_agent_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT briefing_json FROM agent_sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).fetchone()
        if row and row["briefing_json"]:
            try:
                return json.loads(row["briefing_json"])
            except Exception:
                pass
        return None

    def save_agent_session(self, user_id: str, session_id: str, briefing_data: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        briefing_json = json.dumps(briefing_data)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_sessions (user_id, session_id, briefing_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    briefing_json = excluded.briefing_json,
                    created_at = excluded.created_at
                """,
                (user_id, session_id, briefing_json, now),
            )
        return briefing_data



