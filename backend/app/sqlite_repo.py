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
                    target_rental_price REAL,
                    user_rating INTEGER DEFAULT 0,
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
            try:
                conn.execute("ALTER TABLE watchlist ADD COLUMN user_rating INTEGER DEFAULT 0")
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
                conn.execute("ALTER TABLE agent_settings ADD COLUMN personality_preset TEXT NOT NULL DEFAULT 'cinephile'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE agent_settings ADD COLUMN custom_prompt TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE agent_settings ADD COLUMN location TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE agent_settings ADD COLUMN previous_login_at TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE agent_settings ADD COLUMN previous_briefing_presented_at TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE agent_settings ADD COLUMN auto_speak_briefing INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE agent_settings ADD COLUMN timezone TEXT DEFAULT 'America/Los_Angeles'")
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
                    story_cluster_id TEXT,
                    news_item_id TEXT,
                    related_title_id TEXT,
                    news_category TEXT,
                    item_type TEXT NOT NULL,
                    title_id TEXT,
                    source_id TEXT,
                    content_fingerprint TEXT NOT NULL,
                    first_discovered_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL,
                    last_material_change_at TEXT,
                    first_presented_at TEXT NOT NULL,
                    last_presented_at TEXT NOT NULL,
                    presentation_count INTEGER DEFAULT 1,
                    importance INTEGER DEFAULT 3,
                    importance_score INTEGER DEFAULT 3,
                    acknowledged INTEGER DEFAULT 0,
                    dismissed INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, item_key)
                )
                """
            )
            for col_def in [
                "story_cluster_id TEXT",
                "news_item_id TEXT",
                "related_title_id TEXT",
                "news_category TEXT",
                "last_material_change_at TEXT",
                "importance_score INTEGER DEFAULT 3",
                "acknowledged INTEGER DEFAULT 0",
                "dismissed INTEGER DEFAULT 0",
            ]:
                try:
                    conn.execute(f"ALTER TABLE briefing_presentations ADD COLUMN {col_def}")
                except sqlite3.OperationalError:
                    pass
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_greetings (
                    user_id TEXT NOT NULL,
                    date_str TEXT NOT NULL,
                    briefing_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, date_str)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rated_movies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'local_test_user',
                    media_type TEXT NOT NULL CHECK(media_type IN ('movie', 'tv')),
                    tmdb_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    poster_path TEXT,
                    release_date TEXT,
                    rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                    rated_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, media_type, tmdb_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_decision_logs (
                    log_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL DEFAULT 'startup_briefing_candidate_decision',
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT,
                    model_requested TEXT,
                    model_used TEXT,
                    gemini_called INTEGER DEFAULT 0,
                    fallback_used INTEGER DEFAULT 0,
                    fallback_reason TEXT,
                    decision_config_version INTEGER DEFAULT 1,
                    prompt_version INTEGER DEFAULT 1,
                    required_candidates_json TEXT,
                    optional_candidates_json TEXT,
                    selected_candidates_json TEXT,
                    excluded_candidates_json TEXT,
                    random_rolls_json TEXT,
                    cooldowns_applied_json TEXT,
                    selection_summary TEXT,
                    sanitized_prompt TEXT,
                    raw_model_response TEXT,
                    final_response TEXT,
                    request_duration_ms REAL DEFAULT 0.0,
                    daily_cache_key TEXT,
                    attempt_number INTEGER,
                    is_fallback_attempt INTEGER,
                    http_status INTEGER,
                    success INTEGER,
                    error_type TEXT,
                    gemini_request_id TEXT,
                    model_attempted TEXT
                )
                """
            )

            existing_cols = {col[1] for col in conn.execute("PRAGMA table_info(agent_decision_logs)").fetchall()}
            new_cols = [
                ("daily_cache_key", "TEXT"),
                ("attempt_number", "INTEGER"),
                ("is_fallback_attempt", "INTEGER"),
                ("http_status", "INTEGER"),
                ("success", "INTEGER"),
                ("error_type", "TEXT"),
                ("gemini_request_id", "TEXT"),
                ("model_attempted", "TEXT"),
                ("telemetry_version", "INTEGER DEFAULT 1"),
                ("briefing_run_id", "TEXT"),
                ("request_id", "TEXT"),
                ("started_at", "TEXT"),
                ("completed_at", "TEXT"),
                ("total_duration_ms", "REAL"),
                ("force_refresh", "INTEGER"),
                ("user_timezone", "TEXT"),
                ("resolved_local_date", "TEXT"),
                ("server_date", "TEXT"),
                ("result_source", "TEXT"),
                ("final_status", "TEXT"),
                ("response_text_length", "INTEGER"),
                ("daily_cache_result", "TEXT"),
                ("daily_cache_backend", "TEXT"),
                ("candidate_signature", "TEXT"),
                ("gemini_attempt_count", "INTEGER"),
                ("fallback_attempted", "INTEGER"),
                ("fallback_trigger", "TEXT"),
                ("final_model", "TEXT"),
                ("external_attempt_counts_json", "TEXT"),
                ("external_cache_hit_counts_json", "TEXT"),
                ("timeline_json", "TEXT"),
            ]
            for col_name, col_type in new_cols:
                if col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE agent_decision_logs ADD COLUMN {col_name} {col_type}")
                    except sqlite3.OperationalError:
                        pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_decision_configs (
                    version INTEGER PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    change_note TEXT,
                    config_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_prompt_versions (
                    version INTEGER PRIMARY KEY,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    change_note TEXT,
                    prompt_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trivia_facts (
                    fact_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    tmdb_id INTEGER,
                    media_type TEXT DEFAULT 'movie',
                    fact_text TEXT NOT NULL,
                    source TEXT DEFAULT 'verified_archive',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trivia_presentation_history (
                    user_id TEXT NOT NULL,
                    fact_id TEXT NOT NULL,
                    presented_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, fact_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS news_presentation_history (
                    user_id TEXT NOT NULL,
                    story_cluster_id TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    presented_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, story_cluster_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entertainment_news (
                    story_id TEXT PRIMARY KEY,
                    story_cluster_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    source TEXT NOT NULL,
                    news_category TEXT DEFAULT 'official_announcement',
                    is_major INTEGER DEFAULT 1,
                    is_rumor INTEGER DEFAULT 0,
                    published_at TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL
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
            d["user_rating"] = int(d.get("user_rating") or 0)
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
        user_rating: int = 0,
    ) -> dict[str, Any]:
        added_at = self.utc_now_iso()
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO watchlist (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, is_owned, owned_format, status, watch_free_streaming, watch_on_sale_buy, target_rental_price, user_rating)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, media_type, tmdb_id, title, poster_path, release_date, added_at, 1 if is_owned else 0, owned_format, status, 1 if watch_free_streaming else 0, 1 if watch_on_sale_buy else 0, target_rental_price, user_rating),
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
            "user_rating": user_rating,
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
        user_rating: int | None = None,
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
            current_user_rating = int(row["user_rating"]) if (user_rating is None and "user_rating" in row.keys() and row["user_rating"] is not None) else (user_rating or 0)

            conn.execute(
                """
                UPDATE watchlist
                SET is_owned = ?, owned_format = ?, status = ?, watch_free_streaming = ?, watch_on_sale_buy = ?, target_rental_price = ?, user_rating = ?
                WHERE user_id = ? AND media_type = ? AND tmdb_id = ?
                """,
                (1 if current_is_owned else 0, current_owned_format, current_status, 1 if current_watch_free else 0, 1 if current_watch_sale else 0, current_target_price, current_user_rating, user_id, media_type, tmdb_id),
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
            d["user_rating"] = int(d.get("user_rating") or 0)
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
                "timezone": "America/Los_Angeles",
                "user_timezone": "America/Los_Angeles",
                "notify_on_login": True,
                "auto_add_mentioned": True,
                "track_price_drops": True,
                "auto_speak_briefing": False,
                "updated_at": self.utc_now_iso(),
            }
        keys = row.keys()
        tz = (row["timezone"] if ("timezone" in keys and row["timezone"]) else (row["user_timezone"] if ("user_timezone" in keys and row["user_timezone"]) else "America/Los_Angeles"))
        return {
            "user_id": row["user_id"],
            "personality_preset": row["personality_preset"],
            "custom_prompt": row["custom_prompt"] or "",
            "location": row["location"] if ("location" in keys and row["location"]) else "",
            "timezone": tz,
            "user_timezone": tz,
            "notify_on_login": bool(row["notify_on_login"]),
            "auto_add_mentioned": bool(row["auto_add_mentioned"]),
            "track_price_drops": bool(row["track_price_drops"]),
            "auto_speak_briefing": bool(row["auto_speak_briefing"]) if ("auto_speak_briefing" in keys and row["auto_speak_briefing"] is not None) else False,
            "updated_at": row["updated_at"],
        }

    def save_agent_settings(self, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        preset = settings.get("personality_preset", "cinephile")
        custom_prompt = settings.get("custom_prompt", "")
        location = settings.get("location", "").strip()
        tz = (settings.get("timezone") or settings.get("user_timezone") or "America/Los_Angeles").strip()
        notify_on_login = 1 if settings.get("notify_on_login", True) else 0
        auto_add_mentioned = 1 if settings.get("auto_add_mentioned", True) else 0
        track_price_drops = 1 if settings.get("track_price_drops", True) else 0

        auto_speak_briefing = 1 if settings.get("auto_speak_briefing", False) else 0

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_settings (user_id, personality_preset, custom_prompt, location, timezone, notify_on_login, auto_add_mentioned, track_price_drops, auto_speak_briefing, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    personality_preset = excluded.personality_preset,
                    custom_prompt = excluded.custom_prompt,
                    location = excluded.location,
                    timezone = excluded.timezone,
                    notify_on_login = excluded.notify_on_login,
                    auto_add_mentioned = excluded.auto_add_mentioned,
                    track_price_drops = excluded.track_price_drops,
                    auto_speak_briefing = excluded.auto_speak_briefing,
                    updated_at = excluded.updated_at
                """,
                (user_id, preset, custom_prompt, location, tz, notify_on_login, auto_add_mentioned, track_price_drops, auto_speak_briefing, now),
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
                SELECT * FROM (
                    SELECT * FROM agent_conversations
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
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
                item_key = item.get("item_key") or item.get("story_cluster_id") or f"item_{item.get('title_id', 'gen')}"
                item_type = item.get("type") or item.get("category", "unknown")
                title_id = str(item.get("title_id") or "")
                source_id = str(item.get("source") or item.get("source_id") or "")
                content_fp = str(item.get("content_fingerprint") or "")
                importance = int(item.get("importance_score") or item.get("urgency", 3))
                story_cluster_id = str(item.get("story_cluster_id") or item_key)
                news_item_id = str(item.get("news_item_id") or item_key)
                related_title_id = str(item.get("title_id") or "")
                news_category = str(item.get("category") or item_type)
                last_mat_change = str(item.get("last_material_change_at") or now)

                conn.execute(
                    """
                    INSERT INTO briefing_presentations (
                        user_id, item_key, story_cluster_id, news_item_id, related_title_id, news_category,
                        item_type, title_id, source_id, content_fingerprint, first_discovered_at, last_updated_at,
                        last_material_change_at, first_presented_at, last_presented_at, presentation_count,
                        importance, importance_score, acknowledged, dismissed
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 0, 0)
                    ON CONFLICT(user_id, item_key) DO UPDATE SET
                        content_fingerprint = excluded.content_fingerprint,
                        last_updated_at = excluded.last_updated_at,
                        last_material_change_at = excluded.last_material_change_at,
                        last_presented_at = excluded.last_presented_at,
                        presentation_count = briefing_presentations.presentation_count + 1,
                        importance = excluded.importance,
                        importance_score = excluded.importance_score
                    """,
                    (
                        user_id, item_key, story_cluster_id, news_item_id, related_title_id, news_category,
                        item_type, title_id, source_id, content_fp, now, now, last_mat_change, now, now,
                        importance, importance
                    ),
                )

    def get_presented_briefing_keys(self, user_id: str) -> dict[str, dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM briefing_presentations WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {r["item_key"]: dict(r) for r in rows}

    def get_user_briefing_state(self, user_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT previous_login_at, previous_briefing_presented_at, updated_at FROM agent_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return {"previous_login_at": None, "previous_briefing_presented_at": None}
        return {
            "previous_login_at": row["previous_login_at"],
            "previous_briefing_presented_at": row["previous_briefing_presented_at"],
        }

    def update_user_briefing_state(
        self,
        user_id: str,
        login_at: str | None = None,
        briefing_presented_at: str | None = None,
    ) -> None:
        now = self.utc_now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_settings (user_id, previous_login_at, previous_briefing_presented_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    previous_login_at = COALESCE(excluded.previous_login_at, agent_settings.previous_login_at),
                    previous_briefing_presented_at = COALESCE(excluded.previous_briefing_presented_at, agent_settings.previous_briefing_presented_at),
                    updated_at = excluded.updated_at
                """,
                (user_id, login_at, briefing_presented_at, now),
            )

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

    def get_daily_greeting(self, user_id: str, date_str: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT briefing_json FROM daily_greetings WHERE user_id = ? AND date_str = ?",
                (user_id, date_str),
            ).fetchone()
        if row and row["briefing_json"]:
            try:
                return json.loads(row["briefing_json"])
            except Exception:
                pass
        return None

    def claim_daily_greeting_generation(
        self, user_id: str, date_str: str, lease_seconds: int = 30, force_refresh: bool = False
    ) -> tuple[bool, dict[str, Any] | None]:
        from datetime import datetime, timezone, timedelta
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        lease_exp = (now_dt + timedelta(seconds=lease_seconds)).isoformat()

        with self._connection() as conn:
            row = conn.execute(
                "SELECT briefing_json FROM daily_greetings WHERE user_id = ? AND date_str = ?",
                (user_id, date_str),
            ).fetchone()

            if row and row["briefing_json"] and not force_refresh:
                try:
                    data = json.loads(row["briefing_json"])
                    status = data.get("status", "completed")
                    exp_str = data.get("lease_expires_at")

                    if status == "completed":
                        return False, data

                    if status == "generating" and exp_str:
                        try:
                            exp_dt = datetime.fromisoformat(exp_str)
                            if exp_dt > now_dt:
                                return False, data
                        except Exception:
                            pass
                except Exception:
                    pass

            claiming_record = {
                "user_id": user_id,
                "date_str": date_str,
                "status": "generating",
                "lease_expires_at": lease_exp,
                "created_at": now_iso,
            }
            claiming_json = json.dumps(claiming_record)

            conn.execute(
                """
                INSERT INTO daily_greetings (user_id, date_str, briefing_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, date_str) DO UPDATE SET
                    briefing_json = excluded.briefing_json,
                    created_at = excluded.created_at
                """,
                (user_id, date_str, claiming_json, now_iso),
            )

        return True, None

    def save_daily_greeting(self, user_id: str, date_str: str, briefing_data: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        briefing_data.setdefault("status", "completed")
        briefing_json = json.dumps(briefing_data)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO daily_greetings (user_id, date_str, briefing_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, date_str) DO UPDATE SET
                    briefing_json = excluded.briefing_json,
                    created_at = excluded.created_at
                """,
                (user_id, date_str, briefing_json, now),
            )
        return briefing_data

    def list_rated_movies(self, user_id: str) -> list[dict[str, Any]]:
        from app.models import poster_url
        from datetime import datetime, timezone

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM rated_movies
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()

        now = datetime.now(timezone.utc)
        results = []
        for r in rows:
            d = dict(r)
            p_path = d.get("poster_path")
            d["poster_url"] = poster_url(p_path) if p_path else None
            # Calculate time ago
            rated_at_str = d.get("updated_at") or d.get("rated_at")
            rated_ago = "recently"
            if rated_at_str:
                try:
                    dt = datetime.fromisoformat(rated_at_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    seconds = int((now - dt).total_seconds())
                    if seconds < 60:
                        rated_ago = "just now"
                    elif seconds < 3600:
                        mins = seconds // 60
                        rated_ago = f"{mins} min{'s' if mins > 1 else ''} ago"
                    elif seconds < 86400:
                        hrs = seconds // 3600
                        rated_ago = f"{hrs} hour{'s' if hrs > 1 else ''} ago"
                    elif seconds < 2592000:
                        days = seconds // 86400
                        rated_ago = f"{days} day{'s' if days > 1 else ''} ago"
                    elif seconds < 31536000:
                        months = seconds // 2592000
                        rated_ago = f"{months} month{'s' if months > 1 else ''} ago"
                    else:
                        yrs = seconds // 31536000
                        rated_ago = f"{yrs} year{'s' if yrs > 1 else ''} ago"
                except Exception:
                    rated_ago = "recently"
            d["rated_ago"] = rated_ago
            results.append(d)
        return results

    def rate_movie(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        title: str,
        poster_path: str | None,
        release_date: str | None,
        rating: int,
    ) -> dict[str, Any]:
        now = self.utc_now_iso()
        # Clamp rating between 1 and 5
        rating = max(1, min(5, int(rating)))
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO rated_movies (user_id, media_type, tmdb_id, title, poster_path, release_date, rating, rated_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, media_type, tmdb_id) DO UPDATE SET
                    title = excluded.title,
                    poster_path = COALESCE(excluded.poster_path, rated_movies.poster_path),
                    release_date = COALESCE(excluded.release_date, rated_movies.release_date),
                    rating = excluded.rating,
                    updated_at = excluded.updated_at
                """,
                (user_id, media_type, tmdb_id, title, poster_path, release_date, rating, now, now),
            )
            # Synchronize user_rating in watchlist if present
            conn.execute(
                """
                UPDATE watchlist SET user_rating = ?
                WHERE user_id = ? AND media_type = ? AND tmdb_id = ?
                """,
                (rating, user_id, media_type, tmdb_id),
            )
        # Fetch updated record
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM rated_movies WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            ).fetchone()
        d = dict(row) if row else {}
        d["rated_ago"] = "just now"
        from app.models import poster_url
        if d.get("poster_path"):
            d["poster_url"] = poster_url(d["poster_path"])
        return d

    def delete_rated_movie(self, user_id: str, media_type: str, tmdb_id: int) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM rated_movies WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            )
            row = conn.execute(
                "SELECT * FROM watchlist WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                (user_id, media_type, tmdb_id),
            ).fetchone()
            if row:
                if not bool(row["is_owned"]) and (row["status"] == "watched" or not row["status"]):
                    conn.execute(
                        "DELETE FROM watchlist WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                        (user_id, media_type, tmdb_id),
                    )
                else:
                    conn.execute(
                        "UPDATE watchlist SET user_rating = 0 WHERE user_id = ? AND media_type = ? AND tmdb_id = ?",
                        (user_id, media_type, tmdb_id),
                    )
            return cursor.rowcount > 0 or (row is not None)

    # -- Decision Engine Repository Extensions --------------------------------

    def add_decision_log(self, log_dict: dict[str, Any]) -> dict[str, Any]:
        from app.decision_models import scrub_secrets
        clean_dict = scrub_secrets(log_dict)
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_decision_logs (
                        log_id, event_type, timestamp, user_id, session_id,
                        model_requested, model_used, gemini_called, fallback_used, fallback_reason,
                        decision_config_version, prompt_version, required_candidates_json,
                        optional_candidates_json, selected_candidates_json, excluded_candidates_json,
                        random_rolls_json, cooldowns_applied_json, selection_summary,
                        sanitized_prompt, raw_model_response, final_response, request_duration_ms,
                        daily_cache_key, attempt_number, is_fallback_attempt, http_status,
                        success, error_type, gemini_request_id, model_attempted,
                        telemetry_version, briefing_run_id, request_id, started_at, completed_at,
                        total_duration_ms, force_refresh, user_timezone, resolved_local_date,
                        server_date, result_source, final_status, response_text_length,
                        daily_cache_result, daily_cache_backend, candidate_signature,
                        gemini_attempt_count, fallback_attempted, fallback_trigger, final_model,
                        external_attempt_counts_json, external_cache_hit_counts_json, timeline_json
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?
                    )
                    """,
                    (
                        clean_dict["log_id"],
                        clean_dict.get("event_type", "startup_briefing_candidate_decision"),
                        clean_dict["timestamp"],
                        clean_dict["user_id"],
                        clean_dict.get("session_id"),
                        clean_dict.get("model_requested"),
                        clean_dict.get("model_used"),
                        1 if clean_dict.get("gemini_called") is True else 0,
                        1 if clean_dict.get("fallback_used", False) else 0,
                        clean_dict.get("fallback_reason"),
                        clean_dict.get("decision_config_version", 1),
                        clean_dict.get("prompt_version", 1),
                        json.dumps(clean_dict.get("required_candidates", [])),
                        json.dumps(clean_dict.get("optional_candidates", [])),
                        json.dumps(clean_dict.get("selected_candidates", [])),
                        json.dumps(clean_dict.get("excluded_candidates", [])),
                        json.dumps(clean_dict.get("random_rolls", {})),
                        json.dumps(clean_dict.get("cooldowns_applied", [])),
                        clean_dict.get("selection_summary", ""),
                        clean_dict.get("sanitized_prompt", ""),
                        clean_dict.get("raw_model_response", ""),
                        clean_dict.get("final_response", ""),
                        clean_dict.get("request_duration_ms", 0.0),
                        clean_dict.get("daily_cache_key"),
                        clean_dict.get("attempt_number"),
                        1 if clean_dict.get("is_fallback_attempt") is True else (0 if clean_dict.get("is_fallback_attempt") is False else None),
                        clean_dict.get("http_status"),
                        1 if clean_dict.get("success") is True else (0 if clean_dict.get("success") is False else None),
                        clean_dict.get("error_type"),
                        clean_dict.get("gemini_request_id"),
                        clean_dict.get("model_attempted"),
                        clean_dict.get("telemetry_version", 2),
                        clean_dict.get("briefing_run_id"),
                        clean_dict.get("request_id"),
                        clean_dict.get("started_at"),
                        clean_dict.get("completed_at"),
                        clean_dict.get("total_duration_ms"),
                        1 if clean_dict.get("force_refresh") is True else 0,
                        clean_dict.get("user_timezone", "UTC"),
                        clean_dict.get("resolved_local_date"),
                        clean_dict.get("server_date"),
                        clean_dict.get("result_source"),
                        clean_dict.get("final_status"),
                        clean_dict.get("response_text_length", 0),
                        clean_dict.get("daily_cache_result"),
                        clean_dict.get("daily_cache_backend", "sqlite"),
                        clean_dict.get("candidate_signature"),
                        clean_dict.get("gemini_attempt_count", 0),
                        1 if clean_dict.get("fallback_attempted") is True else 0,
                        clean_dict.get("fallback_trigger"),
                        clean_dict.get("final_model"),
                        json.dumps(clean_dict.get("external_attempt_counts", {})),
                        json.dumps(clean_dict.get("external_cache_hit_counts", {})),
                        json.dumps(clean_dict.get("timeline", [])),
                    ),
                )
        except Exception as e:
            logger.warning(f"Failed to persist decision log '{clean_dict.get('log_id')}': {e}")
        return clean_dict

    def list_decision_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
        candidate_type: str | None = None,
        required_only: bool | None = None,
        fallback_only: bool | None = None,
        model: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        conditions = []
        params = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        if fallback_only:
            conditions.append("fallback_used = 1")

        if model:
            conditions.append("(model_requested = ? OR model_used = ?)")
            params.extend([model, model])

        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)

        if candidate_type:
            conditions.append("(selected_candidates_json LIKE ? OR optional_candidates_json LIKE ? OR required_candidates_json LIKE ?)")
            pat = f"%{candidate_type}%"
            params.extend([pat, pat, pat])

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        with self._connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM agent_decision_logs{where_clause}", params).fetchone()[0]
            query = f"SELECT * FROM agent_decision_logs{where_clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            rows = conn.execute(query, params + [limit, offset]).fetchall()

        logs = [self._format_decision_log_row(dict(r)) for r in rows]
        return {"total": total, "logs": logs, "limit": limit, "offset": offset}

    def _format_decision_log_row(self, d: dict[str, Any]) -> dict[str, Any]:
        d["gemini_called"] = bool(d.get("gemini_called"))
        d["fallback_used"] = bool(d.get("fallback_used"))
        d["is_fallback_attempt"] = bool(d.get("is_fallback_attempt")) if d.get("is_fallback_attempt") is not None else None
        d["success"] = bool(d.get("success")) if d.get("success") is not None else None
        d["force_refresh"] = bool(d.get("force_refresh"))
        d["fallback_attempted"] = bool(d.get("fallback_attempted"))

        for json_col, default in [
            ("required_candidates_json", []),
            ("optional_candidates_json", []),
            ("selected_candidates_json", []),
            ("excluded_candidates_json", []),
            ("random_rolls_json", {}),
            ("cooldowns_applied_json", []),
            ("external_attempt_counts_json", {}),
            ("external_cache_hit_counts_json", {}),
            ("timeline_json", []),
        ]:
            key = json_col.replace("_json", "")
            raw_val = d.get(json_col)
            if raw_val:
                try:
                    d[key] = json.loads(raw_val)
                except Exception:
                    d[key] = default
            else:
                if key not in d or d[key] is None:
                    d[key] = default

        t_ver = d.get("telemetry_version")
        if t_ver != 2 or d.get("event_type") == "startup_briefing_decision":
            d["is_legacy"] = True
            summary = d.get("selection_summary", "")
            if "Legacy Candidate Decision — Gemini Call Unverified" not in summary:
                d["selection_summary"] = f"Legacy Candidate Decision — Gemini Call Unverified: {summary}".strip(": ")
        else:
            d["is_legacy"] = False

        return d

    def get_decision_log(self, log_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM agent_decision_logs WHERE log_id = ?", (log_id,)).fetchone()
        if not row:
            return None
        return self._format_decision_log_row(dict(row))

    def get_active_decision_config(self) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute("SELECT config_json FROM agent_decision_configs ORDER BY version DESC LIMIT 1").fetchone()
        if row and row["config_json"]:
            try:
                return json.loads(row["config_json"])
            except Exception:
                pass
        from app.decision_models import DEFAULT_DECISION_CONFIG
        return DEFAULT_DECISION_CONFIG.to_dict()

    def save_decision_config(self, config_dict: dict[str, Any], updated_by: str, change_note: str) -> dict[str, Any]:
        with self._connection() as conn:
            max_row = conn.execute("SELECT MAX(version) FROM agent_decision_configs").fetchone()
            new_ver = (max_row[0] or 0) + 1 if max_row else 1
            config_dict["version"] = new_ver
            config_dict["updated_at"] = self.utc_now_iso()
            config_dict["updated_by"] = updated_by
            config_dict["change_note"] = change_note

            conn.execute(
                """
                INSERT INTO agent_decision_configs (version, updated_at, updated_by, change_note, config_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_ver, config_dict["updated_at"], updated_by, change_note, json.dumps(config_dict)),
            )
        return config_dict

    def get_active_prompt_version(self) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute("SELECT prompt_json FROM agent_prompt_versions ORDER BY version DESC LIMIT 1").fetchone()
        if row and row["prompt_json"]:
            try:
                return json.loads(row["prompt_json"])
            except Exception:
                pass
        from app.decision_models import DEFAULT_PROMPT_VERSION
        return DEFAULT_PROMPT_VERSION.to_dict()

    def list_prompt_versions(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT prompt_json FROM agent_prompt_versions ORDER BY version DESC").fetchall()
        results = []
        for r in rows:
            if r["prompt_json"]:
                try:
                    results.append(json.loads(r["prompt_json"]))
                except Exception:
                    pass
        if not results:
            from app.decision_models import DEFAULT_PROMPT_VERSION
            results = [DEFAULT_PROMPT_VERSION.to_dict()]
        return results

    def save_prompt_version(self, prompt_dict: dict[str, Any], updated_by: str, change_note: str) -> dict[str, Any]:
        with self._connection() as conn:
            max_row = conn.execute("SELECT MAX(version) FROM agent_prompt_versions").fetchone()
            new_ver = (max_row[0] or 0) + 1 if max_row else 1
            prompt_dict["version"] = new_ver
            prompt_dict["updated_at"] = self.utc_now_iso()
            prompt_dict["updated_by"] = updated_by
            prompt_dict["change_note"] = change_note

            conn.execute(
                """
                INSERT INTO agent_prompt_versions (version, updated_at, updated_by, change_note, prompt_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_ver, prompt_dict["updated_at"], updated_by, change_note, json.dumps(prompt_dict)),
            )
        return prompt_dict

    def is_trivia_presented(self, user_id: str, fact_id: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM trivia_presentation_history WHERE user_id = ? AND fact_id = ?",
                (user_id, fact_id),
            ).fetchone()
        return bool(row)

    def record_trivia_presentation(self, user_id: str, fact_id: str) -> None:
        now = self.utc_now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO trivia_presentation_history (user_id, fact_id, presented_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, fact_id) DO UPDATE SET presented_at = excluded.presented_at
                """,
                (user_id, fact_id, now),
            )

    def get_news_presentation(self, user_id: str, story_cluster_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM news_presentation_history WHERE user_id = ? AND story_cluster_id = ?",
                (user_id, story_cluster_id),
            ).fetchone()
        return dict(row) if row else None

    def record_news_presentation(self, user_id: str, story_cluster_id: str, content_fingerprint: str) -> None:
        now = self.utc_now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO news_presentation_history (user_id, story_cluster_id, content_fingerprint, presented_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, story_cluster_id) DO UPDATE SET
                    content_fingerprint = excluded.content_fingerprint,
                    presented_at = excluded.presented_at
                """,
                (user_id, story_cluster_id, content_fingerprint, now),
            )

    def list_verified_trivia(self, title: str | None = None, tmdb_id: int | None = None) -> list[dict[str, Any]]:
        with self._connection() as conn:
            if tmdb_id:
                rows = conn.execute("SELECT * FROM trivia_facts WHERE tmdb_id = ?", (tmdb_id,)).fetchall()
            elif title:
                rows = conn.execute("SELECT * FROM trivia_facts WHERE LOWER(title) LIKE ?", (f"%{title.lower()}%",)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM trivia_facts LIMIT 50").fetchall()
        return [dict(r) for r in rows]

    def add_verified_trivia(self, fact_dict: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        fact_id = fact_dict.get("fact_id") or f"trivia:{fact_dict.get('tmdb_id', 'gen')}:{hash(fact_dict.get('fact_text'))}"
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO trivia_facts (fact_id, title, tmdb_id, media_type, fact_text, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fact_id) DO UPDATE SET fact_text = excluded.fact_text
                """,
                (
                    fact_id,
                    fact_dict["title"],
                    fact_dict.get("tmdb_id"),
                    fact_dict.get("media_type", "movie"),
                    fact_dict["fact_text"],
                    fact_dict.get("source", "verified_archive"),
                    now,
                ),
            )
        fact_dict["fact_id"] = fact_id
        return fact_dict

    def list_major_news(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM entertainment_news WHERE is_major = 1 ORDER BY published_at DESC LIMIT 20").fetchall()
        return [dict(r) for r in rows]

    def add_major_news(self, news_dict: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        story_id = news_dict.get("story_id") or f"news:{news_dict.get('story_cluster_id', 'c')}:{hash(news_dict.get('title'))}"
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO entertainment_news (
                    story_id, story_cluster_id, title, summary, source,
                    news_category, is_major, is_rumor, published_at, content_fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(story_id) DO UPDATE SET
                    summary = excluded.summary,
                    content_fingerprint = excluded.content_fingerprint
                """,
                (
                    story_id,
                    news_dict["story_cluster_id"],
                    news_dict["title"],
                    news_dict["summary"],
                    news_dict.get("source", "verified_media"),
                    news_dict.get("news_category", "official_announcement"),
                    1 if news_dict.get("is_major", True) else 0,
                    1 if news_dict.get("is_rumor", False) else 0,
                    news_dict.get("published_at", now),
                    news_dict.get("content_fingerprint", news_dict["title"]),
                ),
            )
        news_dict["story_id"] = story_id
        return news_dict



