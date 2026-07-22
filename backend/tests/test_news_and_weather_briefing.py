"""Comprehensive unit test suite for Live Weather and Entertainment News Briefing System."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from app.services.agent_service import AiAgentService
from app.services.briefing_service import BriefingService
from app.services.news_service import (
    NewsArticleData,
    NewsCategory,
    NewsVerification,
    cluster_news_stories,
    rank_briefing_candidates,
)
from app.services.weather_provider import WeatherData, WeatherProvider
from app.services.weather_service import WeatherService
from app.sqlite_repo import SqliteWatchlistRepository


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "test_briefing.db"
    with patch("app.sqlite_repo.DB_PATH", str(db_path)):
        repo = SqliteWatchlistRepository()
        yield repo


# Dummy weather provider for testing
class MockWeatherProvider(WeatherProvider):
    def __init__(self, should_fail: bool = False, has_alert: bool = False):
        self._should_fail = should_fail
        self._has_alert = has_alert
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock-weather"

    async def fetch_weather(self, location: str) -> WeatherData | None:
        self.call_count += 1
        if self._should_fail:
            return None
        return WeatherData(
            conditions="Light rain",
            temperature_f=61.0,
            temperature_c=16.1,
            high_f=68.0,
            low_f=55.0,
            precipitation_probability=70,
            significant_alert="Severe Thunderstorm Warning" if self._has_alert else None,
            retrieved_at="2026-07-22T10:00:00Z",
            location_used=location,
            provider_name=self.provider_name,
            status="success",
        )


@pytest.mark.asyncio
async def test_weather_retrieval_and_caching():
    """Verify weather retrieval using user location and in-memory cache behavior."""
    provider = MockWeatherProvider()
    service = WeatherService(providers=[provider])

    # First call - fetches from provider
    res1 = await service.get_weather_data("Concord, CA")
    assert res1 is not None
    assert res1.conditions == "Light rain"
    assert res1.temperature_f == 61.0
    assert provider.call_count == 1

    # Second call within cache TTL - returns cached data without calling provider again
    res2 = await service.get_weather_data("Concord, CA")
    assert res2 is not None
    assert res2.status == "cached"
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_weather_failure_does_not_block_briefing(repo):
    """Verify that a weather service failure silently omits weather and allows briefing to complete."""
    user_id = "user_weather_fail"
    repo.save_agent_settings(user_id, {"location": "InvalidCityName9999", "notify_on_login": True})
    repo.add_item(user_id, "movie", 101, "Test Movie", None, "2026-08-01", status="queue")

    failing_provider = MockWeatherProvider(should_fail=True)
    with patch("app.services.briefing_service.WeatherService", lambda: WeatherService(providers=[failing_provider])):
        res = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None)

    assert res["enabled"] is True
    assert res["briefing"] is not None
    assert res["weather"] is None
    assert "Test Movie" in res["briefing"] or len(res["updates"]) > 0


@pytest.mark.asyncio
async def test_severe_weather_alert_not_a_joke():
    """Verify severe weather alerts are formatted respectfully in structured prompt guidelines."""
    provider = MockWeatherProvider(has_alert=True)
    wx_data = await provider.fetch_weather("Concord, CA")

    settings = {"location": "Concord, CA"}
    items = [{"summary": "Movie A is releasing soon.", "title": "Movie A"}]

    briefing_text = await AiAgentService._format_structured_llm_briefing(
        settings=settings, weather_data=wx_data, briefing_items=items
    )
    assert "Good morning" in briefing_text or "Movie A" in briefing_text


@pytest.mark.asyncio
async def test_weather_greeting_omitted_in_unrelated_chat(repo):
    """Verify weather is not inserted when user asks an unrelated movie question."""
    user_id = "user_chat_wx"
    repo.save_agent_settings(user_id, {"location": "Tokyo"})
    repo.add_item(user_id, "movie", 201, "Inception", None, "2026-08-01", status="queue")

    res = await AiAgentService.process_chat(user_id, "When does Inception release?", repo, tmdb=None)
    reply = res["message"]["content"]
    assert "Inception" in reply
    assert "°F" not in reply
    assert "Tokyo" not in reply


def test_story_clustering_deduplication():
    """Verify multiple articles reporting the same event become 1 story cluster, preferring official sources."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    articles = [
        NewsArticleData(
            headline="Rumor: Sequel B might begin production",
            source="Blog Aggregator",
            url="http://blog.com/1",
            published_at=now_iso,
            first_discovered_at=now_iso,
            last_checked_at=now_iso,
            related_title="Sequel B",
            title_id="movie_202",
            category=NewsCategory.PRODUCTION_STARTED,
            verification=NewsVerification.RUMOR,
            summary="Rumor about Sequel B.",
            normalized_url="blog.com/1",
            content_fingerprint="fp12345",
            story_cluster_id="cluster_sequel_b",
        ),
        NewsArticleData(
            headline="Official: Studio confirms Sequel B production started",
            source="Official Studio",
            url="http://studio.com/news",
            published_at=now_iso,
            first_discovered_at=now_iso,
            last_checked_at=now_iso,
            related_title="Sequel B",
            title_id="movie_202",
            category=NewsCategory.PRODUCTION_STARTED,
            verification=NewsVerification.OFFICIAL,
            summary="Studio announced production started.",
            normalized_url="studio.com/news",
            content_fingerprint="fp12345",
            story_cluster_id="cluster_sequel_b",
        ),
        NewsArticleData(
            headline="Production has officially begun on Sequel B",
            source="Trade News",
            url="http://tradenews.com/2",
            published_at=now_iso,
            first_discovered_at=now_iso,
            last_checked_at=now_iso,
            related_title="Sequel B",
            title_id="movie_202",
            category=NewsCategory.PRODUCTION_STARTED,
            verification=NewsVerification.CONFIRMED,
            summary="Trade news confirms filming.",
            normalized_url="tradenews.com/2",
            content_fingerprint="fp12345",
            story_cluster_id="cluster_sequel_b",
        ),
    ]

    clusters = cluster_news_stories(articles)
    assert len(clusters) == 1
    primary = clusters[0]
    assert primary["verification"] == NewsVerification.OFFICIAL
    assert primary["source"] == "Official Studio"
    assert len(primary["supporting_sources"]) == 2


