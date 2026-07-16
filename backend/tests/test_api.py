import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_tmdb():
    """Mock TMDB client for testing."""
    tmdb = AsyncMock()
    tmdb.search.return_value = [
        {
            "id": 1,
            "media_type": "movie",
            "title": "Test Movie",
            "poster_url": "http://example.com/poster.jpg",
            "release_date": "2024-01-01",
            "days_away": 100,
            "days_label": "100 days away",
            "vote_average": 8.0,
            "popularity": 100.0,
        }
    ]
    tmdb.upcoming_movies.return_value = []
    tmdb.now_playing.return_value = []
    tmdb.trending.return_value = []
    tmdb.on_air_tv.return_value = []
    tmdb.get_details.return_value = {
        "id": 1,
        "media_type": "movie",
        "title": "Test Movie",
        "overview": "Test overview",
        "poster_url": "http://example.com/poster.jpg",
        "backdrop_url": "http://example.com/backdrop.jpg",
        "release_date": "2024-01-01",
        "days_away": 100,
        "days_label": "100 days away",
        "vote_average": 8.0,
        "vote_count": 100,
        "genres": ["Action"],
        "runtime_minutes": 120,
        "status": "Released",
        "homepage": "http://example.com",
    }
    tmdb.get_watch_providers.return_value = {
        "link": "http://example.com/watch",
        "categories": {
            "streaming": [{"name": "Netflix", "logo_url": "http://example.com/netflix.png"}],
            "rent": [],
            "buy": [],
        },
    }
    tmdb.get_reviews.return_value = []
    tmdb.get_videos.return_value = [{"key": "abc", "name": "Official Trailer"}]
    tmdb.get_release_info.return_value = {
        "theatrical": "2024-01-01",
        "digital": "2024-01-15",
        "theatrical_days_away": 100,
        "digital_days_away": 115,
    }
    return tmdb


@pytest.fixture
def app_with_mock(mock_tmdb):
    """Create app with mocked TMDB client."""
    from app.main import app
    app.state.tmdb = mock_tmdb
    return app


def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_search_endpoint(client, app_with_mock):
    """Test the search endpoint."""
    response = client.get("/api/search?q=test")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["title"] == "Test Movie"


def test_search_empty_query(client):
    """Test search endpoint with empty query (should fail validation)."""
    response = client.get("/api/search?q=")
    assert response.status_code == 422


def test_upcoming_endpoint(client, app_with_mock):
    """Test the upcoming movies endpoint."""
    response = client.get("/api/upcoming")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_now_playing_endpoint(client, app_with_mock):
    """Test the now playing endpoint."""
    response = client.get("/api/now-playing")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_trending_endpoint(client, app_with_mock):
    """Test the trending endpoint."""
    response = client.get("/api/trending")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_on_air_endpoint(client, app_with_mock):
    """Test the on air TV endpoint."""
    response = client.get("/api/on-air")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_media_details_endpoint(client, app_with_mock):
    """Test the media details endpoint."""
    response = client.get("/api/movie/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Test Movie"
    assert "watch_providers" in data
    assert "reviews" in data
    assert "release_info" in data
    assert "news" in data
    assert "trailers" in data


def test_media_details_invalid_type(client, app_with_mock):
    """Test media details endpoint with invalid media type."""
    response = client.get("/api/invalid/1")
    assert response.status_code == 400


def test_watchlist_list_empty(client, app_with_mock):
    """Test listing an empty watchlist."""
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_watchlist_concurrency(client, app_with_mock):
    """Test that TMDB details are fetched concurrently."""
    import asyncio
    import time

    # First, add a few items to the watchlist
    client.post(
        "/api/watchlist",
        json={"media_type": "movie", "tmdb_id": 101, "title": "Movie 1"}
    )
    client.post(
        "/api/watchlist",
        json={"media_type": "movie", "tmdb_id": 102, "title": "Movie 2"}
    )
    client.post(
        "/api/watchlist",
        json={"media_type": "movie", "tmdb_id": 103, "title": "Movie 3"}
    )

    # We mock tmdb.get_details with an async function that sleeps for 0.1s
    async def slow_get_details(media_type, tmdb_id):
        await asyncio.sleep(0.1)
        return {
            "id": tmdb_id,
            "media_type": media_type,
            "title": f"Movie {tmdb_id}",
            "overview": "Slow details"
        }
    
    app_with_mock.state.tmdb.get_details = slow_get_details

    # Call the watchlist endpoint and measure the time
    start_time = time.perf_counter()
    response = client.get("/api/watchlist")
    end_time = time.perf_counter()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    duration = end_time - start_time
    # If requests were sequential, 3 items * 0.1s would take >= 0.3s.
    # If they are concurrent, it should take around 0.1s (definitely < 0.25s).
    assert duration < 0.25, f"Expected concurrency, but took {duration:.3f}s"


def test_watchlist_graceful_error_handling(client, app_with_mock):
    """Test that a failed TMDB API request does not crash the entire list."""
    client.post(
        "/api/watchlist",
        json={"media_type": "movie", "tmdb_id": 201, "title": "Movie Good", "release_date": "2024-01-01"}
    )
    client.post(
        "/api/watchlist",
        json={"media_type": "movie", "tmdb_id": 202, "title": "Movie Bad", "release_date": "2024-01-01"}
    )

    async def mock_get_details(media_type, tmdb_id):
        if tmdb_id == 202:
            raise Exception("TMDB connection failure")
        return {
            "id": tmdb_id,
            "media_type": media_type,
            "title": f"Movie {tmdb_id}",
            "overview": "Success details"
        }
    
    app_with_mock.state.tmdb.get_details = mock_get_details

    response = client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    # Verify the successful item has details
    good_item = next(item for item in data if item["tmdb_id"] == 201)
    assert good_item["overview"] == "Success details"
    
    # Verify the failed item has fallback default values (partial object)
    bad_item = next(item for item in data if item["tmdb_id"] == 202)
    assert "overview" not in bad_item
    assert "vote_average" not in bad_item
    assert "media_status" not in bad_item
    assert bad_item["days_away"] is not None




def test_watchlist_add(client, app_with_mock):
    """Test adding an item to the watchlist."""
    response = client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 123,
            "title": "Test Movie",
            "poster_path": "/poster.jpg",
            "release_date": "2024-01-01",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tmdb_id"] == 123
    assert data["title"] == "Test Movie"


def test_watchlist_add_invalid(client, app_with_mock):
    """Test adding an invalid item to the watchlist."""
    response = client.post(
        "/api/watchlist",
        json={
            "media_type": "invalid",
            "tmdb_id": 123,
            "title": "Test",
        },
    )
    assert response.status_code == 400


def test_watchlist_add_missing_fields(client, app_with_mock):
    """Test adding an item with missing required fields."""
    response = client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 123,
        },
    )
    assert response.status_code == 400


