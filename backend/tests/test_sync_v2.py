"""Protocol-v2 HTTP contract; run separately from auth-reloading test suites."""

from copy import deepcopy

import pytest

from app.auth import CurrentUser, get_current_user


@pytest.fixture
def sync_client(client):
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        uid="sync-v2", email="sync-v2@example.com",
    )
    app.state.watchlist_repo.clear_all("sync-v2")
    for item in app.state.watchlist_repo.list_rated_movies("sync-v2"):
        app.state.watchlist_repo.delete_rated_movie("sync-v2", item["media_type"], item["tmdb_id"])
    with app.state.watchlist_repo._connection() as conn:
        conn.execute("DELETE FROM sync_receipts WHERE user_id = ?", ("sync-v2",))
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def operation(op_id="create", base="absent", kind="upsert", **payload):
    return {
        "operationId": op_id, "entityId": "movie_123", "operationType": kind,
        "baseRevision": base,
        "payload": {"tmdbId": 123, "mediaType": "movie", "title": "Example", **payload},
    }


def push(client, *operations, **kwargs):
    return client.post(
        "/api/sync/movies/push",
        json={"protocolVersion": 2, "operations": list(operations)}, **kwargs,
    )


def pull(client):
    return client.get("/api/sync/movies/pull?protocolVersion=2").json()


def test_two_device_conflict_and_canonical_options(sync_client):
    initial = push(sync_client, operation(
        isOwned=True, ownedFormat="hard_copy", watchFreeStreaming=True,
        watchOnSaleBuy=True, rating=4,
    )).json()
    base = initial["applied_operations"][0]["revision"]
    record = pull(sync_client)["records"][0]
    assert record == {
        "id": "movie_123", "tmdbId": 123, "mediaType": "movie", "title": "Example",
        "posterPath": None, "releaseDate": None, "status": "queue", "isOwned": True,
        "ownedFormat": "hard_copy", "watchFreeStreaming": True, "watchOnSaleBuy": True,
        "rating": 4, "revision": base, "deletedAt": None,
    }
    first = push(sync_client, operation("device-a", base, rating=5, status="following")).json()
    second = push(sync_client, operation("device-b", base, rating=1)).json()
    assert first["processed_operations"] == ["device-a"]
    assert second["processed_operations"] == []
    assert second["failed_operations"] == []
    assert second["conflicts"] == [{
        "operationId": "device-b", "entityId": "movie_123", "remote": pull(sync_client)["records"][0],
    }]


def test_delete_retry_after_recreation_preserves_newer_write(sync_client):
    base = push(sync_client, operation(rating=4)).json()["applied_operations"][0]["revision"]
    deletion = operation("delete", base, "delete")
    deleted = push(sync_client, deletion).json()
    assert deleted["applied_operations"] == [{"operationId": "delete", "revision": "absent"}]
    snapshot = pull(sync_client)
    assert snapshot["records"] == []
    assert snapshot["full_snapshot"] is True
    assert isinstance(snapshot["next_cursor"], str)
    recreated = push(sync_client, operation("recreate", rating=2)).json()
    assert push(sync_client, deletion).json()["applied_operations"] == deleted["applied_operations"]
    assert pull(sync_client)["records"][0]["rating"] == 2
    assert pull(sync_client)["records"][0]["revision"] == recreated["applied_operations"][0]["revision"]


def test_snapshot_rated_only_and_legacy_removal(sync_client):
    from app.main import app

    repo = app.state.watchlist_repo
    repo.rate_movie("sync-v2", "tv", 123, "Rated only", None, None, 3)
    record = pull(sync_client)["records"][0]
    assert record["id"] == "tv_123"
    assert record["status"] == "watched"
    assert record["rating"] == 3
    assert repo.list_items("sync-v2") == []
    repo.delete_rated_movie("sync-v2", "tv", 123)
    assert pull(sync_client)["records"] == []


