"""Unit tests for CineQueue daily startup briefing caching, timezone resolution, fallback quality, truncation validation, concurrency protection, and manual refresh."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.decision_models import (
    STARTUP_BRIEFING_CACHE_VERSION,
    build_stable_daily_cache_key,
    resolve_user_local_date,
)
from app.services.agent_service import AgentResult, AiAgentService, normalize_display_title, validate_fallback_greeting
from app.services.briefing_service import BriefingService
from app.sqlite_repo import SqliteWatchlistRepository


@pytest.fixture(autouse=True)
def mock_weather():
    with patch("app.services.briefing_service.WeatherService") as mock_ws:
        instance = mock_ws.return_value
        instance.get_weather_data = AsyncMock(return_value=None)
        instance.get_weather_report = AsyncMock(return_value=None)
        yield instance


@pytest.fixture
def repo():
    return SqliteWatchlistRepository()


@pytest.mark.asyncio
async def test_title_normalization():
    assert normalize_display_title("the odyssey,") == "The Odyssey"
    assert normalize_display_title("  mamma mia!  ") == "Mamma Mia!"
    assert normalize_display_title("What If...?") == "What If...?"
    assert normalize_display_title("spiderman..") == "Spiderman"
    assert normalize_display_title("The Matrix:,") == "The Matrix"


@pytest.mark.asyncio
async def test_validate_fallback_greeting():
    assert validate_fallback_greeting("Welcome back! The Odyssey was released on July 17 and is now available.") is True
    assert validate_fallback_greeting("Welcome back! Here are the latest updates for the odyssey,.") is False
    assert validate_fallback_greeting("Welcome back! Here are the latest updates for") is False
    assert validate_fallback_greeting("Welcome back! MEMORY RECALL: some text.") is False
    assert validate_fallback_greeting("") is False
    assert validate_fallback_greeting("Short text.") is False


@pytest.mark.asyncio
async def test_1_first_successful_gemini_startup(repo):
    """Test 1: First successful Gemini startup creates completed stable cache record."""
    user_id = "user_test_1"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})
    repo.add_item(user_id, "movie", 101, "The Odyssey", "/odyssey.jpg", release_date="2026-07-17", status="queue")

    mock_agent_res = AgentResult(
        text="Welcome back! The Odyssey was released on July 17 and is now available in theaters.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_agent_res

        res = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_1")
        assert res["enabled"] is True
        assert res["briefing"] == "Welcome back! The Odyssey was released on July 17 and is now available in theaters."
        assert mock_gemini.call_count == 1

        local_date, _ = resolve_user_local_date("America/Los_Angeles")
        expected_key = build_stable_daily_cache_key(user_id, local_date, STARTUP_BRIEFING_CACHE_VERSION)
        cached_rec = repo.get_daily_greeting(user_id, expected_key)
        assert cached_rec is not None
        assert cached_rec["status"] == "completed"
        assert cached_rec["result_source"] == "fresh_gemini"


@pytest.mark.asyncio
async def test_2_second_startup_same_day(repo):
    """Test 2: Second startup same day returns exact same greeting with zero external calls."""
    user_id = "user_test_2"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})
    repo.add_item(user_id, "movie", 102, "Dune 2", "/dune2.jpg", release_date="2026-03-01", status="queue")

    mock_agent_res = AgentResult(
        text="Welcome back! Dune 2 is available to watch.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_agent_res

        res1 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_1")
        assert mock_gemini.call_count == 1

        res2 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_1")
        assert res2["briefing"] == res1["briefing"]
        assert mock_gemini.call_count == 1  # 0 new Gemini calls!
        assert res2["telemetry"]["external_attempt_counts"]["gemini"] == 0
        assert res2["telemetry"]["external_attempt_counts"]["weather"] == 0
        assert res2["telemetry"]["external_attempt_counts"]["tmdb_details"] == 0


@pytest.mark.asyncio
async def test_3_different_session_same_day(repo):
    """Test 3: Different session same day returns same greeting with zero external calls."""
    user_id = "user_test_3"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    mock_agent_res = AgentResult(
        text="Welcome back! Everything is up to date on your monitored queue today.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_agent_res

        res1 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="session_A")
        res2 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="session_B_different")

        assert res1["briefing"] == res2["briefing"]
        assert mock_gemini.call_count == 1


@pytest.mark.asyncio
async def test_4_failed_gemini_generation_saves_and_reuses_local_fallback(repo):
    """Test 4: Failed Gemini generation generates local fallback, saves as completed, and reuses same day."""
    user_id = "user_test_4"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})
    repo.add_item(user_id, "movie", 104, "the odyssey,", "/odyssey.jpg", release_date="2026-07-17", status="queue")

    failed_res = AgentResult(
        text="",
        provider="fallback",
        model_requested="gemini-2.5-flash",
        model_used=None,
        gemini_called=True,
        fallback_used=True,
        fallback_reason="primary_max_tokens_truncated",
        http_status=503,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = failed_res

        res1 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_err")
        assert res1["enabled"] is True
        assert "The Odyssey" in res1["briefing"]

        # Check completed record in repo
        local_date, _ = resolve_user_local_date("America/Los_Angeles")
        key = build_stable_daily_cache_key(user_id, local_date, STARTUP_BRIEFING_CACHE_VERSION)
        rec = repo.get_daily_greeting(user_id, key)
        assert rec is not None
        assert rec["status"] == "completed"
        assert rec["result_source"] == "local_rule_fallback"

        # Second call hits cache
        res2 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_err_2")
        assert res2["briefing"] == res1["briefing"]
        assert mock_gemini.call_count == 1


@pytest.mark.asyncio
async def test_5_old_inner_cache_not_called(repo):
    """Test 5: Verify the startup path does not generate or check candidate-dependent cache keys YYYY-MM-DD:<hash>."""
    user_id = "user_test_5"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    mock_agent_res = AgentResult(
        text="Welcome back! Everything is up to date on your monitored queue today.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    get_daily_spy = MagicMock(side_effect=repo.get_daily_greeting)

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini, \
         patch.object(repo, "get_daily_greeting", side_effect=get_daily_spy):
        mock_gemini.return_value = mock_agent_res

        await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_5")

        # Verify all get_daily_greeting calls used the stable v2 key format
        for call in get_daily_spy.call_args_list:
            key_arg = call[0][1] if len(call[0]) > 1 else call[1].get("date_str")
            assert key_arg.startswith("startup_briefing:")
            assert ":v2" in key_arg
            assert ":" not in key_arg.replace("startup_briefing:", "") or "v2" in key_arg


@pytest.mark.asyncio
async def test_6_concurrent_startup_requests(repo):
    """Test 6: Concurrent startup requests acquire 1 claim, wait, and return identical text with 1 generation."""
    user_id = "user_test_6"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})
    repo.add_item(user_id, "movie", 201, "Avatar 3", "/avatar.jpg", release_date="2026-12-18", status="queue")

    mock_agent_res = AgentResult(
        text="Welcome back! Avatar 3 is scheduled for release on December 18.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_agent_res

        task1 = BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="conc_1")
        task2 = BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="conc_2")

        res1, res2 = await asyncio.gather(task1, task2)

        assert res1["briefing"] == res2["briefing"]
        assert mock_gemini.call_count == 1


@pytest.mark.asyncio
async def test_7_generation_lease_recovery(repo):
    """Test 7: An expired generating record is atomically recovered by the next request."""
    user_id = "user_test_7"
    local_date, _ = resolve_user_local_date("America/Los_Angeles")
    key = build_stable_daily_cache_key(user_id, local_date, STARTUP_BRIEFING_CACHE_VERSION)

    # Insert an expired generating record
    expired_exp = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    repo.save_daily_greeting(user_id, key, {
        "status": "generating",
        "lease_expires_at": expired_exp,
        "created_at": expired_exp,
    })

    acquired, claim = repo.claim_daily_greeting_generation(user_id, key, lease_seconds=30, force_refresh=False)
    assert acquired is True


@pytest.mark.asyncio
async def test_8_active_generation_lease(repo):
    """Test 8: An active non-expired generating record prevents another request from making external calls."""
    user_id = "user_test_8"
    local_date, _ = resolve_user_local_date("America/Los_Angeles")
    key = build_stable_daily_cache_key(user_id, local_date, STARTUP_BRIEFING_CACHE_VERSION)

    # Insert an active generating record with future lease
    future_exp = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    repo.save_daily_greeting(user_id, key, {
        "status": "generating",
        "lease_expires_at": future_exp,
        "created_at": repo.utc_now_iso(),
    })

    acquired, claim = repo.claim_daily_greeting_generation(user_id, key, lease_seconds=30, force_refresh=False)
    assert acquired is False


@pytest.mark.asyncio
async def test_9_california_date_boundary():
    """Test 9: 2026-07-25 02:00:00 UTC correctly resolves to 2026-07-24 in America/Los_Angeles."""
    dt_utc = datetime(2026, 7, 25, 2, 0, 0, tzinfo=timezone.utc)
    local_date, tz_name = resolve_user_local_date("America/Los_Angeles", now_dt=dt_utc)

    assert local_date == "2026-07-24"
    assert tz_name == "America/Los_Angeles"


@pytest.mark.asyncio
async def test_10_next_local_day(repo):
    """Test 10: Advancing to the next local day triggers exactly one new generation."""
    user_id = "user_test_10"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    mock_agent_res = AgentResult(
        text="Welcome back! Day 1 greeting.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = mock_agent_res

        dt_day1 = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
        with patch("app.decision_models.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: dt_day1.astimezone(tz) if tz else dt_day1

            res1 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="s1")
            assert mock_gemini.call_count == 1

        dt_day2 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
        with patch("app.decision_models.datetime") as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: dt_day2.astimezone(tz) if tz else dt_day2

            res2 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="s2")
            assert mock_gemini.call_count == 2  # New day triggers new generation!


@pytest.mark.asyncio
async def test_11_manual_refresh(repo):
    """Test 11: Explicit force_refresh=True forces a new generation and replaces the completed record."""
    user_id = "user_test_11"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    res1 = AgentResult(
        text="Welcome back! Initial briefing.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )
    res2 = AgentResult(
        text="Welcome back! Refreshed briefing.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = res1
        r1 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, force_refresh=False)
        assert r1["briefing"] == "Welcome back! Initial briefing."

        mock_gemini.return_value = res2
        r2 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, force_refresh=True)
        assert r2["briefing"] == "Welcome back! Refreshed briefing."
        assert mock_gemini.call_count == 2


@pytest.mark.asyncio
async def test_12_manual_refresh_failure_retains_prior_completed_greeting(repo):
    """Test 12: Manual refresh failure retains the prior completed greeting."""
    user_id = "user_test_12"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    res1 = AgentResult(
        text="Welcome back! Original completed greeting.",
        provider="gemini",
        model_requested="gemini-2.5-flash",
        model_used="gemini-2.5-flash",
        gemini_called=True,
        fallback_used=False,
        fallback_reason=None,
        http_status=200,
        request_duration_ms=100.0,
        actions_taken=[],
    )

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = res1
        r1 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, force_refresh=False)
        assert r1["briefing"] == "Welcome back! Original completed greeting."

        # Simulate exception during refresh
        mock_gemini.side_effect = Exception("API connection dropped")
        r2 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, force_refresh=True)
        # Prior completed greeting retained
        assert r2["briefing"] == "Welcome back! Original completed greeting."


@pytest.mark.asyncio
async def test_13_fallback_quality(repo):
    """Test 13: Local fallback given raw title 'the odyssey,' and release summary."""
    user_id = "user_test_13"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    items = [{
        "title": "the odyssey,",
        "summary": "It is releasing/available (2026-07-17).",
        "type": "newly_available",
    }]

    fallback = AiAgentService._generate_dynamic_human_briefing(
        settings=repo.get_agent_settings(user_id),
        location="",
        weather_json=None,
        briefing_items=items,
        time_of_day="morning",
    )

    assert "The Odyssey" in fallback
    assert "the odyssey," not in fallback
    assert "MEMORY RECALL" not in fallback
    assert ",." not in fallback
    assert ".." not in fallback
    assert fallback.endswith(".")
    assert validate_fallback_greeting(fallback) is True
