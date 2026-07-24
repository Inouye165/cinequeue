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

    # Check that briefing text is a non-empty, reasonable response
    briefing_text = result["briefing"]
    assert len(briefing_text) > 10, f"Expected non-empty briefing text, got: {briefing_text!r}"


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
    # Accept any reasonable non-empty reply from the live LLM
    assert len(reply) > 10, f"Expected non-empty reply, got: {reply!r}"


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


@pytest.mark.asyncio
async def test_agent_rating_and_status_intents(repo):
    user_id = "test_user_intents"

    class DummyTmdb:
        async def search(self, query):
            if "braveheart" in query.lower():
                return [{
                    "id": 9991,
                    "title": "Braveheart",
                    "media_type": "movie",
                    "release_date": "1995-05-24",
                    "poster_path": "/braveheart.jpg",
                }, {
                    "id": 9992,
                    "title": "Braveheart II",
                    "media_type": "movie",
                    "release_date": "2020-01-01",
                    "poster_path": "/braveheart2.jpg",
                }]
            elif "gladiator" in query.lower():
                return [{
                    "id": 8881,
                    "title": "Gladiator",
                    "media_type": "movie",
                    "release_date": "2000-05-01",
                    "poster_path": "/gladiator.jpg",
                }]
            return []

    # Test "add braveheart to movies ive watched and rate it 5"
    title, r_val = AiAgentService._extract_rating_action("add braveheart to movies ive watched and rate it 5")
    assert title.lower() == "braveheart"
    assert r_val == 5

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message="add braveheart to movies ive watched and rate it 5",
        repo=repo,
        tmdb=DummyTmdb(),
    )

    actions = res["actions_taken"]
    assert len(actions) >= 1
    assert actions[0]["action"] == "rate_movie"
    assert actions[0]["title"] == "Braveheart"
    assert actions[0]["rating"] == 5

    rated = repo.list_rated_movies(user_id)
    assert len(rated) == 1
    assert rated[0]["title"] == "Braveheart"
    assert rated[0]["rating"] == 5

    # Test status update
    s_title, new_status, is_owned = AiAgentService._extract_status_action("mark Braveheart as watched")
    assert s_title.lower() == "braveheart"
    assert new_status == "watched"

    # Test search action
    s_query = AiAgentService._extract_search_action("search Gladiator")
    assert s_query.lower() == "gladiator"

    res_s = await AiAgentService.process_chat(
        user_id=user_id,
        user_message="search Gladiator",
        repo=repo,
        tmdb=DummyTmdb(),
    )
    s_actions = res_s["actions_taken"]
    assert len(s_actions) == 1
    assert s_actions[0]["action"] == "movie_search"
    assert len(s_actions[0]["results"]) == 1


@pytest.mark.asyncio
async def test_patriot_extraction_and_fallback_search(repo):
    user_id = "test_user_patriot"
    prompt = "please add the patriot with mel gibson to the lis and rate it 4"

    # Test title and rating extraction
    extracted_title, extracted_rating = AiAgentService._extract_rating_action(prompt)
    assert extracted_title is not None
    assert "patriot" in extracted_title.lower()
    assert extracted_rating == 4

    class DummyPatriotTmdb:
        async def search(self, query):
            # If query contains full string with actor, return empty (simulating TMDB strict match failure)
            if "with mel gibson" in query.lower():
                return []
            # Simplified query "the patriot" returns candidates
            if "patriot" in query.lower():
                return [{
                    "id": 2501,
                    "title": "The Patriot",
                    "media_type": "movie",
                    "release_date": "2000-06-28",
                    "overview": "In 1776 South Carolina, Benjamin Martin (Mel Gibson) is drawn into the Revolutionary War.",
                    "poster_path": "/patriot.jpg",
                }]
            return []

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message=prompt,
        repo=repo,
        tmdb=DummyPatriotTmdb(),
    )

    actions = res["actions_taken"]
    assert len(actions) == 1
    assert actions[0]["action"] == "rate_movie"
    assert actions[0]["title"] == "The Patriot"
    assert actions[0]["rating"] == 4

    rated = repo.list_rated_movies(user_id)
    assert len(rated) == 1
    assert rated[0]["title"] == "The Patriot"
    assert rated[0]["rating"] == 4


