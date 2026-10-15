"""Firestore sync transaction API tests (not an emulator substitute)."""

from copy import deepcopy
from functools import wraps
from unittest.mock import patch

import pytest

from app.firestore_repo import FirestoreWatchlistRepository


class Snapshot:
    def __init__(self, value):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return deepcopy(self.value)


class Reference:
    def __init__(self, db, path=()):
        self.db, self.path = db, path

    def collection(self, name):
        return Reference(self.db, (*self.path, name))

    def document(self, name):
        return Reference(self.db, (*self.path, name))

    def get(self, *, transaction):
        transaction.read()
        return Snapshot(transaction.snapshot.get(self.path))

    def stream(self, *, transaction):
        transaction.read()
        result = [
            Snapshot(value) for key, value in transaction.snapshot.items()
            if key[:-1] == self.path
        ]
        if self.db.after_stream:
            self.db.after_stream(self.path, transaction)
        return result


class Transaction:
    def __init__(self, db):
        self.db = db
        self.writes = []
        self.snapshot = None

    def read(self):
        assert not self.writes, "Firestore forbids reads after writes"
        if self.snapshot is None:
            self.snapshot = deepcopy(self.db.documents)

    def set(self, ref, data, merge=False):
        self.writes.append(("set", ref.path, deepcopy(data), merge))

    def delete(self, ref):
        self.writes.append(("delete", ref.path, None, False))

    def commit(self):
        updated = deepcopy(self.db.documents)
        for kind, path, data, merge in self.writes:
            if kind == "delete":
                updated.pop(path, None)
            else:
                updated[path] = {**updated.get(path, {}), **data} if merge else data
        self.db.documents = updated
        self.db.commits.append(self.writes)


class Database:
    def __init__(self):
        self.documents = {}
        self.commits = []
        self.after_stream = None

    def collection(self, name):
        return Reference(self, (name,))

    def transaction(self):
        return Transaction(self)


def transactional(callback):
    @wraps(callback)
    def run(transaction):
        result = callback(transaction)
        transaction.commit()
        return result
    return run


@pytest.fixture
def repo():
    db = Database()
    with patch("app.firestore_repo.firestore.Client", return_value=db), patch(
        "app.firestore_repo.firestore.transactional", side_effect=transactional,
    ):
        yield FirestoreWatchlistRepository(project="sync-test")


def op(operation_id, base="absent", kind="upsert", **payload):
    return {
        "operationId": operation_id, "entityId": "movie_123", "operationType": kind,
        "baseRevision": base,
        "payload": {"tmdbId": 123, "title": "Example", **payload},
    }


def test_firestore_atomic_options_rating_and_conflict(repo):
    result = repo.apply_sync_operation("u", op(
        "device-a", isOwned=True, ownedFormat="cloud", rating=5,
        watchFreeStreaming=True, watchOnSaleBuy=True,
    ))
    assert len(repo._db.commits[-1]) == 3
    base = result["applied"]["revision"]
    record = repo.sync_snapshot("u")[0]
    assert record["revision"] == base
    assert record["rating"] == 5
    assert record["isOwned"] and record["watchFreeStreaming"] and record["watchOnSaleBuy"]
    assert record["ownedFormat"] == "cloud"
    conflict = repo.apply_sync_operation("u", op("device-b", rating=1))
    assert conflict["conflict"]["remote"] == record
    assert len(repo._db.commits[-1]) == 1  # receipt only; no watchlist/rating mutation
    clear = repo.apply_sync_operation("u", op("clear", base, rating=None))
    assert clear["applied"]["revision"] == repo.sync_snapshot("u")[0]["revision"]
    assert ("users", "u", "rated_movies", "movie_123") not in repo._db.documents
    assert repo.sync_snapshot("u")[0]["rating"] is None


def test_firestore_delete_retry_and_hashed_receipts(repo):
    create = op("op/with/slashes", rating=4)
    created = repo.apply_sync_operation("u", create)
    deletion = op("delete", created["applied"]["revision"], "delete")
    receipt = repo.apply_sync_operation("u", deletion)
    assert repo.sync_snapshot("u") == []
    assert len(repo._db.commits[-2]) == 3
    repo.apply_sync_operation("u", op("later", rating=1))
    assert repo.apply_sync_operation("u", deletion) == receipt
    assert repo.apply_sync_operation("u", create) == created
    assert repo.sync_snapshot("u")[0]["rating"] == 1
    assert "applied" in repo.apply_sync_operation("other", create)
    receipt_paths = [key for key in repo._db.documents if key[-2] == "sync_receipts"]
    assert all(len(key[-1]) == 64 and "/" not in key[-1] for key in receipt_paths)
    with pytest.raises(ValueError, match="different content"):
        repo.apply_sync_operation("u", op("op/with/slashes", rating=2))
    assert repo.sync_snapshot("u")[0]["rating"] == 1


