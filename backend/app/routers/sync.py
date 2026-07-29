from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import get_current_user
from app.repository import WatchlistRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncOperationPayload(BaseModel):
  operationId: str
  entityType: str = "movie"
  entityId: str
  operationType: str  # "upsert", "delete", "patch"
  payload: Dict[str, Any]
  createdAt: Optional[str] = None


class PushSyncRequest(BaseModel):
  operations: List[SyncOperationPayload]


class PushSyncResponse(BaseModel):
  status: str = "ok"
  processed_operations: List[str]
  failed_operations: List[Dict[str, str]] = []
  server_timestamp: str


@router.post("/movies/push", response_model=PushSyncResponse)
async def push_movie_sync(
    request: Request,
    body: PushSyncRequest,
    current_user: Any = Depends(get_current_user),
):
  repo: WatchlistRepository = request.app.state.watchlist_repo
  user_id = current_user.uid if hasattr(current_user, "uid") else current_user["uid"]
  now_iso = datetime.now(timezone.utc).isoformat()
  processed_ids = []
  failed_ops = []

  for op in body.operations:
    try:
      p = op.payload
      tmdb_id = p.get("tmdbId") or p.get("tmdb_id") or p.get("id")
      media_type = p.get("mediaType") or p.get("media_type") or "movie"
      title = p.get("title") or "Untitled"

      if not tmdb_id:
        failed_ops.append(
            {"operationId": op.operationId, "reason": "Missing tmdb_id"}
        )
        continue

      if op.operationType == "delete" or p.get("deletedAt") or p.get("deleted_at"):
        # Tombstone deletion
        repo.remove_item(user_id, media_type, int(tmdb_id))
        processed_ids.append(op.operationId)
      else:
        status = p.get("status", "queue")
        is_owned = bool(p.get("isOwned") or p.get("is_owned") or False)
        rating = p.get("rating")
        user_rating = int(rating) if rating and rating > 0 else 0

        try:
          repo.add_item(
              user_id=user_id,
              media_type=media_type,
              tmdb_id=int(tmdb_id),
              title=title,
              poster_path=p.get("posterPath") or p.get("poster_path"),
              release_date=p.get("releaseDate") or p.get("release_date"),
              is_owned=is_owned,
              status=status,
              user_rating=user_rating,
          )
        except Exception:
          repo.update_item(
              user_id=user_id,
              media_type=media_type,
              tmdb_id=int(tmdb_id),
              is_owned=is_owned,
              status=status,
              user_rating=user_rating if user_rating > 0 else None,
          )

        # Rate movie if rating present
        if user_rating > 0:
          repo.rate_movie(
              user_id=user_id,
              media_type=media_type,
              tmdb_id=int(tmdb_id),
              title=title,
              poster_path=p.get("posterPath") or p.get("poster_path"),
              release_date=p.get("releaseDate") or p.get("release_date"),
              rating=user_rating,
          )

        processed_ids.append(op.operationId)
    except Exception as e:
      logger.exception(f"Failed to sync operation {op.operationId}: {e}")
      failed_ops.append({"operationId": op.operationId, "reason": str(e)})

  return PushSyncResponse(
      status="ok",
      processed_operations=processed_ids,
      failed_operations=failed_ops,
      server_timestamp=now_iso,
  )


@router.get("/movies/pull")
async def pull_movie_sync(
    request: Request,
    since_cursor: Optional[str] = Query(None),
    current_user: Any = Depends(get_current_user),
):
  repo: WatchlistRepository = request.app.state.watchlist_repo
  user_id = current_user.uid if hasattr(current_user, "uid") else current_user["uid"]
  now_iso = datetime.now(timezone.utc).isoformat()

  watchlist_items = repo.list_items(user_id)
  ratings_items = repo.list_rated_movies(user_id)

  return {
      "watchlist": watchlist_items,
      "ratings": ratings_items,
      "server_timestamp": now_iso,
      "next_cursor": now_iso,
  }
