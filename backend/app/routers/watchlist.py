import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.database import get_connection, row_to_dict, utc_now_iso
from app.models import days_label, days_until, poster_url
from app.services.tmdb import TmdbClient, fetch_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("")
async def list_watchlist(request: Request) -> list[dict[str, Any]]:
    logger.info("List watchlist request")
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist ORDER BY added_at DESC"
            ).fetchall()

        tmdb: TmdbClient = request.app.state.tmdb
        items = []
        for row in rows:
            item = row_to_dict(row)
            try:
                details = await tmdb.get_details(item["media_type"], item["tmdb_id"])
                item.update(
                    {
                        "overview": details.get("overview", ""),
                        "vote_average": details.get("vote_average"),
                        "status": details.get("status"),
                        "release_date": details.get("release_date") or item.get("release_date"),
                        "poster_url": details.get("poster_url") or poster_url(item.get("poster_path")),
                        "days_away": details.get("days_away"),
                        "days_label": details.get("days_label"),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to fetch details for {item['media_type']}/{item['tmdb_id']}: {e}")
                days = days_until(item.get("release_date"))
                item["days_away"] = days
                item["days_label"] = days_label(days)
                item["poster_url"] = poster_url(item.get("poster_path"))
            items.append(item)
        logger.info(f"Watchlist returned {len(items)} items")
        return items
    except Exception as e:
        logger.error(f"List watchlist failed: {e}")
        raise


@router.post("")
async def add_to_watchlist(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    media_type = body.get("media_type")
    tmdb_id = body.get("tmdb_id")
    title = body.get("title")
    logger.info(f"Add to watchlist request: {media_type}/{tmdb_id} - {title}")
    if media_type not in {"movie", "tv"} or not tmdb_id or not title:
        logger.warning(f"Invalid add to watchlist request: {body}")
        raise HTTPException(status_code=400, detail="media_type, tmdb_id, and title are required")

    poster_path = body.get("poster_path")
    release_date = body.get("release_date")

    try:
        with get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO watchlist (media_type, tmdb_id, title, poster_path, release_date, added_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (media_type, tmdb_id, title, poster_path, release_date, utc_now_iso()),
                )
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    logger.warning(f"Item already on watchlist: {media_type}/{tmdb_id}")
                    raise HTTPException(status_code=409, detail="Already on watchlist") from exc
                logger.error(f"Database error adding to watchlist: {exc}")
                raise

        days = days_until(release_date)
        logger.info(f"Successfully added to watchlist: {media_type}/{tmdb_id}")
        return {
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "release_date": release_date,
            "days_away": days,
            "days_label": days_label(days),
            "poster_url": poster_url(poster_path),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add to watchlist failed: {e}")
        raise


@router.delete("/{media_type}/{tmdb_id}")
async def remove_from_watchlist(media_type: str, tmdb_id: int) -> dict[str, str]:
    logger.info(f"Remove from watchlist request: {media_type}/{tmdb_id}")
    if media_type not in {"movie", "tv"}:
        logger.warning(f"Invalid media_type for removal: {media_type}")
        raise HTTPException(status_code=400, detail="Invalid media_type")
    try:
        with get_connection() as conn:
            result = conn.execute(
                "DELETE FROM watchlist WHERE media_type = ? AND tmdb_id = ?",
                (media_type, tmdb_id),
            )
            if result.rowcount == 0:
                logger.warning(f"Item not found for removal: {media_type}/{tmdb_id}")
                raise HTTPException(status_code=404, detail="Not found")
        logger.info(f"Successfully removed from watchlist: {media_type}/{tmdb_id}")
        return {"status": "removed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove from watchlist failed: {e}")
        raise
