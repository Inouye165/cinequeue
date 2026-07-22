from datetime import date
import asyncio
import logging
import re
from typing import Any


import feedparser
import httpx

from app.config import TMDB_API_KEY, TMDB_BASE_URL, TMDB_IMAGE_BASE
from app.models import days_label, days_until, enrich_media_item, poster_url

logger = logging.getLogger(__name__)



class TmdbClient:
    def __init__(self) -> None:
        if not TMDB_API_KEY:
            raise RuntimeError("TMDB_API_KEY is not set")
        self._client = httpx.AsyncClient(
            base_url=TMDB_BASE_URL,
            params={"api_key": TMDB_API_KEY},
            timeout=20.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> Any:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def search(self, query: str) -> list[dict[str, Any]]:
        movie_data = await self._get("/search/movie", query=query)
        tv_data = await self._get("/search/tv", query=query)
        results: list[dict[str, Any]] = []
        for item in movie_data.get("results", [])[:8]:
            results.append(enrich_media_item(item, "movie"))
        for item in tv_data.get("results", [])[:8]:
            results.append(enrich_media_item(item, "tv"))
        results.sort(key=lambda x: x.get("popularity") or 0, reverse=True)
        return results[:12]

    async def upcoming_movies(self) -> list[dict[str, Any]]:
        data = await self._get("/movie/upcoming", region="US")
        return [enrich_media_item(item, "movie") for item in data.get("results", [])]

    async def now_playing(self) -> list[dict[str, Any]]:
        data = await self._get("/movie/now_playing", region="US")
        return [enrich_media_item(item, "movie") for item in data.get("results", [])]

    async def trending(self) -> list[dict[str, Any]]:
        data = await self._get("/trending/all/week")
        results = []
        for item in data.get("results", []):
            media_type = item.get("media_type")
            if media_type in {"movie", "tv"}:
                results.append(enrich_media_item(item, media_type))
        return results

    async def on_air_tv(self) -> list[dict[str, Any]]:
        data = await self._get("/tv/on_the_air")
        return [enrich_media_item(item, "tv") for item in data.get("results", [])]

    async def get_details(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        data = await self._get(f"/{media_type}/{tmdb_id}")
        release = data.get("release_date") or data.get("first_air_date")
        days = days_until(release)
        genres = [g["name"] for g in data.get("genres", [])]
        runtime = data.get("runtime")
        if not runtime and data.get("episode_run_time"):
            runtime = data["episode_run_time"][0] if data["episode_run_time"] else None

        return {
            "id": data["id"],
            "media_type": media_type,
            "title": data.get("title") or data.get("name"),
            "overview": data.get("overview", ""),
            "tagline": data.get("tagline", ""),
            "poster_url": poster_url(data.get("poster_path")),
            "backdrop_url": poster_url(data.get("backdrop_path"), "w1280"),
            "release_date": release,
            "days_away": days,
            "days_label": days_label(days),
            "vote_average": data.get("vote_average"),
            "vote_count": data.get("vote_count"),
            "genres": genres,
            "runtime_minutes": runtime,
            "status": data.get("status"),
            "homepage": data.get("homepage"),
            "seasons": data.get("seasons") if media_type == "tv" else None,
        }

    async def get_recommendations(self, media_type: str, tmdb_id: int) -> list[dict[str, Any]]:
        """Fetch recommended/similar titles for a given movie or show."""
        try:
            data = await self._get(f"/{media_type}/{tmdb_id}/recommendations")
            results = data.get("results", [])
            if not results:
                data = await self._get(f"/{media_type}/{tmdb_id}/similar")
                results = data.get("results", [])
            return [enrich_media_item(item, media_type) for item in results[:5]]
        except Exception as e:
            logger.warning(f"Error fetching recommendations for {media_type}/{tmdb_id}: {e}")
            return []

    def get_next_season(self, seasons: list[dict[str, Any]]) -> dict[str, Any] | None:

        if not seasons:
            return None
        valid_seasons = [
            s for s in seasons
            if s.get("season_number", 0) > 0 and s.get("air_date")
        ]
        if not valid_seasons:
            return None

        # Sort by air_date to find chronological order
        valid_seasons.sort(key=lambda s: s["air_date"])

        today_str = date.today().isoformat()
        upcoming = [s for s in valid_seasons if s["air_date"] >= today_str]
        if upcoming:
            target_season = upcoming[0]
        else:
            # If no upcoming season, use the latest season by season number
            valid_seasons.sort(key=lambda s: s["season_number"])
            target_season = valid_seasons[-1] if len(valid_seasons) > 1 else None

        if not target_season:
            return None

        s_air_date = target_season.get("air_date")
        days = days_until(s_air_date)
        return {
            "name": target_season.get("name"),
            "season_number": target_season.get("season_number"),
            "air_date": s_air_date,
            "days_away": days,
            "days_label": days_label(days),
        }

    async def get_season_cast_changes(
        self, series_id: int, next_season_number: int
    ) -> dict[str, Any] | None:
        if next_season_number <= 1:
            return None

        prev_season_number = next_season_number - 1

        try:
            prev_credits, next_credits = await asyncio.gather(
                self._get(f"/tv/{series_id}/season/{prev_season_number}/credits"),
                self._get(f"/tv/{series_id}/season/{next_season_number}/credits")
            )
        except Exception as e:
            logger.warning(f"Failed to fetch credits for comparison: {e}")
            return None

        prev_cast = prev_credits.get("cast", [])
        next_cast = next_credits.get("cast", [])

        def normalize_char(name: str) -> str:
            if not name:
                return ""
            name = re.sub(r'\(.*?\)', '', name)
            name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
            return name.lower().strip()

        main_prev_cast = [c for c in prev_cast if c.get("order", 99) < 15]

        returning_with_new_actors = []
        written_out = []

        next_cast_map = {}
        for c in next_cast:
            char_norm = normalize_char(c.get("character", ""))
            if char_norm:
                if char_norm not in next_cast_map or c.get("order", 99) < next_cast_map[char_norm].get("order", 99):
                    next_cast_map[char_norm] = c

        for member in main_prev_cast:
            char_name = member.get("character", "")
            actor_name = member.get("name", "")
            actor_id = member.get("id")

            char_norm = normalize_char(char_name)
            if not char_norm:
                continue

            if char_norm in next_cast_map:
                next_member = next_cast_map[char_norm]
                next_actor_id = next_member.get("id")
                next_actor_name = next_member.get("name", "")
                if next_actor_id != actor_id:
                    returning_with_new_actors.append({
                        "character": char_name,
                        "old_actor": actor_name,
                        "new_actor": next_actor_name
                    })
            else:
                written_out.append({
                    "character": char_name,
                    "actor": actor_name
                })

        return {
            "prev_season": prev_season_number,
            "next_season": next_season_number,
            "returning_with_new_actors": returning_with_new_actors,
            "written_out": written_out
        }


    async def get_watch_providers(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        data = await self._get(f"/{media_type}/{tmdb_id}/watch/providers")
        us = data.get("results", {}).get("US", {})
        free_list = us.get("free", []) + us.get("ads", [])
        
        categories = {
            "streaming": _format_providers(us.get("flatrate", [])),
            "free": _format_providers(free_list),
            "rent": _format_providers(us.get("rent", [])),
            "buy": _format_providers(us.get("buy", [])),
        }
        
        # Calculate flags
        is_free_streaming = len(categories["streaming"]) > 0 or len(categories["free"]) > 0
        
        # Simulated buy pricing
        has_buy_options = len(categories["buy"]) > 0
        is_sale = False
        original_price = 0.0
        current_price = 0.0
        
        if has_buy_options:
            # Deterministic pricing based on tmdb_id
            state = (tmdb_id * 31) % 100
            is_sale = state < 35  # 35% chance of being on sale
            original_price = 14.99 if state % 2 == 0 else 19.99
            if is_sale:
                current_price = 4.99 if state % 3 == 0 else 7.99 if state % 3 == 1 else 9.99
            else:
                current_price = original_price
            
            # Enrich buy providers with prices
            enriched_buy = []
            for provider in categories["buy"]:
                enriched_buy.append({
                    **provider,
                    "current_price": f"${current_price:.2f}",
                    "original_price": f"${original_price:.2f}",
                    "is_on_sale": is_sale,
                })
            categories["buy"] = enriched_buy
            
        link = us.get("link")
        in_theatres = media_type == "movie" and await self._is_in_theatres(tmdb_id)
        if in_theatres:
            categories["theatres"] = [{"name": "In theatres now", "logo_url": None}]
            
        return {
            "link": link,
            "categories": categories,
            "is_free_streaming": is_free_streaming,
            "is_on_sale": has_buy_options and is_sale,
            "buy_original_price": f"${original_price:.2f}" if has_buy_options else None,
            "buy_current_price": f"${current_price:.2f}" if has_buy_options else None,
        }

    async def get_videos(self, media_type: str, tmdb_id: int) -> list[dict[str, Any]]:
        try:
            data = await self._get(f"/{media_type}/{tmdb_id}/videos")
            results = data.get("results", [])
            official_trailers = []
            for v in results:
                if (
                    v.get("site") == "YouTube"
                    and v.get("type") == "Trailer"
                    and v.get("official") is True
                ):
                    official_trailers.append(
                        {
                            "key": v.get("key"),
                            "name": v.get("name"),
                        }
                    )
            return official_trailers
        except Exception:
            return []

    async def _is_in_theatres(self, tmdb_id: int) -> bool:
        now_playing = await self.now_playing()
        return any(item["id"] == tmdb_id for item in now_playing)

    async def get_reviews(self, media_type: str, tmdb_id: int) -> list[dict[str, Any]]:
        data = await self._get(f"/{media_type}/{tmdb_id}/reviews")
        reviews = []
        for review in data.get("results", [])[:8]:
            reviews.append(
                {
                    "author": review.get("author", "Anonymous"),
                    "rating": review.get("author_details", {}).get("rating"),
                    "content": review.get("content", ""),
                    "url": review.get("url"),
                    "created_at": review.get("created_at"),
                }
            )
        return reviews

    async def get_release_info(self, media_type: str, tmdb_id: int) -> dict[str, Any]:
        if media_type == "movie":
            data = await self._get(f"/movie/{tmdb_id}/release_dates")
            theatrical = None
            digital = None
            for entry in data.get("results", []):
                if entry.get("iso_3166_1") != "US":
                    continue
                for release in entry.get("release_dates", []):
                    release_type = release.get("type")
                    date_value = release.get("release_date", "")[:10]
                    if release_type == 3 and not theatrical:
                        theatrical = date_value
                    if release_type in {4, 5} and not digital:
                        digital = date_value
            return {
                "theatrical": theatrical,
                "digital": digital,
                "theatrical_days_away": days_until(theatrical),
                "digital_days_away": days_until(digital),
            }
        data = await self._get(f"/tv/{tmdb_id}")
        next_episode = data.get("next_episode_to_air")
        if not next_episode:
            return {"next_episode": None}
        air_date = next_episode.get("air_date")
        return {
            "next_episode": {
                "name": next_episode.get("name"),
                "season": next_episode.get("season_number"),
                "episode": next_episode.get("episode_number"),
                "air_date": air_date,
                "days_away": days_until(air_date),
                "days_label": days_label(days_until(air_date)),
            }
        }


def _format_providers(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted = []
    seen = set()
    for provider in providers:
        name = provider.get("provider_name")
        if not name or name in seen:
            continue
        seen.add(name)
        logo_path = provider.get("logo_path")
        formatted.append(
            {
                "name": name,
                "logo_url": f"{TMDB_IMAGE_BASE}/w45{logo_path}" if logo_path else None,
            }
        )
    return formatted


async def fetch_news(title: str, limit: int = 6) -> list[dict[str, Any]]:
    from urllib.parse import quote_plus

    query = quote_plus(f"{title} movie OR show")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    async with httpx.AsyncClient(timeout=15.0) as client:
        feed = await client.get(url)
        feed.raise_for_status()
        parsed = feedparser.parse(feed.text)
    articles = []
    for entry in parsed.entries[:limit]:
        articles.append(
            {
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": entry.get("source", {}).get("title") if entry.get("source") else None,
            }
        )
    return articles
