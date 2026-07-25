import pytest
from app.sqlite_repo import SqliteWatchlistRepository
from app.services.agent_service import AiAgentService


@pytest.fixture
def repo(tmp_path, monkeypatch):
    db_file = tmp_path / "test_ratings_watchlist.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repository = SqliteWatchlistRepository()
    yield repository
    repository.clear_all("test_user_ratings")


def test_rate_movie_crud_and_time_ago(repo):
    user_id = "test_user_ratings"

    # Initially empty
    rated = repo.list_rated_movies(user_id)
    assert len(rated) == 0

    # Rate a movie (5 stars)
    res = repo.rate_movie(
        user_id=user_id,
        media_type="movie",
        tmdb_id=27205,
        title="Inception",
        poster_path="/oYuLEW9W2vBBGLB2JSXA3iYj6i7.jpg",
        release_date="2010-07-16",
        rating=5,
    )
    assert res["rating"] == 5
    assert res["title"] == "Inception"
    assert res["rated_ago"] == "just now"

    # List rated movies
    list_after = repo.list_rated_movies(user_id)
    assert len(list_after) == 1
    assert list_after[0]["tmdb_id"] == 27205
    assert list_after[0]["rating"] == 5

    # Update rating (4 stars)
    updated = repo.rate_movie(
        user_id=user_id,
        media_type="movie",
        tmdb_id=27205,
        title="Inception",
        poster_path="/oYuLEW9W2vBBGLB2JSXA3iYj6i7.jpg",
        release_date="2010-07-16",
        rating=4,
    )
    assert updated["rating"] == 4

    # Delete rating
    deleted = repo.delete_rated_movie(user_id, "movie", 27205)
    assert deleted is True

    list_final = repo.list_rated_movies(user_id)
    assert len(list_final) == 0


@pytest.mark.asyncio
async def test_generate_movie_quiz(repo):
    user_id = "test_user_quiz"
    quiz = await AiAgentService.generate_movie_quiz(user_id, repo, None)
    assert len(quiz) == 5
    assert all("tmdb_id" in m and "title" in m for m in quiz)


@pytest.mark.asyncio
async def test_agent_chat_quiz_and_ratings_intents(repo, monkeypatch):
    user_id = "test_user_intents"

    # Mock _call_gemini_api to return expected chat answers dynamically
    from app.services.agent_service import AgentResult

    async def mock_gemini_chat(*args, **kwargs):
        msg = kwargs.get("user_message") or kwargs.get("prompt") or (args[0] if args else "")
        if "rated" in str(msg).lower() or "ratings" in str(msg).lower():
            rated_movies = repo.list_rated_movies(user_id)
            if not rated_movies:
                text = "You haven't logged ratings for any movies yet."
            else:
                lines = [f"• {m['title']} - {m['rating']}/5 stars" for m in rated_movies]
                text = "Here are your logged movie ratings:\n" + "\n".join(lines)
        else:
            text = "Here is a movie quiz for you!"

        return AgentResult(
            text=text,
            provider="gemini",
            model_requested="gemini-2.5-flash",
            model_used="gemini-2.5-flash",
            gemini_called=True,
            fallback_used=False,
            fallback_reason=None,
            http_status=200,
            request_duration_ms=50.0,
            actions_taken=[],
        )

    monkeypatch.setattr(AiAgentService, "_call_gemini_api", mock_gemini_chat)

    # 1. Ask for quiz
    res_quiz = await AiAgentService.process_chat(user_id, "quiz me on 5 movies", repo, None)
    actions = res_quiz.get("actions_taken", [])
    assert any(a.get("action") == "movie_quiz" for a in actions)
    assert len(actions[0]["movies"]) == 5

    res_ratings_empty = await AiAgentService.process_chat(user_id, "what movies have I rated?", repo, None)
    assert any(phrase in res_ratings_empty["message"]["content"].lower() for phrase in ["haven't rated", "haven't logged ratings", "clear right now", "no rated movies"])

    repo.rate_movie(user_id, "movie", 155, "The Dark Knight", "/poster.jpg", "2008-07-16", 5)
    res_ratings = await AiAgentService.process_chat(user_id, "show my ratings", repo, None)
    assert "The Dark Knight" in res_ratings["message"]["content"]
    assert any(p in res_ratings["message"]["content"].lower() for p in ["5/5", "5 out of 5", "5 star"])


def test_delete_rating_and_readd_to_queue(repo):
    user_id = "test_readd_user"

    # 1. Rate a movie
    repo.rate_movie(user_id, "movie", 672, "Harry Potter and the Chamber of Secrets", "/poster.jpg", "2002-11-15", 4)
    rated_movies = repo.list_rated_movies(user_id)
    assert len(rated_movies) == 1

    # 2. Delete rating
    deleted = repo.delete_rated_movie(user_id, "movie", 672)
    assert deleted is True
    assert len(repo.list_rated_movies(user_id)) == 0

    # 3. Add back to queue (should succeed without DuplicateItemError)
    added = repo.add_item(user_id, "movie", 672, "Harry Potter and the Chamber of Secrets", "/poster.jpg", "2002-11-15", status="queue")
    assert added["status"] == "queue"

    items = repo.list_items(user_id)
    assert len(items) == 1
    assert items[0]["status"] == "queue"


def test_firestore_rate_movie_crud_and_fallback(monkeypatch):
    from unittest.mock import MagicMock
    from app.firestore_repo import FirestoreWatchlistRepository

    mock_db = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {
        "user_id": "fs_user",
        "media_type": "movie",
        "tmdb_id": 27205,
        "title": "Inception",
        "rating": 5,
        "updated_at": "2026-07-24T12:00:00+00:00",
    }
    mock_col = MagicMock()
    mock_col.order_by.side_effect = Exception("Missing index")
    mock_col.stream.return_value = [mock_doc]
    mock_db.collection.return_value.document.return_value.collection.return_value = mock_col

    monkeypatch.setattr("google.cloud.firestore.Client", lambda project=None: mock_db)
    fs_repo = FirestoreWatchlistRepository()

    rated = fs_repo.list_rated_movies("fs_user")
    assert len(rated) == 1
    assert rated[0]["title"] == "Inception"
    assert rated[0]["rating"] == 5
