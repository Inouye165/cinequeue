import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Depends

from app.auth import get_current_user
from app.services.tmdb import TmdbClient, fetch_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["movies"], dependencies=[Depends(get_current_user)])


@router.get("/search")
async def search(
    request: Request,
    q: str | None = Query(None, min_length=1),
    actor: list[str] | None = Query(None),
    actors: list[str] | None = Query(None),
    director: str | None = Query(None),
    year: int | None = Query(None),
    year_before: int | None = Query(None),
    year_after: int | None = Query(None),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
    media_type: str = Query("all"),
) -> list[dict[str, Any]]:
    tmdb: TmdbClient = request.app.state.tmdb
    all_actors: list[str] = []
    if actor:
        all_actors.extend(actor)
    if actors:
        all_actors.extend(actors)

    has_filters = bool(
        all_actors
        or (director and director.strip())
        or year is not None
        or year_before is not None
        or year_after is not None
        or year_from is not None
        or year_to is not None
        or (media_type and media_type != "all")
    )

    clean_q = q.strip() if q else None

    if not clean_q and not has_filters:
        return []

    logger.info(
        f"Search request - query: '{clean_q}', actors: {all_actors}, director: '{director}', "
        f"year: {year}, year_before: {year_before}, year_after: {year_after}, "
        f"year_from: {year_from}, year_to: {year_to}, media_type: '{media_type}'"
    )

    try:
        if has_filters:
            result = await tmdb.discover(
                query=clean_q,
                actors=all_actors,
                director=director,
                year=year,
                year_before=year_before,
                year_after=year_after,
                year_from=year_from,
                year_to=year_to,
                media_type=media_type,
            )
        else:
            result = await tmdb.search(clean_q or "")
        logger.info(f"Search returned {len(result)} results")
        return result
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise


@router.get("/upcoming")
async def upcoming(request: Request) -> list[dict[str, Any]]:
    logger.info("Upcoming movies request")
    tmdb: TmdbClient = request.app.state.tmdb
    try:
        result = await tmdb.upcoming_movies()
        logger.info(f"Upcoming returned {len(result)} results")
        return result
    except Exception as e:
        logger.error(f"Upcoming movies failed: {e}")
        raise


@router.get("/now-playing")
async def now_playing(request: Request) -> list[dict[str, Any]]:
    logger.info("Now playing request")
    tmdb: TmdbClient = request.app.state.tmdb
    try:
        result = await tmdb.now_playing()
        logger.info(f"Now playing returned {len(result)} results")
        return result
    except Exception as e:
        logger.error(f"Now playing failed: {e}")
        raise


@router.get("/trending")
async def trending(request: Request) -> list[dict[str, Any]]:
    logger.info("Trending request")
    tmdb: TmdbClient = request.app.state.tmdb
    try:
        result = await tmdb.trending()
        logger.info(f"Trending returned {len(result)} results")
        return result
    except Exception as e:
        logger.error(f"Trending failed: {e}")
        raise


@router.get("/on-air")
async def on_air(request: Request) -> list[dict[str, Any]]:
    logger.info("On air TV request")
    tmdb: TmdbClient = request.app.state.tmdb
    try:
        result = await tmdb.on_air_tv()
        logger.info(f"On air TV returned {len(result)} results")
        return result
    except Exception as e:
        logger.error(f"On air TV failed: {e}")
        raise


@router.get("/{media_type}/{tmdb_id}")
async def media_details(
    media_type: str,
    tmdb_id: int,
    request: Request,
    current_user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    logger.info(f"Media details request: {media_type}/{tmdb_id}")
    if media_type not in {"movie", "tv"}:
        logger.warning(f"Invalid media_type: {media_type}")
        raise HTTPException(status_code=400, detail="media_type must be movie or tv")
    tmdb: TmdbClient = request.app.state.tmdb
    try:
        details = await tmdb.get_details(media_type, tmdb_id)
        
        next_season = None
        if media_type == "tv" and details.get("seasons"):
            next_season = tmdb.get_next_season(details["seasons"])

        # Prepare cast changes task if tv and has next_season
        cast_changes_task = None
        if media_type == "tv" and next_season:
            cast_changes_task = tmdb.get_season_cast_changes(tmdb_id, next_season["season_number"])
        else:
            async def get_none():
                return None
            cast_changes_task = get_none()

        # Concurrently fetch other details
        providers, reviews, release_info, news, trailers, cast_changes = await asyncio.gather(
            tmdb.get_watch_providers(media_type, tmdb_id),
            tmdb.get_reviews(media_type, tmdb_id),
            tmdb.get_release_info(media_type, tmdb_id),
            fetch_news(details["title"]),
            tmdb.get_videos(media_type, tmdb_id),
            cast_changes_task,
        )

        user_rating = None
        repo = getattr(request.app.state, "watchlist_repo", None)
        if repo and current_user:
            try:
                user_id = getattr(current_user, "uid", str(current_user))
                rated_list = repo.list_rated_movies(user_id)
                match_r = next((r for r in rated_list if r.get("media_type") == media_type and r.get("tmdb_id") == tmdb_id), None)
                if match_r:
                    user_rating = match_r.get("rating")
                else:
                    w_item = repo.get_item(user_id, media_type, tmdb_id)
                    if w_item and w_item.get("user_rating"):
                        user_rating = w_item.get("user_rating")
            except Exception as e:
                logger.warning(f"Could not retrieve user rating for {media_type}/{tmdb_id}: {e}")

        logger.info(f"Media details retrieved successfully for {media_type}/{tmdb_id}")
        return {
            **details,
            "watch_providers": providers,
            "reviews": reviews,
            "release_info": release_info,
            "news": news,
            "trailers": trailers,
            "next_season": next_season,
            "cast_changes": cast_changes,
            "user_rating": user_rating,
        }
    except Exception as e:
        logger.error(f"Media details failed for {media_type}/{tmdb_id}: {e}")
        raise
