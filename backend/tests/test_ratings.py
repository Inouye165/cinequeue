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
async def test_agent_chat_quiz_and_ratings_intents(repo):
    user_id = "test_user_intents"

    # 1. Ask for quiz
    res_quiz = await AiAgentService.process_chat(user_id, "quiz me on 5 movies", repo, None)
    actions = res_quiz.get("actions_taken", [])
    assert any(a.get("action") == "movie_quiz" for a in actions)
    assert len(actions[0]["movies"]) == 5

    # 2. Ask for ratings (initially empty)
    res_ratings_empty = await AiAgentService.process_chat(user_id, "what movies have I rated?", repo, None)
    assert "haven't rated" in res_ratings_empty["message"]["content"].lower()

    # 3. Rate a movie then ask for ratings
    repo.rate_movie(user_id, "movie", 155, "The Dark Knight", "/poster.jpg", "2008-07-16", 5)
    res_ratings = await AiAgentService.process_chat(user_id, "show my ratings", repo, None)
    assert "The Dark Knight" in res_ratings["message"]["content"]
    assert "5/5" in res_ratings["message"]["content"]
