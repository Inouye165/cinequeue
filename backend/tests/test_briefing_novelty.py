"""Tests for briefing novelty tracking, change detection, news clustering, session caching, and live Gemini integration."""

from datetime import date, timedelta
import pytest
from app.sqlite_repo import SqliteWatchlistRepository
from app.services.briefing_service import BriefingService, generate_item_key, compute_content_fingerprint
from app.services.agent_service import AiAgentService, RECOMMENDED_SYSTEM_PROMPT


@pytest.fixture
def repo(tmp_path, monkeypatch):
    db_file = tmp_path / "test_briefing_novelty.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repository = SqliteWatchlistRepository()
    yield repository
    repository.clear_all("test_user")


def test_generate_item_key_and_fingerprint():
    key = generate_item_key("newly_available", "movie_123", "2026-07-15")
    assert key == "newly_available:movie_123:2026-07-15"

    fp1 = compute_content_fingerprint("The Odyssey became available TODAY (2026-07-15).")
    fp2 = compute_content_fingerprint("  the odyssey became available today (2026-07-15).  ")
    assert fp1 == fp2


@pytest.mark.asyncio
async def test_first_time_user_and_returning_user_novelty(repo):
    user_id = "test_novelty_user"
    today = date.today()
    in_9_days = (today + timedelta(days=9)).isoformat()
    available_date = (today - timedelta(days=1)).isoformat()

    # Title A (in 9 days) and Title C (available yesterday)
    repo.add_item(user_id=user_id, media_type="movie", tmdb_id=1, title="Title A", poster_path=None, release_date=in_9_days, status="queue")
    repo.add_item(user_id=user_id, media_type="movie", tmdb_id=3, title="Title C", poster_path=None, release_date=available_date, status="queue")

    # First login briefing
    briefing1 = await BriefingService.evaluate_startup_briefing(user_id, repo, None, session_id="sess_1")
    assert briefing1["enabled"] is True
    assert briefing1["updates_count"] >= 1
    presented = repo.get_presented_briefing_keys(user_id)
    assert len(presented) >= 1

    # Second login: No changes occurred
    briefing2 = await BriefingService.evaluate_startup_briefing(user_id, repo, None, session_id="sess_2")
    assert briefing2["telemetry"]["already_presented_count"] >= 1
    assert briefing2["updates_count"] == 0

    # Third login: Title B added as newly available
    repo.add_item(user_id=user_id, media_type="movie", tmdb_id=2, title="Title B", poster_path=None, release_date=available_date, status="queue")
    briefing3 = await BriefingService.evaluate_startup_briefing(user_id, repo, None, session_id="sess_3")
    assert briefing3["updates_count"] == 1
    assert briefing3["updates"][0]["title"] == "Title B"


@pytest.mark.asyncio
async def test_session_deduplication(repo):
    user_id = "test_session_user"
    today = date.today().isoformat()
    repo.add_item(user_id=user_id, media_type="movie", tmdb_id=99, title="Session Title", poster_path=None, release_date=today, status="queue")

    res1 = await BriefingService.evaluate_startup_briefing(user_id, repo, None, session_id="session_abc")
    res2 = await BriefingService.evaluate_startup_briefing(user_id, repo, None, session_id="session_abc")

    assert res1["briefing"] == res2["briefing"]
    assert res1["updates_count"] == res2["updates_count"]


@pytest.mark.asyncio
async def test_single_title_query_does_not_dump_all_updates(repo):
    user_id = "test_single_title_query"
    repo.add_item(user_id=user_id, media_type="movie", tmdb_id=10, title="Title 1", poster_path=None, release_date="2026-08-01", status="queue")
    repo.add_item(user_id=user_id, media_type="movie", tmdb_id=20, title="Title 2", poster_path=None, release_date="2026-09-01", status="queue")

    reply = await AiAgentService.process_chat(user_id, "is Title 1 coming out soon?", repo, None)
    content = reply["message"]["content"]
    assert "Title 1" in content
    assert "Title 2" not in content


@pytest.mark.asyncio
async def test_neutral_fallback_when_gemini_unavailable(repo, monkeypatch):
    user_id = "test_fallback_user"
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "")
    today = date.today().isoformat()
    repo.add_item(user_id=user_id, media_type="movie", tmdb_id=88, title="Fallback Film", poster_path=None, release_date=today, status="queue")

    briefing = await BriefingService.evaluate_startup_briefing(user_id, repo, None, session_id="sess_fallback")
    assert briefing["enabled"] is True
    assert "Fallback Film" in briefing["briefing"]
    assert "*Sigh*" not in briefing["briefing"]


@pytest.mark.live_gemini
@pytest.mark.asyncio
async def test_live_gemini_provider_integration():
    """Optional live integration test using configured GEMINI_API_KEY."""
    from app.config import GEMINI_API_KEY
    if not GEMINI_API_KEY:
        pytest.skip("GEMINI_API_KEY not configured")

    res = await AiAgentService._call_gemini_api(
        RECOMMENDED_SYSTEM_PROMPT,
        "What is the capital of France? Answer in one short sentence."
    )
    assert res is not None
    assert "Paris" in res
