import pytest
from unittest.mock import AsyncMock

def test_watchlist_enrichment_includes_release_info(client):
    from app.main import app

    mock_tmdb = AsyncMock()
    mock_tmdb.get_details.return_value = {
        "id": 550,
        "media_type": "movie",
        "title": "Fight Club",
        "overview": "An insomniac office worker...",
        "poster_url": "http://example.com/poster.jpg",
        "release_date": "1999-10-15",
        "vote_average": 8.4,
    }
    mock_tmdb.get_watch_providers.return_value = {
        "is_free_streaming": True,
        "is_on_sale": False,
        "categories": {
            "streaming": [{"name": "Hulu"}],
            "rent": [{"name": "Amazon"}],
            "buy": [{"name": "Apple TV"}],
        },
    }
    mock_tmdb.get_release_info.return_value = {
        "theatrical": "1999-10-15",
        "digital": "2000-03-01",
        "theatrical_days_away": -9500,
        "digital_days_away": -9300,
    }

    app.state.tmdb = mock_tmdb

    # Add item to watchlist
    add_resp = client.post(
        "/api/watchlist",
        json={"media_type": "movie", "tmdb_id": 550, "title": "Fight Club"},
    )
    assert add_resp.status_code == 200

    # List watchlist items
    list_resp = client.get("/api/watchlist")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) > 0
    item = next((i for i in items if i["tmdb_id"] == 550), None)
    assert item is not None
    assert "release_info" in item
    assert item["release_info"]["theatrical"] == "1999-10-15"
    assert item["release_info"]["digital"] == "2000-03-01"
    assert item["theatrical_release_date"] == "1999-10-15"
    assert item["digital_release_date"] == "2000-03-01"
    assert "watch_providers" in item

