import pytest
from unittest.mock import AsyncMock, patch
from app.sqlite_repo import SqliteWatchlistRepository
from app.services.briefing_service import BriefingService
from app.services.agent_service import AiAgentService
from app.services.tmdb import TmdbClient


@pytest.mark.asyncio
async def test_daily_greeting_caching():
    repo = SqliteWatchlistRepository()
    user_id = "test_cache_user"
    repo.clear_all(user_id)

    with patch.object(AiAgentService, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        from app.services.agent_service import AgentResult
        mock_gemini.return_value = AgentResult(
            text="Hello, here is your daily briefing for today!",
            provider="gemini",
            model_requested="gemini-3.6-flash",
            model_used="gemini-3.6-flash",
            gemini_called=True,
            fallback_used=False,
            fallback_reason=None,
            http_status=200,
            request_duration_ms=100.0,
            actions_taken=[],
        )

        # First call of the day - should call Gemini API
        res1 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, force_refresh=False)
        assert res1["briefing"] == "Hello, here is your daily briefing for today!"
        assert mock_gemini.call_count == 1

        # Second call of the same day - should return daily cached briefing WITHOUT calling Gemini API again
        res2 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, force_refresh=False)
        assert res2["briefing"] == "Hello, here is your daily briefing for today!"
        assert mock_gemini.call_count == 1  # Still 1! Gemini API call skipped!

        # Third call with force_refresh=True - should bypass daily cache and call Gemini API again
        res3 = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, force_refresh=True)
        assert res3["briefing"] == "Hello, here is your daily briefing for today!"
        assert mock_gemini.call_count == 2


@pytest.mark.asyncio
async def test_tmdb_metadata_caching():
    import os
    with patch("app.services.tmdb.TMDB_API_KEY", "test_tmdb_key_for_ci"), patch.dict(os.environ, {"TMDB_API_KEY": "test_tmdb_key_for_ci"}):
        tmdb = TmdbClient()

    with patch.object(tmdb, "_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 27205,
            "title": "Inception",
            "release_date": "2010-07-16",
            "genres": [{"name": "Sci-Fi"}],
            "results": [{"id": 27205, "title": "Inception", "popularity": 10.0, "media_type": "movie"}],
        }

        # First search call - triggers HTTP _get
        res1 = await tmdb.search("Inception")
        assert len(res1) > 0
        call_count_1 = mock_get.call_count

        # Second search call - uses in-memory TTL cache, no additional _get
        res2 = await tmdb.search("Inception")
        assert len(res2) > 0
        assert mock_get.call_count == call_count_1

        # First details call - triggers HTTP _get
        det1 = await tmdb.get_details("movie", 27205)
        assert det1["title"] == "Inception"
        call_count_2 = mock_get.call_count

        # Second details call - uses in-memory TTL cache
        det2 = await tmdb.get_details("movie", 27205)
        assert det2["title"] == "Inception"
        assert mock_get.call_count == call_count_2

    await tmdb.close()
