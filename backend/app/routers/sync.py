from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, StrictInt, StrictStr

from app.auth import get_current_user
from app.repository import DuplicateItemError, WatchlistRepository
from app.sync_protocol import validate_operation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncOperationPayload(BaseModel):
  operationId: str
  entityType: str = "movie"
  entityId: str
  operationType: str  # "upsert", "delete", "patch"
  payload: Dict[str, Any]
  createdAt: Optional[str] = None
  baseRevision: Optional[StrictStr] = None


class PushSyncRequest(BaseModel):
  protocolVersion: StrictInt = Field(default=1, ge=1, le=2)
  operations: List[SyncOperationPayload]


class PushSyncResponse(BaseModel):
  status: str = "ok"
  processed_operations: List[str]
  failed_operations: List[Dict[str, str]] = []
  applied_operations: List[Dict[str, str]] = []
  conflicts: List[Dict[str, Any]] = []
  server_timestamp: str


@router.post("/movies/push", response_model=PushSyncResponse)
async def push_movie_sync(
    request: Request,
    body: PushSyncRequest,
    current_user: Any = Depends(get_current_user),
):
  repo: WatchlistRepository = request.app.state.watchlist_repo
  user_id = current_user.uid if hasattr(current_user, "uid") else current_user["uid"]
  expected_owner = request.headers.get("X-Sync-Owner")
  if expected_owner and expected_owner != user_id:
    raise HTTPException(status_code=409, detail="Sync owner does not match session")
  if any(
      op.payload.get("ownerId") is not None and op.payload["ownerId"] != user_id
      for op in body.operations
  ):
    raise HTTPException(status_code=409, detail="Operation owner does not match session")
  now_iso = datetime.now(timezone.utc).isoformat()
  processed_ids = []
  failed_ops = []

  if body.protocolVersion == 2:
    operations = [op.model_dump() for op in body.operations]
    seen = set()
    try:
      for operation in operations:
        validate_operation(operation, user_id)
        if operation["operationId"] in seen:
          raise ValueError(f"Duplicate operationId in the same batch: {operation['operationId']}")
        seen.add(operation["operationId"])
    except ValueError as exc:
      raise HTTPException(status_code=422, detail=str(exc)) from exc
    applied = []
    conflicts = []
    for operation in operations:
      try:
        result = repo.apply_sync_operation(user_id, operation)
        if "conflict" in result:
          conflicts.append(result["conflict"])
        else:
          processed_ids.append(operation["operationId"])
          applied.append(result["applied"])
      except Exception as exc:
        logger.exception("Failed to sync operation %s", operation["operationId"])
        failed_ops.append({"operationId": operation["operationId"], "reason": str(exc)})
    return PushSyncResponse(
        processed_operations=processed_ids, failed_operations=failed_ops,
        applied_operations=applied, conflicts=conflicts, server_timestamp=now_iso,
    )

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
              owned_format=p.get("ownedFormat"),
              watch_free_streaming=bool(p.get("watchFreeStreaming", False)),
              watch_on_sale_buy=bool(p.get("watchOnSaleBuy", False)),
              status=status,
              user_rating=user_rating,
          )
        except DuplicateItemError:
          repo.update_item(
              user_id=user_id,
              media_type=media_type,
              tmdb_id=int(tmdb_id),
              is_owned=is_owned,
              owned_format=p.get("ownedFormat"),
              watch_free_streaming=bool(p.get("watchFreeStreaming", False)),
              watch_on_sale_buy=bool(p.get("watchOnSaleBuy", False)),
              status=status,
              user_rating=user_rating,
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
        elif rating is not None:
          repo.delete_rated_movie(user_id, media_type, int(tmdb_id))

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
    protocolVersion: int = Query(1, ge=1, le=2),
    current_user: Any = Depends(get_current_user),
):
  repo: WatchlistRepository = request.app.state.watchlist_repo
  user_id = current_user.uid if hasattr(current_user, "uid") else current_user["uid"]
  expected_owner = request.headers.get("X-Sync-Owner")
  if expected_owner and expected_owner != user_id:
    raise HTTPException(status_code=409, detail="Sync owner does not match session")
  now_iso = datetime.now(timezone.utc).isoformat()

  if protocolVersion == 2:
    return {
        "records": repo.sync_snapshot(user_id),
        "full_snapshot": True,
        "next_cursor": now_iso,
    }

  watchlist_items = repo.list_items(user_id)
  ratings_items = repo.list_rated_movies(user_id)

  return {
      "watchlist": watchlist_items,
      "ratings": ratings_items,
      "server_timestamp": now_iso,
      "next_cursor": now_iso,
  }