def test_firestore_rated_only_and_cache_fingerprint(repo):
    rated_path = ("users", "u", "rated_movies", "movie_123")
    repo._db.documents[rated_path] = {
        "media_type": "movie", "tmdb_id": 123, "title": "Example", "rating": 3,
    }
    record = repo.sync_snapshot("u")[0]
    assert record["status"] == "watched"
    assert len(repo._db.documents) == 1
    assert "conflict" in repo.apply_sync_operation("u", op("unknown"))
    assert "applied" in repo.apply_sync_operation("u", op("edit", record["revision"], rating=3))
    watch_path = ("users", "u", "watchlist", "movie_123")
    before = repo.sync_snapshot("u")[0]["revision"]
    repo._db.documents[watch_path].update(details_cached={"vote": 10}, last_updated="tomorrow")
    assert repo.sync_snapshot("u")[0]["revision"] == before
    del repo._db.documents[watch_path]
    assert repo.sync_snapshot("u")[0]["revision"] != before
    del repo._db.documents[rated_path]
    assert repo.sync_snapshot("u") == []


def test_firestore_receipt_failure_does_not_commit_partial_write(repo):
    original_set = Transaction.set

    def fail_receipt(transaction, ref, data, merge=False):
        if ref.path[-2] == "sync_receipts":
            raise RuntimeError("Receipt storage unavailable")
        original_set(transaction, ref, data, merge)

    with patch.object(Transaction, "set", fail_receipt):
        with pytest.raises(RuntimeError, match="Receipt storage unavailable"):
            repo.apply_sync_operation("u", op("write", rating=3))
    assert repo._db.documents == {}
    assert "applied" in repo.apply_sync_operation("u", op("write", rating=3))


def test_firestore_retries_ignore_mutable_transport_fields(repo):
    operation = op("write", rating=3)
    operation.update(attemptCount=0, status="pending", nextAttemptAt=100)
    original = repo.apply_sync_operation("u", operation)
    operation.update(attemptCount=5, status="retry", nextAttemptAt=200)
    assert repo.apply_sync_operation("u", operation) == original


def test_firestore_invalid_identity_and_owner_before_transaction(repo):
    operation = op("invalid")
    operation["entityId"] = "tv_123"
    with pytest.raises(ValueError, match="entityId"):
        repo.apply_sync_operation("u", operation)
    with pytest.raises(ValueError, match="owner"):
        repo.apply_sync_operation("u", op("foreign", ownerId="other"))
    assert repo._db.commits == []


def test_firestore_full_snapshot_uses_same_transaction_for_both_collections(repo):
    rated_path = ("users", "u", "rated_movies", "movie_123")
    watch_path = ("users", "u", "watchlist", "movie_123")
    repo._db.documents[rated_path] = {
        "media_type": "movie", "tmdb_id": 123, "title": "Example", "rating": 3,
    }
    before = repo.sync_snapshot("u")
    reads = []

    def move_between_queries(path, transaction):
        reads.append((path, transaction))
        if path[-1] == "watchlist":
            del repo._db.documents[rated_path]
            repo._db.documents[watch_path] = {
                "media_type": "movie", "tmdb_id": 123, "title": "Example",
            }

    repo._db.after_stream = move_between_queries
    assert repo.sync_snapshot("u") == before
    assert [path[-1] for path, _ in reads] == ["watchlist", "rated_movies"]
    assert reads[0][1] is reads[1][1]
    repo._db.after_stream = None
    assert repo.sync_snapshot("u")[0]["rating"] is None


def test_firestore_rebased_retry_is_rejected_without_writes(repo):
    operation = op("create", rating=3)
    original = repo.apply_sync_operation("u", operation)
    commits = len(repo._db.commits)
    operation["baseRevision"] = original["applied"]["revision"]
    with pytest.raises(ValueError, match="different content"):
        repo.apply_sync_operation("u", operation)
    assert len(repo._db.commits) == commits
    assert repo.sync_snapshot("u")[0]["revision"] == original["applied"]["revision"]