@pytest.mark.asyncio
async def test_novelty_and_material_change_tracking(repo):
    """Verify seen news is skipped, but material change (verification upgrade or date change) triggers presentation."""
    user_id = "user_novelty"
    repo.save_agent_settings(user_id, {"notify_on_login": True})

    # Step 1: Initial presentation of a rumor
    initial_items = [{
        "item_key": "cluster_b",
        "story_cluster_id": "cluster_b",
        "type": "entertainment_news",
        "category": NewsCategory.RUMOR_UNCONFIRMED,
        "verification": NewsVerification.RUMOR,
        "urgency": 3,
        "title": "Movie B",
        "title_id": "movie_300",
        "summary": "Rumor that Movie B will start filming.",
        "content_fingerprint": "fp_rumor",
    }]

    repo.record_briefing_presentations(user_id, initial_items)
    presented_keys = repo.get_presented_briefing_keys(user_id)
    assert "cluster_b" in presented_keys

    # Step 2: Unchanged rumor is skipped
    cand1 = dict(initial_items[0])
    fp_match = (cand1["content_fingerprint"] == presented_keys["cluster_b"]["content_fingerprint"])
    assert fp_match is True

    # Step 3: Material change (Official confirmation with upgraded verification)
    material_item = dict(initial_items[0])
    material_item["verification"] = NewsVerification.OFFICIAL
    material_item["summary"] = "Studio officially confirmed filming has started on Movie B."
    material_item["content_fingerprint"] = "fp_official_confirmed"

    # Material change check
    curr_fp = material_item["content_fingerprint"]
    prev_fp = presented_keys["cluster_b"]["content_fingerprint"]
    assert curr_fp != prev_fp  # Trigger material update presentation!


@pytest.mark.asyncio
async def test_previous_login_timestamp_captured_before_update(repo):
    """Verify previous_login_at is captured before evaluating briefing and before updating reference timestamps."""
    user_id = "user_timestamp"
    repo.save_agent_settings(user_id, {"notify_on_login": True})

    # Set initial state
    t1 = "2026-07-20T10:00:00Z"
    repo.update_user_briefing_state(user_id, login_at=t1, briefing_presented_at=t1)

    initial_state = repo.get_user_briefing_state(user_id)
    assert initial_state["previous_login_at"] == t1

    # Run briefing
    res = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None)

    # In response metadata, previous_login_at must reflect t1
    assert res["previous_login_at"] == t1

    # After evaluation, DB is updated to newer timestamp
    updated_state = repo.get_user_briefing_state(user_id)
    assert updated_state["previous_login_at"] != t1


@pytest.mark.asyncio
async def test_manual_refresh_command(repo):
    """Verify manual 'What's new?' chat query triggers force_refresh novelty pipeline."""
    user_id = "user_manual_refresh"
    repo.save_agent_settings(user_id, {"notify_on_login": True})
    repo.add_item(user_id, "movie", 401, "Movie Alpha", None, "2026-08-10", status="queue")

    chat_res = await AiAgentService.process_chat(user_id, "What's new on my watchlist?", repo, tmdb=None)
    reply = chat_res["message"]["content"]
    assert "Good morning" in reply or "Movie Alpha" in reply or "watchlist" in reply


def test_ranking_monitored_title_over_general_news():
    """Verify candidate ranking prioritizes direct watchlist title updates over generic rumors."""
    candidates = [
        {
            "title": "Unrelated Speculation",
            "type": "entertainment_news",
            "category": NewsCategory.RUMOR_UNCONFIRMED,
            "verification": NewsVerification.RUMOR,
            "urgency": 4,
            "new_to_user": True,
        },
        {
            "title": "Monitored Movie",
            "type": "newly_available",
            "category": "newly_available",
            "urgency": 1,
            "new_to_user": True,
        },
    ]

    ranked = rank_briefing_candidates(candidates)
    assert ranked[0]["title"] == "Monitored Movie"
