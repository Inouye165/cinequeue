import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DATA_DIR, DB_PATH


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
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
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
