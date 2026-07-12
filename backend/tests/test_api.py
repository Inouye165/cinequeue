import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app


@pytest.fixture
def client():
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
