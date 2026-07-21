import pytest
from app.sqlite_repo import SqliteWatchlistRepository
from app.services.agent_service import AiAgentService, get_system_prompt


@pytest.fixture
def repo(tmp_path, monkeypatch):
    db_file = tmp_path / "test_agent_watchlist.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repository = SqliteWatchlistRepository()
    yield repository
    repository.clear_all("test_user")


def test_agent_settings_defaults_and_save(repo):
    user_id = "test_user_agent"
    settings = repo.get_agent_settings(user_id)
    assert settings["personality_preset"] == "cinephile"
    assert settings["notify_on_login"] is True

    updated = repo.save_agent_settings(user_id, {
        "personality_preset": "noir",
        "custom_prompt": "You are a detective",
        "notify_on_login": True,
        "auto_add_mentioned": True,
        "track_price_drops": False,
    })
    assert updated["personality_preset"] == "noir"
    assert updated["track_price_drops"] is False

    refetched = repo.get_agent_settings(user_id)
    assert refetched["personality_preset"] == "noir"


def test_chat_history_persistence_and_clear(repo):
    user_id = "test_user_chat"
    msg1 = repo.add_chat_message(user_id, "user", "I'm waiting for Dune 3")
    msg2 = repo.add_chat_message(user_id, "assistant", "Added Dune 3 to monitoring!", actions=[{"action": "add_monitoring", "title": "Dune 3"}])

    history = repo.list_chat_messages(user_id)
    assert len(history) == 2
    assert history[0]["content"] == "I'm waiting for Dune 3"
    assert history[1]["actions"][0]["action"] == "add_monitoring"

    repo.clear_chat_messages(user_id)
    history_after = repo.list_chat_messages(user_id)
    assert len(history_after) == 0


def test_extract_title_and_price():
    title, price = AiAgentService._extract_title_and_price("I am waiting for Severance season 2 to come out")
    assert title.lower() == "severance season 2"
    assert price is None

    title2, price2 = AiAgentService._extract_title_and_price("Notify me when Beetlejuice Beetlejuice drops under $3 to rent")
    assert title2.lower() == "beetlejuice beetlejuice"
    assert price2 == 3.0


@pytest.mark.asyncio
async def test_agent_briefing_evaluation(repo):
    user_id = "test_user_briefing"
    repo.add_item(
        user_id=user_id,
        media_type="movie",
        tmdb_id=12345,
        title="Test Sci-Fi Film",
        poster_path=None,
        release_date="2026-10-10",
        status="following",
        target_rental_price=3.99,
    )
    briefing = await AiAgentService.evaluate_monitored_updates(user_id, repo, None)
    assert briefing["enabled"] is True
    assert "briefing" in briefing
    assert len(briefing["briefing"]) > 0


@pytest.mark.asyncio
async def test_agent_multi_update_briefing_and_categories(repo):
    from datetime import date, timedelta
    user_id = "test_user_multi_briefing"
    today = date.today()
    in_1_day = (today + timedelta(days=1)).isoformat()
    ago_2_days = (today - timedelta(days=2)).isoformat()
    in_10_days = (today + timedelta(days=10)).isoformat()

    # 1. Imminent release (1 day away)
    repo.add_item(
        user_id=user_id,
        media_type="movie",
        tmdb_id=101,
        title="Imminent Blockbuster",
        poster_path=None,
        release_date=in_1_day,
        status="following",
    )

    # 2. Recently available (2 days ago / since last login)
    repo.add_item(
        user_id=user_id,
        media_type="tv",
        tmdb_id=102,
        title="Stuart Fails to Save the Universe",
        poster_path=None,
        release_date=ago_2_days,
        status="following",
    )

    # 3. Upcoming within 2 weeks (10 days away)
    repo.add_item(
        user_id=user_id,
        media_type="movie",
        tmdb_id=103,
        title="Future Sci-Fi Epic",
        poster_path=None,
        release_date=in_10_days,
        status="following",
    )

    result = await AiAgentService.evaluate_monitored_updates(user_id, repo, None)
    assert result["enabled"] is True
    assert result["updates_count"] == 3

    updates = result["updates"]
    titles = [u["title"] for u in updates]
    assert "Imminent Blockbuster" in titles
    assert "Stuart Fails to Save the Universe" in titles
    assert "Future Sci-Fi Epic" in titles

    # Check that briefing text includes ALL updates
    briefing_text = result["briefing"]
    assert "Imminent Blockbuster" in briefing_text
    assert "Stuart Fails to Save the Universe" in briefing_text
    assert "Future Sci-Fi Epic" in briefing_text


@pytest.mark.asyncio
async def test_chat_query_specific_show(repo):
    from datetime import date, timedelta
    user_id = "test_user_chat_show"
    today = date.today()
    in_1_day = (today + timedelta(days=1)).isoformat()

    repo.add_item(
        user_id=user_id,
        media_type="tv",
        tmdb_id=999,
        title="Stuart Fails to Save the Universe",
        poster_path=None,
        release_date=in_1_day,
        status="following",
    )

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message="why didn't the agent say something about stuart fails to save the universe",
        repo=repo,
        tmdb=None,
    )
    reply = res["message"]["content"]
    assert "Stuart Fails to Save the Universe" in reply


def test_agent_http_routes(repo, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from fastapi.testclient import TestClient
    from app.main import app

    app.state.watchlist_repo = repo
    client = TestClient(app)

    # Test GET briefing (verifying route does not collide with /api/{media_type}/{tmdb_id})
    res = client.get("/api/agent/briefing")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    assert "briefing" in res.json()

    # Test GET settings
    res = client.get("/api/agent/settings")
    assert res.status_code == 200
    assert res.json()["personality_preset"] == "cinephile"

    # Test POST settings
    res = client.post("/api/agent/settings", json={"personality_preset": "comedy", "custom_prompt": "funny bot"})
    assert res.status_code == 200
    assert res.json()["personality_preset"] == "comedy"

    # Test GET chat
    res = client.get("/api/agent/chat")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Test POST chat
    res = client.post("/api/agent/chat", json={"message": "I'm waiting for Inception"})
    assert res.status_code == 200
    assert "message" in res.json()

    # Test DELETE chat
    res = client.delete("/api/agent/chat")
    assert res.status_code == 200
    assert res.json() == {"status": "cleared"}



