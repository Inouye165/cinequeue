import pytest
from app.auth import get_current_user, CurrentUser

def test_sync_push_unauthenticated(client_with_auth):
    # Unauthenticated request without session cookie
    res = client_with_auth.post("/api/sync/movies/push", json={"operations": []})
    assert res.status_code == 401

def test_sync_push_and_pull_authenticated(client_with_auth):
    from app.main import app
    mock_user = CurrentUser(uid="user_sync_test", email="sync@example.com", display_name="Sync User")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        op_payload = {
            "operations": [
                {
                    "operationId": "op_test_1",
                    "entityType": "movie",
                    "entityId": "movie_550",
                    "operationType": "upsert",
                    "payload": {
                        "tmdbId": 550,
                        "mediaType": "movie",
                        "title": "Fight Club",
                        "status": "queue",
                        "rating": 5,
                        "posterPath": "/poster.jpg"
                    }
                }
            ]
        }

        push_res = client_with_auth.post("/api/sync/movies/push", json=op_payload)
        assert push_res.status_code == 200
        data = push_res.json()
        assert data["status"] == "ok"
        assert "op_test_1" in data["processed_operations"]

        # Pull changes
        pull_res = client_with_auth.get("/api/sync/movies/pull")
        assert pull_res.status_code == 200
        pull_data = pull_res.json()
        assert len(pull_data["watchlist"]) >= 1
        assert any(item["tmdb_id"] == 550 for item in pull_data["watchlist"])
        assert len(pull_data["ratings"]) >= 1
        assert any(item["tmdb_id"] == 550 and item["rating"] == 5 for item in pull_data["ratings"])
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.parametrize("method,path", [
    ("post", "/api/sync/movies/push"),
    ("get", "/api/sync/movies/pull"),
])
def test_sync_rejects_session_owner_mismatch(client_with_auth, method, path):
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(uid="B", email="b@example.com")
    try:
        kwargs = {"headers": {"X-Sync-Owner": "A"}}
        if method == "post":
            kwargs["json"] = {"operations": []}
        response = getattr(client_with_auth, method)(path, **kwargs)
        assert response.status_code == 409
    finally:
        app.dependency_overrides.pop(get_current_user, None)

def test_sync_rejects_foreign_operation_before_any_write(client_with_auth):
    from app.main import app
    from unittest.mock import patch
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(uid="B", email="b@example.com")
    try:
        with patch.object(app.state.watchlist_repo, "add_item") as add_item:
            response = client_with_auth.post("/api/sync/movies/push", json={
                "operations": [{
                    "operationId": "foreign", "entityId": "movie_1", "operationType": "upsert",
                    "payload": {"ownerId": "A", "tmdbId": 1, "title": "Private A"},
                }]
            })
            assert response.status_code == 409
            add_item.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user, None)

def test_sync_preserves_local_options_and_rating_clear(client_with_auth):
    from app.main import app
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(uid="options", email="options@example.com")
    try:
        operation = {
            "operationId": "options-1", "entityId": "movie_999", "operationType": "upsert",
            "payload": {
                "ownerId": "options", "tmdbId": 999, "title": "Options",
                "isOwned": True, "ownedFormat": "hard_copy",
                "watchFreeStreaming": True, "watchOnSaleBuy": True, "rating": 4,
            },
        }
        assert client_with_auth.post("/api/sync/movies/push", json={"operations": [operation]}).status_code == 200
        data = client_with_auth.get("/api/sync/movies/pull").json()
        item = next(item for item in data["watchlist"] if item["tmdb_id"] == 999)
        assert item["owned_format"] == "hard_copy"
        assert item["watch_free_streaming"]
        assert item["watch_on_sale_buy"]
        operation["operationId"] = "options-2"
        operation["payload"]["rating"] = 0
        result = client_with_auth.post("/api/sync/movies/push", json={"operations": [operation]}).json()
        assert result["processed_operations"] == ["options-2"]
        assert client_with_auth.get("/api/sync/movies/pull").json()["ratings"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)

def test_sync_push_delete_tombstone(client_with_auth):
    from app.main import app
    mock_user = CurrentUser(uid="user_sync_test", email="sync@example.com", display_name="Sync User")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        op_payload = {
            "operations": [
                {
                    "operationId": "op_test_del",
                    "entityType": "movie",
                    "entityId": "movie_550",
                    "operationType": "delete",
                    "payload": {
                        "tmdbId": 550,
                        "mediaType": "movie",
                        "deletedAt": "2026-07-29T12:00:00Z"
                    }
                }
            ]
        }

        push_res = client_with_auth.post("/api/sync/movies/push", json=op_payload)
        assert push_res.status_code == 200
        assert "op_test_del" in push_res.json()["processed_operations"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
