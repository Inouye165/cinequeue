import pytest
from unittest.mock import AsyncMock, patch
from app.services.tmdb import TmdbClient


@pytest.fixture
def tmdb_client():
    with patch.dict("os.environ", {"TMDB_API_KEY": "test_key"}):
        client = TmdbClient()
        return client


@pytest.mark.asyncio
async def test_search_person(tmdb_client):
    mock_get = AsyncMock(return_value={
        "results": [
            {"id": 101, "name": "Tom Hanks", "popularity": 45.0},
            {"id": 102, "name": "Tom Hanks Lookalike", "popularity": 2.0},
        ]
    })
    tmdb_client._get = mock_get

    person = await tmdb_client.search_person("Tom Hanks")
    assert person is not None
    assert person["id"] == 101
    assert person["name"] == "Tom Hanks"

    # Verify cached on second call
    person2 = await tmdb_client.search_person("tom hanks")
    assert person2["id"] == 101
    assert mock_get.call_count == 1


@pytest.mark.asyncio
async def test_discover_actors_and_director_and_years(tmdb_client):
    async def mock_get(path, **params):
        if path == "/search/person":
            q = params.get("query", "").lower()
            if "hanks" in q:
                return {"results": [{"id": 31, "name": "Tom Hanks", "popularity": 50.0}]}
            if "ryan" in q:
                return {"results": [{"id": 2157, "name": "Meg Ryan", "popularity": 30.0}]}
            if "nolan" in q:
                return {"results": [{"id": 525, "name": "Christopher Nolan", "popularity": 40.0}]}
            return {"results": []}
        elif "/combined_credits" in path:
            return {
                "cast": [
                    {
                        "id": 999,
                        "title": "Sleepless in Seattle",
                        "release_date": "1993-06-25",
                        "popularity": 80.0,
                        "media_type": "movie",
                    }
                ],
                "crew": [
                    {
                        "id": 999,
                        "title": "Sleepless in Seattle",
                        "release_date": "1993-06-25",
                        "popularity": 80.0,
                        "media_type": "movie",
                        "job": "Director",
                    }
                ],
            }
        elif path == "/discover/movie":
            return {
                "results": [
                    {
                        "id": 999,
                        "title": "Sleepless in Seattle",
                        "release_date": "1993-06-25",
                        "popularity": 80.0,
                    }
                ]
            }
        elif path == "/discover/tv":
            return {"results": []}
        return {}

    tmdb_client._get = mock_get

    results = await tmdb_client.discover(
        actors=["Tom Hanks", "Meg Ryan"],
        director="Christopher Nolan",
        year_from=1990,
        year_to=2000,
        media_type="movie",
    )

    assert len(results) == 1
    assert results[0]["id"] == 999
    assert results[0]["title"] == "Sleepless in Seattle"
