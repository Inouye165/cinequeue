import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user
from app.services.agent_service import AiAgentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"], dependencies=[Depends(get_current_user)])


class AgentSettingsPayload(BaseModel):
    personality_preset: str = "cinephile"
    custom_prompt: str = ""
    notify_on_login: bool = True
    auto_add_mentioned: bool = True
    track_price_drops: bool = True


class ChatMessagePayload(BaseModel):
    message: str


@router.get("/briefing")
async def get_agent_briefing(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    logger.info("Fetching agent briefing for user: %s", current_user.uid)
    repo = request.app.state.watchlist_repo
    tmdb = getattr(request.app.state, "tmdb", None)
    return await AiAgentService.evaluate_monitored_updates(current_user.uid, repo, tmdb)


@router.get("/settings")
async def get_agent_settings(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    return repo.get_agent_settings(current_user.uid)


@router.post("/settings")
async def save_agent_settings(
    payload: AgentSettingsPayload,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    return repo.save_agent_settings(current_user.uid, payload.model_dump())


@router.get("/chat")
async def list_chat_messages(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, Any]]:
    repo = request.app.state.watchlist_repo
    return repo.list_chat_messages(current_user.uid)


@router.post("/chat")
async def send_chat_message(
    payload: ChatMessagePayload,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    repo = request.app.state.watchlist_repo
    tmdb = getattr(request.app.state, "tmdb", None)
    return await AiAgentService.process_chat(current_user.uid, payload.message.strip(), repo, tmdb)


@router.delete("/chat")
async def clear_chat_history(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    repo = request.app.state.watchlist_repo
    repo.clear_chat_messages(current_user.uid)
    return {"status": "cleared"}
