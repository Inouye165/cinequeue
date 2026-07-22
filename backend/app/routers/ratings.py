import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ratings", tags=["ratings"], dependencies=[Depends(get_current_user)])


class RateMoviePayload(BaseModel):
    media_type: str = "movie"
    tmdb_id: int
    title: str
    poster_path: str | None = None
    release_date: str | None = None
    rating: int = Field(ge=1, le=5)


@router.get("")
async def list_rated_movies(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    repo = request.app.state.watchlist_repo
    return repo.list_rated_movies(current_user.uid)


@router.post("")
async def rate_movie(
    payload: RateMoviePayload,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    return repo.rate_movie(
        user_id=current_user.uid,
        media_type=payload.media_type,
        tmdb_id=payload.tmdb_id,
        title=payload.title,
        poster_path=payload.poster_path,
        release_date=payload.release_date,
        rating=payload.rating,
    )


@router.delete("/{media_type}/{tmdb_id}")
async def delete_rated_movie(
    media_type: str,
    tmdb_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, bool]:
    repo = request.app.state.watchlist_repo
    removed = repo.delete_rated_movie(current_user.uid, media_type, tmdb_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Rated movie not found")
    return {"success": True}
