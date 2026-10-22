"""Canonical protocol-v2 state shared by both storage backends."""

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class MoviePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    tmdbId: StrictInt = Field(gt=0)
    mediaType: Literal["movie", "tv"] = "movie"
    title: StrictStr = "Untitled"
    posterPath: StrictStr | None = None
    releaseDate: StrictStr | None = None
    status: Literal["queue", "following", "watched", "library"] = "queue"
    isOwned: StrictBool = False
    ownedFormat: Literal["electronic", "cloud", "hard_copy"] | None = None
    watchFreeStreaming: StrictBool = False
    watchOnSaleBuy: StrictBool = False
    rating: StrictInt | None = Field(default=None, ge=0, le=5)
    deletedAt: StrictStr | None = None


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def operation_fingerprint(operation: dict[str, Any]) -> str:
    """Ignore transport/retry bookkeeping; bind the immutable write intent."""
    return digest({key: operation[key] for key in (
        "entityId", "operationType", "baseRevision", "payload",
    )})


def validate_operation(operation: dict[str, Any], user_id: str | None = None) -> None:
    """Validate the complete batch before entering any storage transaction."""
    if not operation["operationId"].strip() or not operation.get("baseRevision"):
        raise ValueError("operationId and baseRevision must be non-empty strings")
    if operation["operationType"] not in {"upsert", "delete"}:
        raise ValueError("Protocol v2 supports only upsert and delete")
    payload = MoviePayload.model_validate(operation["payload"])
    owner = operation["payload"].get("ownerId")
    if user_id is not None and owner is not None and owner != user_id:
        raise ValueError("Operation owner does not match session")
    if operation["entityId"] != f"{payload.mediaType}_{payload.tmdbId}":
        raise ValueError("entityId must match mediaType and tmdbId")
    if operation["operationType"] == "upsert" and payload.deletedAt is not None:
        raise ValueError("Use a delete operation for tombstones")
    operation_fingerprint(operation)


def sync_record(
    media_type: str, tmdb_id: int, watch: dict | None, rated: dict | None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    source = watch or rated or {}
    rating = (rated or {}).get("rating") if rated else (watch or {}).get("user_rating")
    record = {
        "id": f"{media_type}_{tmdb_id}",
        "tmdbId": tmdb_id,
        "mediaType": media_type,
        "title": source.get("title") or "Untitled",
        "posterPath": source.get("poster_path"),
        "releaseDate": source.get("release_date"),
        "status": source.get("status") or ("queue" if watch is not None else "watched"),
        "isOwned": bool(source.get("is_owned")),
        "ownedFormat": source.get("owned_format") if source.get("is_owned") else None,
        "watchFreeStreaming": bool(source.get("watch_free_streaming")),
        "watchOnSaleBuy": bool(source.get("watch_on_sale_buy")),
        "rating": int(rating) if rating else None,
        "deletedAt": deleted_at if watch is None and rated is None else None,
    }
    # Presence and both rating stores are authoritative. TMDB metadata, caches,
    # IDs and timestamps must not manufacture conflicts during a refresh.
    state = {key: record[key] for key in (
        "status", "isOwned", "ownedFormat", "watchFreeStreaming", "watchOnSaleBuy", "rating",
    )}
    state.update(
        watchlist_present=watch is not None,
        rating_present=rated is not None,
        user_rating=int((watch or {}).get("user_rating") or 0),
        target_rental_price=(watch or {}).get("target_rental_price"),
    )
    record["revision"] = (
        "v2:" + digest(state) if watch is not None or rated is not None else "absent"
    )
    return record


def sync_records(watchlist: list[dict], ratings: list[dict]) -> list[dict]:
    watch = {(row["media_type"], row["tmdb_id"]): row for row in watchlist}
    rated = {(row["media_type"], row["tmdb_id"]): row for row in ratings}
    return [
        sync_record(media, tmdb, watch.get((media, tmdb)), rated.get((media, tmdb)))
        for media, tmdb in sorted(watch.keys() | rated.keys())
    ]


def operation_result(operation: dict, remote: dict) -> dict:
    if operation["baseRevision"] != remote["revision"]:
        return {"conflict": {
            "operationId": operation["operationId"],
            "entityId": operation["entityId"], "remote": remote,
        }}
    return {}


def write_values(payload: dict, existing: dict | None, now: str) -> dict:
    p = MoviePayload.model_validate(payload)
    return {
        "media_type": p.mediaType, "tmdb_id": p.tmdbId, "title": p.title,
        "poster_path": p.posterPath, "release_date": p.releaseDate,
        "added_at": (existing or {}).get("added_at") or now,
        "is_owned": p.isOwned, "owned_format": p.ownedFormat if p.isOwned else None,
        "status": p.status, "watch_free_streaming": p.watchFreeStreaming,
        "watch_on_sale_buy": p.watchOnSaleBuy,
        "target_rental_price": (existing or {}).get("target_rental_price"),
        "user_rating": p.rating or 0,
    }


def check_receipt(receipt: dict, fingerprint: str) -> dict:
    if receipt["fingerprint"] != fingerprint:
        raise ValueError("operationId has already been used with different content")
    return receipt["result"]
