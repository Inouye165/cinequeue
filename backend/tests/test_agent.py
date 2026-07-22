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


def test_persistent_query_memory_repository(repo):
    user_id = "test_user_mem"
    repo.add_query_memory(user_id, "what about Succession", tmdb_id=99, media_type="tv", title="Succession")
    repo.add_query_memory(user_id, "tell me about Avatar 3", title="Avatar 3")

    mems = repo.list_query_memories(user_id)
    assert len(mems) == 2
    titles = [m["title"] for m in mems]
    assert "Succession" in titles
    assert "Avatar 3" in titles

    removed = repo.remove_query_memory(user_id, "Succession")
    assert removed is True
    mems_after = repo.list_query_memories(user_id)
    assert len(mems_after) == 1
    assert mems_after[0]["title"] == "Avatar 3"


@pytest.mark.asyncio
async def test_auto_monitoring_intent_extraction(repo):
    user_id = "test_user_auto_intent"
    # "add succession to my monitor list"
    title, price = AiAgentService._extract_title_and_price("add succession to my monitor list")
    assert title and title.lower() == "succession"

    # "waiting for Severance"
    title2, price2 = AiAgentService._extract_title_and_price("waiting for Severance")
    assert title2 and title2.lower() == "severance"


@pytest.mark.asyncio
async def test_persistent_query_memory_briefing_recall(repo):
    from datetime import date, timedelta
    user_id = "test_user_mem_recall"
    today = date.today()
    in_2_days = (today + timedelta(days=2)).isoformat()

    # User asked about "What Dreams May Come" 20 days ago
    repo.add_query_memory(user_id, "any update on What Dreams May Come", title="What Dreams May Come")

    # Mock tmdb search to return release date in 2 days
    class DummyTmdb:
        async def get_details(self, media_type, tmdb_id):
            return {"release_date": in_2_days}
        async def search(self, title):
            return [{"title": title, "release_date": in_2_days, "media_type": "movie", "id": 777}]

    briefing = await AiAgentService.evaluate_monitored_updates(user_id, repo, DummyTmdb())
    assert briefing["enabled"] is True
    messages = [u["message"] for u in briefing["updates"]]
    assert any("MEMORY RECALL" in msg and "What Dreams May Come" in msg for msg in messages)


def test_extract_rating_and_delete_actions():
    title1, rating1 = AiAgentService._extract_rating_action("Add Braveheart to my watched list with a 4 star rating")
    assert title1 and title1.lower() == "braveheart"
    assert rating1 == 4

    title2, rating2 = AiAgentService._extract_rating_action("I watched Inception and rate it 5 stars")
    assert title2 and title2.lower() == "inception"
    assert rating2 == 5

    title3, rating3 = AiAgentService._extract_rating_action("Log a 3-star rating for Gladiator")
    assert title3 and title3.lower() == "gladiator"
    assert rating3 == 3

    title4, rating4 = AiAgentService._extract_rating_action("Add Titanic to my rated movies")
    assert title4 and title4.lower() == "titanic"
    assert rating4 == 5

    del_t1, del_type1 = AiAgentService._extract_delete_action("Remove Braveheart from my watched list")
    assert del_t1 and del_t1.lower() == "braveheart"
    assert del_type1 == "rating"

    del_t2, del_type2 = AiAgentService._extract_delete_action("Delete rating for Inception")
    assert del_t2 and del_t2.lower() == "inception"
    assert del_type2 == "rating"

    del_t3, del_type3 = AiAgentService._extract_delete_action("Remove Gladiator from my queue")
    assert del_t3 and del_t3.lower() == "gladiator"
    assert del_type3 == "watchlist"


@pytest.mark.asyncio
async def test_agent_process_chat_rating_and_deletion(repo):
    user_id = "test_user_rate_chat"

    class DummyTmdb:
        async def search(self, title):
            if "braveheart" in title.lower():
                return [{
                    "id": 19995,
                    "title": "Braveheart",
                    "media_type": "movie",
                    "release_date": "1995-05-24",
                    "poster_path": "/braveheart.jpg",
                }]
            return []

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message="Add Braveheart to my watched list with a 4 star rating",
        repo=repo,
        tmdb=DummyTmdb(),
    )

    actions = res["actions_taken"]
    assert len(actions) == 1
    assert actions[0]["action"] == "rate_movie"
    assert actions[0]["title"] == "Braveheart"
    assert actions[0]["rating"] == 4

    rated = repo.list_rated_movies(user_id)
    assert len(rated) == 1
    assert rated[0]["title"] == "Braveheart"
    assert rated[0]["rating"] == 4

    res_del = await AiAgentService.process_chat(
        user_id=user_id,
        user_message="Delete rating for Braveheart",
        repo=repo,
        tmdb=DummyTmdb(),
    )

    del_actions = res_del["actions_taken"]
    assert len(del_actions) == 1
    assert del_actions[0]["action"] == "delete_rating"
    assert del_actions[0]["title"] == "Braveheart"

    rated_after = repo.list_rated_movies(user_id)
    assert len(rated_after) == 0