def test_chat_history_recent_messages_persistence(repo):
    user_id = "test_recent_history_user"
    # Insert 60 messages
    for i in range(1, 61):
        repo.add_chat_message(user_id, "user", f"Message {i}")

    history = repo.list_chat_messages(user_id, limit=50)
    assert len(history) == 50
    # Must contain the most recent message #60 at the end
    assert history[-1]["content"] == "Message 60"
    assert history[0]["content"] == "Message 11"


@pytest.mark.asyncio
async def test_harry_potter_series_rating_expansion(repo):
    user_id = "test_hp_series_user"
    prompt = "add the harry potter series of movies to the rated movies"

    class DummyHpTmdb:
        async def search(self, query):
            return [
                {"id": 671, "title": "Harry Potter and the Philosopher's Stone", "media_type": "movie", "release_date": "2001-11-16", "poster_path": "/hp1.jpg"},
                {"id": 672, "title": "Harry Potter and the Chamber of Secrets", "media_type": "movie", "release_date": "2002-11-15", "poster_path": "/hp2.jpg"},
                {"id": 673, "title": "Harry Potter and the Prisoner of Azkaban", "media_type": "movie", "release_date": "2004-05-31", "poster_path": "/hp3.jpg"},
            ]

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message=prompt,
        repo=repo,
        tmdb=DummyHpTmdb(),
    )

    actions = res["actions_taken"]
    assert len(actions) == 3
    titles_rated = [a["title"] for a in actions]
    assert "Harry Potter and the Philosopher's Stone" in titles_rated
    assert "Harry Potter and the Chamber of Secrets" in titles_rated

    rated = repo.list_rated_movies(user_id)
    assert len(rated) == 3


@pytest.mark.asyncio
async def test_harry_potter_batch_queue_entry(repo):
    user_id = "test_hp_queue_user"
    prompt = "enter the series of harry potter movies"

    class DummyHpTmdb:
        async def search(self, query):
            assert "series" not in query.lower()
            return [
                {"id": 671, "title": "Harry Potter and the Sorcerer's Stone", "media_type": "movie", "release_date": "2001-11-16", "poster_path": "/hp1.jpg"},
                {"id": 672, "title": "Harry Potter and the Chamber of Secrets", "media_type": "movie", "release_date": "2002-11-15", "poster_path": "/hp2.jpg"},
                {"id": 673, "title": "Harry Potter and the Prisoner of Azkaban", "media_type": "movie", "release_date": "2004-05-31", "poster_path": "/hp3.jpg"},
            ]

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message=prompt,
        repo=repo,
        tmdb=DummyHpTmdb(),
    )

    actions = res["actions_taken"]
    assert len(actions) == 3
    actions_titles = [a["title"] for a in actions]
    assert "Harry Potter and the Sorcerer's Stone" in actions_titles
    assert "Harry Potter and the Chamber of Secrets" in actions_titles

    items = repo.list_items(user_id)
    assert len(items) == 3


@pytest.mark.asyncio
async def test_ordinal_range_slicing(repo):
    user_id = "test_ordinal_user"
    prompt = "add the 2nd through the end of the harry potter movies"

    class DummyHpTmdb:
        async def search(self, query):
            assert "2nd" not in query.lower()
            return [
                {"id": 671, "title": "Harry Potter and the Sorcerer's Stone", "media_type": "movie"},
                {"id": 672, "title": "Harry Potter and the Chamber of Secrets", "media_type": "movie"},
                {"id": 673, "title": "Harry Potter and the Prisoner of Azkaban", "media_type": "movie"},
                {"id": 674, "title": "Harry Potter and the Goblet of Fire", "media_type": "movie"},
            ]

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message=prompt,
        repo=repo,
        tmdb=DummyHpTmdb(),
    )

    actions = res["actions_taken"]
    # Should slice from 2nd item (index 1) to end -> 3 movies
    assert len(actions) == 3
    action_titles = [a["title"] for a in actions]
    assert "Harry Potter and the Sorcerer's Stone" not in action_titles
    assert "Harry Potter and the Chamber of Secrets" in action_titles
    assert "Harry Potter and the Goblet of Fire" in action_titles


