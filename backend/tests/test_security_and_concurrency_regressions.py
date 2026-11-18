"""Regression tests for security hardening, secret scrubbing, concurrency, and dual-store sync."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.decision_models import (
    DecisionConfig,
    PromptVersion,
    build_stable_daily_cache_key,
    get_current_run_context,
    scrub_secrets,
)
from app.services.agent_service import AiAgentService
from app.services.briefing_service import BriefingService
from app.sqlite_repo import SqliteWatchlistRepository


def _login_cookie_user(client_with_auth, uid: str = "sec_user_1", email: str = "inouye165@gmail.com") -> str:
    csrf_resp = client_with_auth.get("/api/auth/csrf")
    assert csrf_resp.status_code == 200
    csrf_token = csrf_resp.json()["csrf_token"]
    now = int(time.time())
    with patch("firebase_admin.auth.verify_id_token", return_value={
        "uid": uid,
        "email": email,
        "email_verified": True,
        "auth_time": now,
    }), patch("firebase_admin.auth.create_session_cookie", return_value="mock_sec_session"):
        res = client_with_auth.post(
            "/api/auth/session",
            json={"id_token": "valid_tok", "csrf_token": csrf_token},
            headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"},
        )
        assert res.status_code == 200
    return csrf_token


def test_mutating_user_routers_enforce_cookie_csrf_and_origin(client_with_auth):
    csrf_token = _login_cookie_user(client_with_auth)
    valid_origin = "https://cinequeue-7tvty3vmvq-uw.a.run.app"
    claims = {"uid": "sec_user_1", "email": "inouye165@gmail.com", "email_verified": True}

    mutations = [
        ("/api/watchlist", {"media_type": "movie", "tmdb_id": 550, "title": "Fight Club", "status": "queue"}),
        ("/api/ratings", {"media_type": "movie", "tmdb_id": 550, "title": "Fight Club", "rating": 5}),
        ("/api/sync/movies/push", {"protocolVersion": 2, "operations": []}),
        ("/api/agent/chat", {"message": "Hello there"}),
    ]

    with patch("firebase_admin.auth.verify_session_cookie", return_value=claims), \
         patch("app.services.agent_service.ENABLE_AI_CALLS", False):
        for path, body in mutations:
            no_csrf = client_with_auth.post(path, json=body, headers={"Origin": valid_origin})
            assert no_csrf.status_code == 401, f"Expected 401 without X-CSRF-Token on {path}"

            bad_origin = client_with_auth.post(
                path,
                json=body,
                headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf_token},
            )
            assert bad_origin.status_code == 401, f"Expected 401 with untrusted Origin on {path}"

            valid = client_with_auth.post(
                path,
                json=body,
                headers={"Origin": valid_origin, "X-CSRF-Token": csrf_token},
            )
            assert valid.status_code == 200, f"Expected 200 on {path}, got {valid.status_code}: {valid.text}"


def test_auth_proxy_hardening_and_clickjacking_headers(client_with_auth):
    # Security headers prevent framing/clickjacking
    health = client_with_auth.get("/api/health")
    assert health.status_code == 200
    assert health.headers.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in (health.headers.get("content-security-policy") or "")

    # Disallowed / traversal proxy paths are blocked
    assert client_with_auth.get("/__/auth/evil").status_code == 400
    assert client_with_auth.get("/__/auth/handler%2f..%2fadmin").status_code == 400

    # Oversized proxy bodies are rejected with 413
    oversized = b"a" * (64 * 1024 + 1)
    too_big = client_with_auth.post("/__/auth/handler", content=oversized)
    assert too_big.status_code == 413

    # CineQueue session/admin cookies are stripped while Firebase helper cookies pass through
    upstream_resp = MagicMock(status_code=200, content=b"ok")
    upstream_resp.headers = {"content-type": "text/plain"}
    mock_http = AsyncMock()
    mock_http.request = AsyncMock(return_value=upstream_resp)
    client_with_auth.app.state.http_client = mock_http

    proxied = client_with_auth.get(
        "/__/auth/handler",
        headers={
            "Cookie": (
                "cinequeue_admin_session=secret_admin_tok; "
                "__Host-cinequeue_admin_session=secret_host_admin_tok; "
                "cinequeue_session=user_session_tok; "
                "firebase_oauth_state=ok123"
            )
        },
    )
    assert proxied.status_code == 200
    forwarded_headers = mock_http.request.await_args.kwargs["headers"]
    forwarded_cookie = forwarded_headers.get("cookie", "")
    assert "cinequeue_admin_session" not in forwarded_cookie
    assert "__Host-cinequeue_admin_session" not in forwarded_cookie
    assert "cinequeue_session" not in forwarded_cookie
    assert "firebase_oauth_state=ok123" in forwarded_cookie


def test_scrub_secrets_preserves_telemetry_keys_and_redacts_secrets():
    payload = {
        "daily_cache_key": "2026-10-21:America/Los_Angeles",
        "item_key": "movie_550",
        "prompt_token_count": 120,
        "candidate_token_count": 45,
        "total_token_count": 165,
        "api_key": "raw_secret_api_key",
        "token": "secret_session_token",
        "url": "https://api.themoviedb.org/3/movie/550?api_key=TMDB_SECRET_KEY&language=en",
        "nested": {"authorization": "Bearer eyJabc.def.ghi"},
    }
    scrubbed = scrub_secrets(payload)
    assert scrubbed["daily_cache_key"] == "2026-10-21:America/Los_Angeles"
    assert scrubbed["item_key"] == "movie_550"
    assert scrubbed["prompt_token_count"] == 120
    assert scrubbed["candidate_token_count"] == 45
    assert scrubbed["total_token_count"] == 165
    assert scrubbed["api_key"] == "[REDACTED]"
    assert scrubbed["token"] == "[REDACTED]"
    assert "TMDB_SECRET_KEY" not in scrubbed["url"]
    assert "eyJabc.def.ghi" not in scrubbed["nested"]["authorization"]


def test_dataclass_from_dict_ignores_unknown_keys():
    cfg = DecisionConfig.from_dict({"minimum_interest_score": 0.61, "obsolete_key": "ignore_me"})
    assert cfg.minimum_interest_score == 0.61

    prompt = PromptVersion.from_dict({"wording_instruction": "Concise", "unknown_col": 99})
    assert prompt.wording_instruction == "Concise"


@pytest.mark.asyncio
async def test_agent_process_chat_persists_user_msg_pronoun_guard_and_status_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", tmp_path / "agent_reg.db")
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    monkeypatch.setattr("app.services.agent_service.ENABLE_AI_CALLS", False)
    repo = SqliteWatchlistRepository()
    uid = "mod01_user"

    repo.add_chat_message(uid, "assistant", "Earlier we talked about The Matrix.")

    # Casual question with "it" must NOT trigger auto-adding "The Matrix"
    res = await AiAgentService.process_chat(uid, "Wait, what is it about?", repo, None)
    assert res["actions_taken"] == []
    assert repo.list_items(uid) == []

    history = repo.list_chat_messages(uid, limit=10)
    assert [m["role"] for m in history[-2:]] == ["user", "assistant"]
    assert history[-2]["content"] == "Wait, what is it about?"

    # Status updates map "watching" -> "following" and "dropped" -> removal
    repo.add_item(uid, "movie", 603, "The Matrix", None, "1999-03-31", status="queue")
    await AiAgentService.process_chat(uid, "mark The Matrix as watching", repo, None)
    items = repo.list_items(uid)
    assert len(items) == 1
    assert items[0]["status"] == "following"

    await AiAgentService.process_chat(uid, "mark The Matrix as dropped", repo, None)
    assert repo.list_items(uid) == []


def test_protocol_v1_rating_zero_preserves_watched_item(client):
    from app.main import app

    repo = app.state.watchlist_repo
    uid = "local_test_user"

    # Protocol v1 sync with rating=5 creates both watchlist and rated_movies
    res1 = client.post("/api/sync/movies/push", json={
        "operations": [{
            "operationId": "op-v1-rate5",
            "entityId": "movie_603",
            "operationType": "upsert",
            "payload": {
                "mediaType": "movie",
                "tmdbId": 603,
                "title": "The Matrix",
                "status": "watched",
                "rating": 5,
            },
        }],
    })
    assert res1.status_code == 200
    assert len(repo.list_rated_movies(uid)) == 1
    assert any(i["tmdb_id"] == 603 and i["status"] == "watched" for i in repo.list_items(uid))

    # Clearing rating to 0 while keeping watched status clears rated_movies but keeps watched row
    res2 = client.post("/api/sync/movies/push", json={
        "operations": [{
            "operationId": "op-v1-rate0",
            "entityId": "movie_603",
            "operationType": "upsert",
            "payload": {
                "mediaType": "movie",
                "tmdbId": 603,
                "title": "The Matrix",
                "status": "watched",
                "rating": 0,
            },
        }],
    })
    assert res2.status_code == 200
    assert repo.list_rated_movies(uid) == []
    assert any(i["tmdb_id"] == 603 and i["status"] == "watched" for i in repo.list_items(uid))


@pytest.mark.asyncio
async def test_briefing_step4_race_waits_for_winner_and_clears_context(tmp_path, monkeypatch):
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", tmp_path / "briefing_race.db")
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()
    uid = "race_user_1"
    repo.save_agent_settings(uid, {"notify_on_login": True, "timezone": "America/Los_Angeles"})
    repo.add_item(uid, "movie", 550, "Fight Club", None, "2026-10-21", status="queue")

    stable_key = build_stable_daily_cache_key(uid, "America/Los_Angeles")
    completed_record = {
        "cache_key": stable_key,
        "cache_version": 2,
        "user_id": uid,
        "status": "completed",
        "briefing": "Winner generated briefing ready.",
        "briefing_text": "Winner generated briefing ready.",
        "selected_candidates": [],
        "result_source": "gemini_personalized_greeting",
    }

    with patch.object(repo, "claim_daily_greeting_generation", return_value=(False, None)), \
         patch.object(
             repo,
             "get_daily_greeting",
             side_effect=[None, {"status": "generating"}, completed_record],
         ), \
         patch("app.services.briefing_service.WeatherService") as mock_ws:
        mock_ws.return_value.get_weather_data = AsyncMock(return_value=None)
        mock_ws.return_value.get_weather_report = AsyncMock(return_value=None)

        result = await BriefingService.evaluate_startup_briefing(uid, repo, None)

    assert result["enabled"] is True
    assert result["briefing"] == "Winner generated briefing ready."
    assert result["cached"] is True
    assert get_current_run_context() is None


def test_cookie_csrf_cannot_be_bypassed_by_invalid_bearer_header(client_with_auth):
    csrf_token = _login_cookie_user(client_with_auth)
    valid_origin = "https://cinequeue-7tvty3vmvq-uw.a.run.app"
    claims = {"uid": "sec_user_1", "email": "inouye165@gmail.com", "email_verified": True}

    with patch("firebase_admin.auth.verify_id_token", side_effect=ValueError("invalid bearer")), \
         patch("firebase_admin.auth.verify_session_cookie", return_value=claims):
        # Fallback to session cookie must still enforce X-CSRF-Token and Origin
        bypass_attempt = client_with_auth.post(
            "/api/watchlist",
            json={"media_type": "movie", "tmdb_id": 550, "title": "Fight Club"},
            headers={"Authorization": "Bearer unverified_tok", "Origin": valid_origin},
        )
        assert bypass_attempt.status_code == 401

        bad_origin = client_with_auth.post(
            "/api/watchlist",
            json={"media_type": "movie", "tmdb_id": 550, "title": "Fight Club"},
            headers={
                "Authorization": "Bearer unverified_tok",
                "Origin": "https://untrusted.example",
                "X-CSRF-Token": csrf_token,
            },
        )
        assert bad_origin.status_code == 401


def test_production_config_fails_closed_when_auth_disabled_or_weak_admin_password():
    import importlib
    from conftest import reload_all_app_modules
    import app.config

    try:
        with patch.dict("os.environ", {"ENVIRONMENT": "production", "AUTH_ENABLED": "false"}):
            with pytest.raises(ValueError, match="AUTH_ENABLED must be True"):
                importlib.reload(app.config)

        with patch.dict(
            "os.environ",
            {
                "ENVIRONMENT": "production",
                "AUTH_ENABLED": "true",
                "AUTH_ALLOWED_EMAILS": "inouye165@gmail.com",
                "AUTH_ALLOWED_ORIGINS": "https://cinequeue.example",
                "FIREBASE_API_KEY": "mock_key",
                "ENABLE_FALLBACK_ADMIN_AUTH": "true",
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "short",
            },
        ):
            with pytest.raises(ValueError, match="at least 12 characters"):
                importlib.reload(app.config)
    finally:
        reload_all_app_modules()


def test_input_validation_path_traversal_actor_cap_and_no_store_headers(client):
    from app.firestore_repo import _doc_id, _safe_firestore_id

    # Firestore ID helpers reject path traversal and non-integer IDs
    for bad_doc_id in ("", ".", "..", "a/b", "a\\b", "../admin"):
        with pytest.raises(ValueError):
            _safe_firestore_id(bad_doc_id)
    for bad_tmdb in ("../x", True, 0, -10):
        with pytest.raises(ValueError):
            _doc_id("movie", bad_tmdb)  # type: ignore[arg-type]

    # Watchlist rejects string/boolean/negative tmdb_id and oversized titles with 400
    for bad_payload in (
        {"media_type": "movie", "tmdb_id": "not_an_int", "title": "Test"},
        {"media_type": "movie", "tmdb_id": True, "title": "Test"},
        {"media_type": "movie", "tmdb_id": -1, "title": "Test"},
        {"media_type": "movie", "tmdb_id": 100, "title": "x" * 501},
    ):
        res = client.post("/api/watchlist", json=bad_payload)
        assert res.status_code == 400

    # Sensitive endpoints emit Cache-Control: no-store
    wl_res = client.get("/api/watchlist")
    assert wl_res.status_code == 200
    assert "no-store" in (wl_res.headers.get("cache-control") or "")

    # Search actor filter fan-out is bounded to <= 10 actors
    client.app.state.tmdb = AsyncMock()
    too_many_actors = [("actor", f"Actor {i}") for i in range(11)]
    search_res = client.get("/api/search", params=too_many_actors)
    assert search_res.status_code == 400


def test_session_endpoint_rate_limits_repeated_failures_and_bounds_admin_password(client_with_auth):
    csrf_resp = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_resp.json()["csrf_token"]
    valid_origin = "https://cinequeue-7tvty3vmvq-uw.a.run.app"

    # Oversized admin password rejected by schema before PBKDF2 hashing
    huge_pwd = client_with_auth.post(
        "/api/admin/login",
        json={"username": "admin", "password": "A" * 2000, "csrf_token": csrf_token},
        headers={"Origin": valid_origin},
    )
    assert huge_pwd.status_code == 422

    # Repeated invalid session attempts trigger 429 rate limit
    with patch("firebase_admin.auth.verify_id_token", side_effect=ValueError("bad token")):
        statuses = []
        for _ in range(21):
            r = client_with_auth.post(
                "/api/auth/session",
                json={"id_token": "bad.jwt.token", "csrf_token": csrf_token},
                headers={"Origin": valid_origin},
            )
            statuses.append(r.status_code)
        assert statuses[-1] == 429
