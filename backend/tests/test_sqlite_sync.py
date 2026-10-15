"""SQLite protocol-v2 transaction and persistence guarantees."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from threading import Barrier
from unittest.mock import patch

import pytest

from app.sqlite_repo import SqliteWatchlistRepository
from app.sync_protocol import sync_record


@pytest.fixture
def repo(tmp_path):
    with patch("app.sqlite_repo.DB_PATH", tmp_path / "sync.db"):
        yield SqliteWatchlistRepository()


def op(operation_id, base="absent", kind="upsert", **payload):
    return {
        "operationId": operation_id, "entityId": "movie_123", "operationType": kind,
        "baseRevision": base, "payload": {"tmdbId": 123, "title": "Example", **payload},
    }


def test_atomic_competing_edits(repo):
    base = repo.apply_sync_operation("u", op("create", rating=3))["applied"]["revision"]
    barrier = Barrier(2)

    def write(index):
        barrier.wait(timeout=5)
        return repo.apply_sync_operation("u", op(f"device-{index}", base, rating=index))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [1, 2]))
    assert sum("applied" in result for result in results) == 1
    assert sum("conflict" in result for result in results) == 1
    assert repo.list_items("u")[0]["user_rating"] == repo.list_rated_movies("u")[0]["rating"]


def test_receipts_durable_user_scoped_and_delete_removes_both(repo):
    create = op("same/id", rating=4)
    result = repo.apply_sync_operation("u", create)
    base = result["applied"]["revision"]
    deletion = op("delete", base, "delete")
    receipt = repo.apply_sync_operation("u", deletion)
    assert repo.list_items("u") == repo.list_rated_movies("u") == repo.sync_snapshot("u") == []
    repo.apply_sync_operation("u", op("later", rating=2))
    reopened = SqliteWatchlistRepository()
    assert reopened.apply_sync_operation("u", deletion) == receipt
    assert reopened.apply_sync_operation("u", create) == result
    assert reopened.sync_snapshot("u")[0]["rating"] == 2
    assert "applied" in reopened.apply_sync_operation("other", create)
    with pytest.raises(ValueError, match="different content"):
        reopened.apply_sync_operation("u", op("same/id", rating=1))


def test_revision_ignores_cache_and_tracks_every_authoritative_field(repo):
    repo.add_item("u", "movie", 123, "Example", None, None)
    base = repo.sync_snapshot("u")[0]["revision"]
    repo.update_item_cache("u", "movie", 123, {"title": "Metadata refresh", "vote_average": 7})
    assert repo.sync_snapshot("u")[0]["revision"] == base
    watch = repo.list_items("u")[0]
    for field, value in {
        "status": "following", "is_owned": True, "watch_free_streaming": True,
        "watch_on_sale_buy": True, "target_rental_price": 2.99, "user_rating": 3,
    }.items():
        assert sync_record("movie", 123, {**watch, field: value}, None)["revision"] != base
    owned = {**watch, "is_owned": True}
    assert sync_record("movie", 123, owned, None)["revision"] != sync_record(
        "movie", 123, {**owned, "owned_format": "hard_copy"}, None,
    )["revision"]
    rated = {"rating": 3}
    assert sync_record("movie", 123, watch, rated)["revision"] != base
    assert sync_record("movie", 123, watch, rated)["revision"] != sync_record("movie", 123, None, rated)["revision"]


def test_rating_constraint_failure_rolls_back_watchlist_and_receipt(repo):
    with repo._connection() as conn:
        conn.execute("""
            CREATE TRIGGER reject_rating BEFORE INSERT ON rated_movies
            BEGIN SELECT RAISE(ABORT, 'simulated rating failure'); END
        """)
    with pytest.raises(Exception, match="simulated rating failure"):
        repo.apply_sync_operation("u", op("create", rating=3))
    assert repo.sync_snapshot("u") == []
    with repo._connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM sync_receipts").fetchone()[0] == 0
        conn.execute("DROP TRIGGER reject_rating")
    assert "applied" in repo.apply_sync_operation("u", op("create", rating=3))


def test_conflict_receipt_replays_original_snapshot(repo):
    repo.apply_sync_operation("u", op("create", rating=3))
    conflicting = op("stale", rating=1)
    conflict = repo.apply_sync_operation("u", conflicting)
    base = repo.sync_snapshot("u")[0]["revision"]
    repo.apply_sync_operation("u", op("later", base, rating=5))
    assert repo.apply_sync_operation("u", conflicting) == conflict


def test_missing_remote_conflict_returns_canonical_tombstone(repo):
    result = repo.apply_sync_operation("u", op("missing", "unknown"))
    remote = result["conflict"]["remote"]
    assert remote["revision"] == "absent"
    assert remote["deletedAt"] is not None
    datetime.fromisoformat(remote["deletedAt"])
    assert remote == {
        "id": "movie_123", "tmdbId": 123, "mediaType": "movie", "title": "Untitled",
        "posterPath": None, "releaseDate": None, "status": "watched", "isOwned": False,
        "ownedFormat": None, "watchFreeStreaming": False, "watchOnSaleBuy": False,
        "rating": None, "revision": "absent", "deletedAt": remote["deletedAt"],
    }
    assert repo.sync_snapshot("u") == []


def test_retries_ignore_mutable_transport_fields(repo):
    operation = op("write", rating=3)
    operation.update(attemptCount=0, status="pending", nextAttemptAt=100)
    result = repo.apply_sync_operation("u", operation)
    operation.update(attemptCount=5, status="retry", nextAttemptAt=200)
    assert repo.apply_sync_operation("u", operation) == result


def test_full_snapshot_never_loses_entity_moved_between_tables(repo):
    repo.rate_movie("u", "movie", 123, "Example", None, None, 3)
    with repo._connection() as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    before = repo.sync_snapshot("u")
    connection = repo._connection

    def move_to_watchlist():
        with connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM rated_movies WHERE user_id = ?", ("u",))
            conn.execute("""
                INSERT INTO watchlist (user_id, media_type, tmdb_id, title, added_at)
                VALUES ('u', 'movie', 123, 'Example', 'now')
            """)

    with ThreadPoolExecutor(max_workers=1) as pool:
        class Cursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchall(self):
                rows = self.cursor.fetchall()
                # Commit a write between the two snapshot queries. In WAL mode
                # a read transaction must keep its original rated-only entity.
                pool.submit(move_to_watchlist).result(timeout=5)
                return rows

        class Connection:
            def __init__(self, conn):
                self.conn = conn

            def execute(self, sql, *args):
                cursor = self.conn.execute(sql, *args)
                if sql == "SELECT * FROM watchlist WHERE user_id = ?":
                    return Cursor(cursor)
                return cursor

        @contextmanager
        def intercepted_connection():
            with connection() as conn:
                yield Connection(conn)

        with patch.object(repo, "_connection", intercepted_connection):
            assert repo.sync_snapshot("u") == before
    after = repo.sync_snapshot("u")
    assert after[0]["id"] == before[0]["id"]
    assert after[0]["rating"] is None
    assert after[0]["revision"] != before[0]["revision"]


def test_rebased_retry_is_rejected_without_new_write(repo):
    operation = op("create", rating=3)
    original = repo.apply_sync_operation("u", operation)
    operation["baseRevision"] = original["applied"]["revision"]
    with pytest.raises(ValueError, match="different content"):
        repo.apply_sync_operation("u", operation)
    assert repo.sync_snapshot("u")[0]["revision"] == original["applied"]["revision"]