@pytest.mark.asyncio
async def test_pronoun_context_followup(repo):
    user_id = "test_pronoun_user"

    class DummyHpTmdb:
        async def search(self, query):
            movies = [
                {"id": 672, "title": "Harry Potter and the Chamber of Secrets", "media_type": "movie"},
                {"id": 673, "title": "Harry Potter and the Prisoner of Azkaban", "media_type": "movie"},
            ]
            matched = [m for m in movies if m["title"].lower() in query.lower() or query.lower() in m["title"].lower()]
            return matched if matched else movies

    # Pre-populate history with assistant proposal containing italicized titles
    repo.add_chat_message(user_id, "user", "add the 2nd through the end of the harry potter movies")
    repo.add_chat_message(
        user_id,
        "assistant",
        "I can add the remaining movies: 1. *Harry Potter and the Chamber of Secrets* 2. *Harry Potter and the Prisoner of Azkaban*. Say the word!",
        actions=[{"action": "movie_search", "query": "harry potter", "results": [{"title": "Harry Potter and the Chamber of Secrets"}, {"title": "Harry Potter and the Prisoner of Azkaban"}]}]
    )

    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message="yes add those and rate them 4",
        repo=repo,
        tmdb=DummyHpTmdb(),
    )

    actions = res["actions_taken"]
    assert len(actions) > 0
    rated_actions = [a for a in actions if a.get("action") == "rate_movie"]
    assert len(rated_actions) == 2
    assert rated_actions[0]["rating"] == 4
    assert rated_actions[1]["rating"] == 4

    rated_db = repo.list_rated_movies(user_id)
    assert len(rated_db) == 2


@pytest.mark.asyncio
async def test_explicit_title_ignores_previous_history(repo):
    user_id = "test_explicit_ignore_history_user"

    class DummyHpTmdb:
        async def search(self, query):
            assert "harry potter" in query.lower()
            return [
                {"id": 671, "title": "Harry Potter and the Sorcerer's Stone", "media_type": "movie"},
                {"id": 672, "title": "Harry Potter and the Chamber of Secrets", "media_type": "movie"},
                {"id": 673, "title": "Harry Potter and the Prisoner of Azkaban", "media_type": "movie"},
            ]

    # Pre-populate history with unrelated assistant titles (Stuart Fails to Save the Universe, Ted Lasso)
    repo.add_chat_message(user_id, "user", "recommend some sci fi movies")
    repo.add_chat_message(
        user_id,
        "assistant",
        "Here are recommendations: 1. *Stuart Fails to Save the Universe* 2. *Spider-Man: Brand New Day* 3. *Ted Lasso*",
        actions=[{"action": "movie_search", "results": [{"title": "Stuart Fails to Save the Universe"}, {"title": "Spider-Man: Brand New Day"}, {"title": "Ted Lasso"}]}]
    )

    # User asks for explicit title with range + rate clause containing "them"
    res = await AiAgentService.process_chat(
        user_id=user_id,
        user_message="please add the 2nd through the end of the harry potter movies to my rated list and rate them 4",
        repo=repo,
        tmdb=DummyHpTmdb(),
    )

    actions = res["actions_taken"]
    assert len(actions) == 2  # Chamber of Secrets & Prisoner of Azkaban (2nd and 3rd)
    action_titles = [a["title"] for a in actions]
    assert "Stuart Fails to Save the Universe" not in action_titles
    assert "Spider-Man: Brand New Day" not in action_titles
    assert "Harry Potter and the Chamber of Secrets" in action_titles
    assert "Harry Potter and the Prisoner of Azkaban" in action_titles











