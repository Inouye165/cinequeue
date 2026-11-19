"""Regression tests for Sports router auth/CSRF, DB errors, NY timezone anchoring, and schedule fallback behavior."""

import time
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.sports_service import SportsService, get_active_schedule_dates


def _login_session_user(client_with_auth, uid: str = "sports_user_1", email: str = "inouye165@gmail.com") -> str:
    csrf_resp = client_with_auth.get("/api/auth/csrf")
    assert csrf_resp.status_code == 200
    csrf_token = csrf_resp.json()["csrf_token"]
    now = int(time.time())

    with patch("firebase_admin.auth.verify_id_token", return_value={
        "uid": uid,
        "email": email,
        "email_verified": True,
        "auth_time": now,
    }), patch("firebase_admin.auth.create_session_cookie", return_value="mock_sports_session"):
        sess_resp = client_with_auth.post(
            "/api/auth/session",
            json={"id_token": "tok", "csrf_token": csrf_token},
            headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"},
        )
        assert sess_resp.status_code == 200
    return csrf_token


def test_sports_endpoints_require_authentication(client_with_auth):
    assert client_with_auth.get("/api/sports/catalog").status_code == 401
    assert client_with_auth.get("/api/sports/schedule").status_code == 401
    assert client_with_auth.get("/api/sports/preferences").status_code == 401
    assert client_with_auth.put("/api/sports/preferences", json={
        "streaming_services": ["espn_plus"],
        "tracked_teams": ["nba_lal"],
        "show_in_queue": True,
        "setup_completed": True,
    }).status_code == 401


def test_sports_preferences_cookie_csrf_and_origin_enforcement(client_with_auth):
    csrf_token = _login_session_user(client_with_auth)
    payload = {
        "streaming_services": ["espn_plus", "youtube_tv"],
        "tracked_teams": ["nba_lal"],
        "show_in_queue": True,
        "setup_completed": True,
    }
    session_claims = {
        "uid": "sports_user_1",
        "email": "inouye165@gmail.com",
        "email_verified": True,
    }

    with patch("firebase_admin.auth.verify_session_cookie", return_value=session_claims):
        missing_csrf = client_with_auth.put(
            "/api/sports/preferences",
            json=payload,
            headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"},
        )
        assert missing_csrf.status_code == 401

        bad_origin = client_with_auth.put(
            "/api/sports/preferences",
            json=payload,
            headers={"Origin": "https://evil.example", "X-CSRF-Token": csrf_token},
        )
        assert bad_origin.status_code == 401

        valid = client_with_auth.put(
            "/api/sports/preferences",
            json=payload,
            headers={
                "Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app",
                "X-CSRF-Token": csrf_token,
            },
        )
        assert valid.status_code == 200
        data = valid.json()
        assert data["streaming_services"] == ["espn_plus", "youtube_tv"]
        assert data["tracked_teams"] == ["nba_lal"]


def test_sports_preferences_returns_503_on_db_error(client):
    from app.main import app

    with patch.object(app.state.watchlist_repo, "get_sports_preferences", side_effect=RuntimeError("db down")):
        resp = client.get("/api/sports/preferences")
    assert resp.status_code == 503


def test_active_schedule_dates_anchored_to_new_york_timezone():
    # 02:00 UTC Thursday is 22:00 EDT Wednesday — must stay on Wednesday in America/New_York
    wed_evening_edt = datetime(2026, 10, 22, 2, 0, tzinfo=timezone.utc)
    assert get_active_schedule_dates(wed_evening_edt) == [date(2026, 10, 21)]

    # Friday EDT expands to Friday + Saturday + Sunday
    fri_edt = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
    assert get_active_schedule_dates(fri_edt) == [
        date(2026, 10, 23),
        date(2026, 10, 24),
        date(2026, 10, 25),
    ]


@pytest.mark.asyncio
async def test_sports_schedule_empty_upstream_vs_failure_cooldown_and_team_filter():
    svc = SportsService(cache_ttl_seconds=300.0, refresh_cooldown_seconds=30.0)

    empty_resp = MagicMock(status_code=200)
    empty_resp.json.return_value = {"events": []}

    with patch("app.services.sports_service.httpx.AsyncClient") as mock_client_cls:
        client_inst = AsyncMock()
        client_inst.get = AsyncMock(return_value=empty_resp)
        mock_client_cls.return_value.__aenter__.return_value = client_inst

        # Upstream succeeded with 0 games -> must return [], NOT fake fallback games
        games = await svc.get_schedule()
        assert games == []
        calls_after_first = client_inst.get.await_count
        assert calls_after_first >= 2

        # Cooldown (<30s) suppresses repeated force_refresh hits
        await svc.get_schedule(force_refresh=True)
        assert client_inst.get.await_count == calls_after_first

    # Separate instance where upstream fails -> returns realistic fallback games & filters tracked_teams
    svc_fail = SportsService(cache_ttl_seconds=300.0, refresh_cooldown_seconds=30.0)
    with patch("app.services.sports_service.httpx.AsyncClient") as mock_client_cls:
        client_inst = AsyncMock()
        client_inst.get = AsyncMock(side_effect=httpx.ConnectError("upstream down"))
        mock_client_cls.return_value.__aenter__.return_value = client_inst

        fallback_all = await svc_fail.get_schedule()
        assert len(fallback_all) > 0

        lal_only = await svc_fail.get_schedule(tracked_teams=["nba_lal"])
        assert len(lal_only) >= 1
        assert all(
            g["home_team"]["id"] == "nba_lal" or g["away_team"]["id"] == "nba_lal"
            for g in lal_only
        )