@pytest.mark.parametrize("base", ["absent", "legacy-revision", "123456"])
def test_unknown_revision_never_overwrites_server(sync_client, base):
    push(sync_client, operation(rating=4))
    result = push(sync_client, operation("stale", base, rating=1)).json()
    assert len(result["conflicts"]) == 1
    assert pull(sync_client)["records"][0]["rating"] == 4


def test_receipt_reuse_rejected_and_rating_clear(sync_client):
    original = operation(rating=5)
    result = push(sync_client, original).json()
    base = result["applied_operations"][0]["revision"]
    clear = push(sync_client, operation("clear", base, rating=None, isOwned=False)).json()
    assert clear["processed_operations"] == ["clear"]
    from app.main import app
    assert app.state.watchlist_repo.list_rated_movies("sync-v2") == []
    assert pull(sync_client)["records"][0]["rating"] is None
    retry = push(sync_client, original).json()
    assert retry["applied_operations"] == result["applied_operations"]
    changed = deepcopy(original)
    changed["payload"]["rating"] = 1
    rejected = push(sync_client, changed).json()
    assert rejected["processed_operations"] == []
    assert "different content" in rejected["failed_operations"][0]["reason"]
    assert pull(sync_client)["records"][0]["rating"] is None


@pytest.mark.parametrize("changes", [
    {"tmdbId": "123"}, {"tmdbId": True}, {"tmdbId": -1}, {"mediaType": "person"},
    {"rating": 6}, {"rating": 2.5}, {"rating": True}, {"isOwned": "false"},
    {"status": "invalid"}, {"ownedFormat": "invalid"}, {"deletedAt": "yesterday"},
])
def test_invalid_batch_rejected_before_any_write(sync_client, changes):
    valid = operation()
    invalid = operation("invalid", **changes)
    response = push(sync_client, valid, invalid)
    assert response.status_code == 422
    assert pull(sync_client)["records"] == []


@pytest.mark.parametrize("changes", [
    {"baseRevision": None}, {"baseRevision": ""}, {"operationId": ""},
    {"entityId": "tv_123"}, {"operationType": "patch"},
])
def test_invalid_envelope_rejected_before_any_write(sync_client, changes):
    invalid = operation("invalid")
    invalid.update(changes)
    assert push(sync_client, operation(), invalid).status_code == 422
    assert pull(sync_client)["records"] == []


def test_foreign_owner_batch_and_header_rejected_before_writes(sync_client):
    assert push(sync_client, operation(), operation("foreign", ownerId="other")).status_code == 409
    assert push(sync_client, operation(), headers={"X-Sync-Owner": "other"}).status_code == 409
    assert sync_client.get(
        "/api/sync/movies/pull?protocolVersion=2", headers={"X-Sync-Owner": "other"},
    ).status_code == 409
    assert pull(sync_client)["records"] == []


def test_duplicate_batch_id_with_different_content_rejected(sync_client):
    assert push(sync_client, operation(), operation(rating=1)).status_code == 422
    assert pull(sync_client)["records"] == []


def test_identical_duplicate_batch_ids_rejected_before_any_write(sync_client):
    response = push(sync_client, operation(), operation())
    assert response.status_code == 422
    assert response.json()["detail"] == "Duplicate operationId in the same batch: create"
    assert pull(sync_client)["records"] == []


def test_retry_cannot_rebase_an_already_applied_operation(sync_client):
    original = operation(rating=3)
    applied = push(sync_client, original).json()["applied_operations"][0]
    changed = deepcopy(original)
    changed["baseRevision"] = applied["revision"]
    result = push(sync_client, changed).json()
    assert result["processed_operations"] == result["applied_operations"] == result["conflicts"] == []
    assert "different content" in result["failed_operations"][0]["reason"]
    assert push(sync_client, original).json()["applied_operations"] == [applied]


@pytest.mark.parametrize("invalid", [
    None, {}, {"operationId": "missing"}, {"operationId": 123},
])
def test_malformed_operation_envelope_is_explicit_and_atomic(sync_client, invalid):
    response = push(sync_client, operation(), invalid)
    assert response.status_code == 422
    assert response.json()["detail"]
    assert pull(sync_client)["records"] == []
