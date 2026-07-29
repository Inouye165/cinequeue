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
