"""Sports router for catalog, live NFL/NBA schedule, and user sports preferences."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, StringConstraints

from app.auth import CurrentUser, get_current_user, require_cookie_csrf_and_origin
from app.services.sports_service import sports_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sports",
    tags=["sports"],
    dependencies=[Depends(get_current_user), Depends(require_cookie_csrf_and_origin)],
)


ShortIdStr = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class SportsPreferencesPayload(BaseModel):
    streaming_services: list[ShortIdStr] | None = Field(default=None, max_length=50)
    tracked_teams: list[ShortIdStr] | None = Field(default=None, max_length=100)
    show_in_queue: bool | None = None
    setup_completed: bool | None = None


@router.get("/catalog")
def get_sports_catalog() -> dict[str, Any]:
    return sports_service.get_catalog()


@router.get("/schedule")
async def get_sports_schedule(
    teams: str | None = Query(default=None, max_length=2000),
    force_refresh: bool = False,
) -> dict[str, Any]:
    tracked = [t.strip() for t in teams.split(",") if t.strip()][:100] if teams else None
    games = await sports_service.get_schedule(tracked_teams=tracked, force_refresh=force_refresh)
    return {"games": games}


@router.get("/preferences")
def get_sports_preferences(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    try:
        return repo.get_sports_preferences(current_user.uid)
    except Exception as exc:
        logger.error("Error getting sports preferences for %s: %s", current_user.uid, exc, exc_info=True)
        raise HTTPException(status_code=503, detail="Sports preferences temporarily unavailable")


@router.put("/preferences")
def save_sports_preferences(
    payload: SportsPreferencesPayload,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    try:
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        return repo.save_sports_preferences(current_user.uid, data)
    except Exception as exc:
        logger.error("Error saving sports preferences for %s: %s", current_user.uid, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save sports preferences")
