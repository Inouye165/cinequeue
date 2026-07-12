import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.tmdb import TmdbClient, fetch_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["movies"])


@router.get("/search")
async def search(request: Request, q: str = Query(min_length=1)) -> list[dict[str, Any]]:
    logger.info(f"Search request for query: {q}")
    tmdb: TmdbClient = request.app.state.tmdb
    try:
        result = await tmdb.search(q)
        logger.info(f"Search returned {len(result)} results")
        return result
    except Exception as e:
        logger.error(f"Search failed for query '{q}': {e}")
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
async def media_details(media_type: str, tmdb_id: int, request: Request) -> dict[str, Any]:
    logger.info(f"Media details request: {media_type}/{tmdb_id}")
    if media_type not in {"movie", "tv"}:
        logger.warning(f"Invalid media_type: {media_type}")
        raise HTTPException(status_code=400, detail="media_type must be movie or tv")
    tmdb: TmdbClient = request.app.state.tmdb
    try:
        details = await tmdb.get_details(media_type, tmdb_id)
        providers = await tmdb.get_watch_providers(media_type, tmdb_id)
        reviews = await tmdb.get_reviews(media_type, tmdb_id)
        release_info = await tmdb.get_release_info(media_type, tmdb_id)
        news = await fetch_news(details["title"])
        logger.info(f"Media details retrieved successfully for {media_type}/{tmdb_id}")
        return {
            **details,
            "watch_providers": providers,
            "reviews": reviews,
            "release_info": release_info,
            "news": news,
        }
    except Exception as e:
        logger.error(f"Media details failed for {media_type}/{tmdb_id}: {e}")
        raise