def test_watchlist_remove(client, app_with_mock):
    """Test removing an item from the watchlist."""
    # First add an item
    client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 456,
            "title": "Test Movie",
            "poster_path": "/poster.jpg",
            "release_date": "2024-01-01",
        },
    )
    
    # Then remove it
    response = client.delete("/api/watchlist/movie/456")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "removed"


def test_watchlist_remove_not_found(client, app_with_mock):
    """Test removing a non-existent item."""
    response = client.delete("/api/watchlist/movie/999")
    assert response.status_code == 404


def test_watchlist_remove_invalid_type(client, app_with_mock):
    """Test removing with invalid media type."""
    response = client.delete("/api/watchlist/invalid/123")
    assert response.status_code == 400


def test_watchlist_add_owned(client, app_with_mock):
    """Test adding an owned item to the watchlist/library."""
    response = client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 789,
            "title": "Owned Movie",
            "is_owned": True,
            "owned_format": "hard_copy"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_owned"] is True
    assert data["owned_format"] == "hard_copy"


def test_watchlist_patch_owned(client, app_with_mock):
    """Test updating ownership status and format of a watchlist item."""
    # First, add a regular movie to watchlist
    client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 888,
            "title": "Regular Movie"
        }
    )

    # Now patch it to be owned (electronic format)
    response = client.patch(
        "/api/watchlist/movie/888",
        json={
            "is_owned": True,
            "owned_format": "electronic"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["is_owned"] is True
    assert data["owned_format"] == "electronic"

    # Now update format to hard_copy
    response = client.patch(
        "/api/watchlist/movie/888",
        json={
            "is_owned": True,
            "owned_format": "hard_copy"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_owned"] is True
    assert data["owned_format"] == "hard_copy"

    # Now make it unowned (should clear format to None)
    response = client.patch(
        "/api/watchlist/movie/888",
        json={
            "is_owned": False,
            "owned_format": None
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_owned"] is False
    assert data["owned_format"] is None


def test_watchlist_patch_invalid_format(client, app_with_mock):
    """Test patching with an invalid owned_format validation."""
    client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 889,
            "title": "Another Movie"
        }
    )

    response = client.patch(
        "/api/watchlist/movie/889",
        json={
            "is_owned": True,
            "owned_format": "invalid_format_name"
        }
    )
    assert response.status_code == 400


def test_watchlist_patch_not_found(client, app_with_mock):
    """Test patching an item that doesn't exist."""
    response = client.patch(
        "/api/watchlist/movie/99999",
        json={
            "is_owned": True,
            "owned_format": "electronic"
        }
    )
    assert response.status_code == 404


def test_watchlist_add_status(client, app_with_mock):
    """Test adding an item with custom status."""
    response = client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 901,
            "title": "Following Movie",
            "status": "following"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "following"


def test_watchlist_patch_status(client, app_with_mock):
    """Test patching custom status of an item."""
    client.post(
        "/api/watchlist",
        json={
            "media_type": "movie",
            "tmdb_id": 902,
            "title": "Queue Movie",
            "status": "queue"
        }
    )
    
    response = client.patch(
        "/api/watchlist/movie/902",
        json={
            "status": "following"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status_value"] == "following"


