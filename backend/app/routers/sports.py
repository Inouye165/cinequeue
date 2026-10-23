"""Sports router for catalog, live NFL/NBA schedule, and user sports preferences."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.services.sports_service import sports_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sports", tags=["sports"])


class SportsPreferencesPayload(BaseModel):
    streaming_services: list[str] | None = None
    tracked_teams: list[str] | None = None
    show_in_queue: bool | None = None
    setup_completed: bool | None = None


@router.get("/catalog")
async def get_sports_catalog() -> dict[str, Any]:
    return sports_service.get_catalog()


@router.get("/schedule")
async def get_sports_schedule(
    teams: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    tracked = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    games = await sports_service.get_schedule(tracked_teams=tracked, force_refresh=force_refresh)
    return {"games": games}


@router.get("/preferences")
async def get_sports_preferences(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    try:
        return repo.get_sports_preferences(current_user.uid)
    except Exception as exc:
        logger.error("Error getting sports preferences for %s: %s", current_user.uid, exc, exc_info=True)
        return {
            "user_id": current_user.uid,
            "streaming_services": [],
            "tracked_teams": [],
            "show_in_queue": True,
            "setup_completed": False,
        }


@router.put("/preferences")
async def save_sports_preferences(
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
