import asyncio
from datetime import datetime, timezone, timedelta
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Depends

from app.auth import get_current_user, CurrentUser
from app.models import days_label, days_until, poster_url
from app.repository import DuplicateItemError
from app.services.tmdb import TmdbClient, fetch_news

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_watchlist(request: Request, current_user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    logger.info("List watchlist request for user: %s", current_user.uid)
    try:
        repo = request.app.state.watchlist_repo
        rows = repo.list_items(current_user.uid)

        tmdb: TmdbClient = request.app.state.tmdb

        async def enrich_item(item: dict[str, Any]) -> dict[str, Any]:
            enriched = dict(item)
            details_cached = enriched.get("details_cached")
            last_updated = enriched.get("last_updated")

            cache_valid = False
            if details_cached and last_updated:
                try:
                    last_updated_dt = datetime.fromisoformat(last_updated)
                    age = datetime.now(timezone.utc) - last_updated_dt
                    if age < timedelta(hours=24):
                        cache_valid = True
                except Exception:
                    pass

            details = None
            if cache_valid:
                try:
                    if isinstance(details_cached, str):
                        details = json.loads(details_cached)
                    else:
                        details = details_cached
                except Exception:
                    pass

            if not details:
                try:
                    details = await tmdb.get_details(enriched["media_type"], enriched["tmdb_id"])
                    repo.update_item_cache(
                        current_user.uid,
                        enriched["media_type"],
                        enriched["tmdb_id"],
                        details,
                    )
                except Exception as exc:
                    logger.warning(f"Failed to fetch details for {enriched['media_type']}/{enriched['tmdb_id']}: {exc}")
                    # Fallback to stale cache if it exists
                    if details_cached:
                        try:
                            if isinstance(details_cached, str):
                                details = json.loads(details_cached)
                            else:
                                details = details_cached
                        except Exception:
                            pass
                    
                    if not details:
                        details = {}

            rel_date = details.get("release_date") or enriched.get("release_date")
            days = days_until(rel_date)
            
            enriched.update(
                {
                    "release_date": rel_date,
                    "poster_url": details.get("poster_url") or poster_url(enriched.get("poster_path")),
                    "days_away": days,
                    "days_label": days_label(days),
                }
            )
            if "overview" in details:
                enriched["overview"] = details["overview"]
            if "vote_average" in details:
                enriched["vote_average"] = details["vote_average"]
            if "status" in details:
                enriched["media_status"] = details["status"]
            return enriched

        tasks = [enrich_item(item) for item in rows]
        items = await asyncio.gather(*tasks)
        logger.info(f"Watchlist returned {len(items)} items")
        return items
    except Exception as e:
        logger.error(f"List watchlist failed: {e}")
        raise


@router.post("")
async def add_to_watchlist(request: Request, body: dict[str, Any], current_user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    media_type = body.get("media_type")
    tmdb_id = body.get("tmdb_id")
    title = body.get("title")
    logger.info(f"Add to watchlist request for user {current_user.uid}: {media_type}/{tmdb_id} - {title}")
    if media_type not in {"movie", "tv"} or not tmdb_id or not title:
        logger.warning(f"Invalid add to watchlist request: {body}")
        raise HTTPException(status_code=400, detail="media_type, tmdb_id, and title are required")

    poster_path = body.get("poster_path")
    release_date = body.get("release_date")
    is_owned = body.get("is_owned", False)
    owned_format = body.get("owned_format", None)
    status = body.get("status", "queue")

    if is_owned and owned_format not in {"electronic", "cloud", "hard_copy"}:
        raise HTTPException(status_code=400, detail="Invalid owned_format. Must be 'electronic', 'cloud', or 'hard_copy'")

    if status not in {"queue", "following"}:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'queue' or 'following'")

    try:
        repo = request.app.state.watchlist_repo
        added = repo.add_item(
            current_user.uid,
            media_type,
            tmdb_id,
            title,
            poster_path,
            release_date,
            is_owned=is_owned,
            owned_format=owned_format,
            status=status,
        )

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
            "is_owned": added.get("is_owned", False),
            "owned_format": added.get("owned_format"),
            "status": added.get("status", "queue"),
        }
    except DuplicateItemError:
        logger.warning(f"Item already on watchlist: {media_type}/{tmdb_id}")
        raise HTTPException(status_code=409, detail="Already on watchlist")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add to watchlist failed: {e}")
        raise


@router.patch("/{media_type}/{tmdb_id}")
async def update_watchlist_item(
    media_type: str,
    tmdb_id: int,
    request: Request,
    body: dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    logger.info(f"Update watchlist item request for user {current_user.uid}: {media_type}/{tmdb_id}")
    if media_type not in {"movie", "tv"}:
        logger.warning(f"Invalid media_type for update: {media_type}")
        raise HTTPException(status_code=400, detail="Invalid media_type")

    is_owned = body.get("is_owned")
    owned_format = body.get("owned_format")
    status = body.get("status")

    if is_owned is None and status is None:
        raise HTTPException(status_code=400, detail="is_owned or status field is required")

    if is_owned is not None and is_owned and owned_format not in {"electronic", "cloud", "hard_copy"}:
        raise HTTPException(status_code=400, detail="Invalid owned_format. Must be 'electronic', 'cloud', or 'hard_copy'")

    if status is not None and status not in {"queue", "following"}:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'queue' or 'following'")

    try:
        repo = request.app.state.watchlist_repo
        updated = repo.update_item(
            current_user.uid,
            media_type,
            tmdb_id,
            is_owned=is_owned,
            owned_format=owned_format,
            status=status,
        )
        if not updated:
            logger.warning(f"Item not found for update: {media_type}/{tmdb_id}")
            raise HTTPException(status_code=404, detail="Not found")

        logger.info(f"Successfully updated watchlist item: {media_type}/{tmdb_id}")
        return {
            "status": "updated",
            "is_owned": updated.get("is_owned", False),
            "owned_format": updated.get("owned_format"),
            "status_value": updated.get("status", "queue"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update watchlist item failed: {e}")
        raise


@router.delete("/{media_type}/{tmdb_id}")
async def remove_from_watchlist(media_type: str, tmdb_id: int, request: Request, current_user: CurrentUser = Depends(get_current_user)) -> dict[str, str]:
    logger.info(f"Remove from watchlist request for user {current_user.uid}: {media_type}/{tmdb_id}")
    if media_type not in {"movie", "tv"}:
        logger.warning(f"Invalid media_type for removal: {media_type}")
        raise HTTPException(status_code=400, detail="Invalid media_type")
    try:
        repo = request.app.state.watchlist_repo
        removed = repo.remove_item(current_user.uid, media_type, tmdb_id)
        if not removed:
            logger.warning(f"Item not found for removal: {media_type}/{tmdb_id}")
            raise HTTPException(status_code=404, detail="Not found")
        logger.info(f"Successfully removed from watchlist: {media_type}/{tmdb_id}")
        return {"status": "removed"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Remove from watchlist failed: {e}")
        raise
