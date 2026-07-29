import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel

import app.config as config
from app.config import (
    ADMIN_SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
)
from app.routers.auth import validate_csrf
from app.services.admin_auth import (
    verify_password,
    hash_password,
    generate_salt,
    generate_session_token,
    get_current_admin,
)
from app.services.email_service import send_invite_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

class AdminLoginRequest(BaseModel):
    username: str
    password: str
    csrf_token: str

class InviteRequest(BaseModel):
    email: str
    csrf_token: str

class ApprovalActionRequest(BaseModel):
    email: str
    csrf_token: str

class AdminLogoutRequest(BaseModel):
    csrf_token: str

@router.post("/login")
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    response: Response
) -> dict[str, str]:
    # 1. CSRF Validation
    validate_csrf(request, body.csrf_token)

    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    repo = request.app.state.watchlist_repo
    timestamp = repo.utc_now_iso()

    # 2. Check credentials
    admin_user = repo.get_admin_user(body.username)
    success = False
    reason = "invalid_credentials"

    if admin_user and verify_password(body.password, admin_user["password_hash"], admin_user["salt"]):
        success = True
    elif config.ENABLE_FALLBACK_ADMIN_AUTH and config.ADMIN_USERNAME and config.ADMIN_PASSWORD:
        if secrets.compare_digest(body.username, config.ADMIN_USERNAME) and secrets.compare_digest(body.password, config.ADMIN_PASSWORD):
            success = True

    if not success:
        repo.log_login_attempt(
            email=body.username,
            status="failed",
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            timestamp=timestamp,
        )
        logger.warning("Admin login failed for user: %s", body.username)
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    # 3. Create Admin Session
    session_token = generate_session_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    repo.create_admin_session(
        session_id=session_token,
        username=body.username,
        expires_at=expires_at,
    )

    # 4. Log attempt
    repo.log_login_attempt(
        email=body.username,
        status="success",
        reason="admin_login",
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=timestamp,
    )

    # 5. Set secure session cookie
    max_age = 24 * 60 * 60  # 1 day
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=max_age,
    )

    logger.info("Admin %s logged in successfully", body.username)
    return {"status": "success"}

@router.post("/logout")
async def admin_logout(
    body: AdminLogoutRequest,
    request: Request,
    response: Response,
) -> dict[str, str]:
    validate_csrf(request, body.csrf_token)

    session_cookie = request.cookies.get(ADMIN_SESSION_COOKIE_NAME)
    if session_cookie:
        repo = request.app.state.watchlist_repo
        repo.delete_admin_session(session_cookie)

    response.delete_cookie(
        key=ADMIN_SESSION_COOKIE_NAME,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
    )
    return {"status": "success"}

@router.get("/me")
async def admin_me(
    current_admin: str = Depends(get_current_admin)
) -> dict[str, str]:
    return {"username": current_admin}

@router.get("/requests")
async def get_requests(
    request: Request,
    current_admin: str = Depends(get_current_admin)
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    approvals = repo.list_user_approvals()
    return {"approvals": approvals}

@router.post("/approve")
async def approve_request(
    body: ApprovalActionRequest,
    request: Request,
    current_admin: str = Depends(get_current_admin)
) -> dict[str, str]:
    validate_csrf(request, body.csrf_token)
    email_normalized = body.email.strip().lower()

    repo = request.app.state.watchlist_repo
    decided_at = repo.utc_now_iso()
    repo.update_user_approval(
        email=email_normalized,
        status="approved",
        decided_at=decided_at,
        decided_by=current_admin,
    )
    logger.info("Admin %s approved user %s", current_admin, email_normalized)
    return {"status": "success"}

@router.post("/deny")
async def deny_request(
    body: ApprovalActionRequest,
    request: Request,
    current_admin: str = Depends(get_current_admin)
) -> dict[str, str]:
    validate_csrf(request, body.csrf_token)
    email_normalized = body.email.strip().lower()

    repo = request.app.state.watchlist_repo
    decided_at = repo.utc_now_iso()
    repo.update_user_approval(
        email=email_normalized,
        status="revoked",
        decided_at=decided_at,
        decided_by=current_admin,
    )
    logger.info("Admin %s revoked/denied access for user %s", current_admin, email_normalized)
    return {"status": "success"}

@router.post("/invite")
async def invite_user(
    body: InviteRequest,
    request: Request,
    current_admin: str = Depends(get_current_admin)
) -> dict[str, Any]:
    validate_csrf(request, body.csrf_token)
    email_normalized = body.email.strip().lower()

    repo = request.app.state.watchlist_repo
    decided_at = repo.utc_now_iso()
    
    # Check if entry already exists
    existing = repo.get_user_approval(email_normalized)
    if existing:
        repo.update_user_approval(
            email=email_normalized,
            status="approved",
            decided_at=decided_at,
            decided_by=current_admin,
        )
    else:
        repo.create_user_approval(
            email=email_normalized,
            status="approved",
            requested_at=decided_at,
        )
        repo.update_user_approval(
            email=email_normalized,
            status="approved",
            decided_at=decided_at,
            decided_by=current_admin,
        )
    logger.info("Admin %s invited/pre-approved user %s", current_admin, email_normalized)

    # Determine origin/app URL from request headers
    origin = request.headers.get("origin") or ""
    if not origin and request.headers.get("referer"):
        origin = request.headers.get("referer").rstrip("/")

    email_sent, email_detail = await send_invite_email(
        to_email=email_normalized,
        app_url=origin,
        sender_admin=current_admin,
    )

    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    log_status = "success" if email_sent else "warning"
    log_reason = "invite_email_dispatched" if email_sent else f"invite_preapproved_no_email ({email_detail})"

    repo.log_login_attempt(
        email=email_normalized,
        status=log_status,
        reason=log_reason,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=decided_at,
    )

    msg = email_detail if email_sent else f"User {email_normalized} pre-approved! ({email_detail})"

    return {
        "status": "success",
        "email": email_normalized,
        "email_sent": email_sent,
        "message": msg,
    }

@router.get("/login-logs")
async def get_login_logs(
    request: Request,
    limit: int = 100,
    email: Optional[str] = None,
    status: Optional[str] = None,
    reason: Optional[str] = None,
    current_admin: str = Depends(get_current_admin)
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    logs = repo.list_login_logs(limit=limit, email=email, status=status, reason=reason)
    return {"logs": logs}


# -- Agent Decisions Admin Endpoints -----------------------------------------

class SaveDecisionConfigRequest(BaseModel):
    config: dict[str, Any]
    change_note: str = "Updated decision configuration"


class SavePromptVersionRequest(BaseModel):
    system_instruction_template: str
    wording_instruction: str
    change_note: str = "Updated wording instruction"


class PreviewDecisionRequest(BaseModel):
    user_id: str = "preview_user"
    weather_condition: Optional[str] = "Rain"
    significant_alert: Optional[str] = None
    monitored_title_update: Optional[str] = "Spider-Man"
    is_streaming_arrival: bool = True
    trivia_fact: Optional[str] = None
    major_news_title: Optional[str] = None
    user_interest_score: float = 0.85
    random_seed: Optional[int] = 42


@router.get("/agent/decision-logs")
async def get_agent_decision_logs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[str] = None,
    candidate_type: Optional[str] = None,
    fallback_only: bool = False,
    model: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    return repo.list_decision_logs(
        limit=limit,
        offset=offset,
        user_id=user_id,
        candidate_type=candidate_type,
        fallback_only=fallback_only,
        model=model,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/agent/decision-logs/{log_id}")
async def get_agent_decision_log_detail(
    log_id: str,
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    log = repo.get_decision_log(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Decision log not found")
    return log


@router.get("/agent/config")
async def get_agent_decision_config(
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    return repo.get_active_decision_config()


@router.put("/agent/config")
async def save_agent_decision_config(
    body: SaveDecisionConfigRequest,
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    from app.decision_models import DecisionConfig
    repo = request.app.state.watchlist_repo

    # Validate config
    try:
        cfg = DecisionConfig(**body.config)
        errs = cfg.validate()
        if errs:
            raise HTTPException(status_code=400, detail="; ".join(errs))
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration parameters: {e}")

    saved = repo.save_decision_config(cfg.to_dict(), updated_by=current_admin, change_note=body.change_note)
    logger.info("Admin %s updated decision config to version %d", current_admin, saved["version"])
    return saved


@router.post("/agent/config/reset")
async def reset_agent_decision_config(
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    from app.decision_models import DEFAULT_DECISION_CONFIG
    repo = request.app.state.watchlist_repo
    saved = repo.save_decision_config(
        DEFAULT_DECISION_CONFIG.to_dict(),
        updated_by=current_admin,
        change_note="Reset decision settings to default values",
    )
    logger.info("Admin %s reset decision settings to default version %d", current_admin, saved["version"])
    return saved


@router.get("/agent/prompts")
async def list_agent_prompt_versions(
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    versions = repo.list_prompt_versions()
    return {"versions": versions, "active_version": repo.get_active_prompt_version()}


@router.post("/agent/prompts")
async def save_agent_prompt_version(
    body: SavePromptVersionRequest,
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    from app.decision_models import PromptVersion
    repo = request.app.state.watchlist_repo

    prompt_obj = PromptVersion(
        system_instruction_template=body.system_instruction_template,
        wording_instruction=body.wording_instruction,
    )
    errs = prompt_obj.validate()
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))

    saved = repo.save_prompt_version(prompt_obj.to_dict(), updated_by=current_admin, change_note=body.change_note)
    logger.info("Admin %s created prompt version %d", current_admin, saved["version"])
    return saved


@router.post("/agent/prompts/{version}/restore")
async def restore_agent_prompt_version(
    version: int,
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    versions = repo.list_prompt_versions()
    target = next((v for v in versions if v.get("version") == version), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Prompt version {version} not found")

    saved = repo.save_prompt_version(
        target,
        updated_by=current_admin,
        change_note=f"Restored prompt version {version}",
    )
    logger.info("Admin %s restored prompt version %d (new version %d)", current_admin, version, saved["version"])
    return saved


@router.post("/agent/preview")
async def preview_agent_decision(
    body: PreviewDecisionRequest,
    request: Request,
    current_admin: str = Depends(get_current_admin),
) -> dict[str, Any]:
    from app.decision_models import Candidate, CandidateType, DecisionConfig, PromptVersion
    from app.services.decision_engine import DecisionEngine
    from app.services.agent_service import AiAgentService

    repo = request.app.state.watchlist_repo
    cfg = DecisionConfig(**repo.get_active_decision_config())
    prompt_ver = PromptVersion(**repo.get_active_prompt_version())

    raw_candidates: list[Candidate] = []

    if body.significant_alert:
        raw_candidates.append(Candidate(
            candidate_id="preview_weather_alert",
            type=CandidateType.WEATHER_ALERT.value,
            title="Severe Weather Warning",
            summary=body.significant_alert,
            source="preview_input",
            required=True,
            importance_score=0.95,
            interest_score=0.90,
            confidence_score=0.99,
        ))

    if body.monitored_title_update:
        c_type = CandidateType.STREAMING_ARRIVAL.value if body.is_streaming_arrival else CandidateType.MONITORED_TITLE_RELEASE.value
        raw_candidates.append(Candidate(
            candidate_id="preview_monitored_title",
            type=c_type,
            title=body.monitored_title_update,
            summary=f"'{body.monitored_title_update}' became available to stream today." if body.is_streaming_arrival else f"'{body.monitored_title_update}' is releasing today.",
            source="preview_input",
            required=True,
            importance_score=0.90,
            interest_score=body.user_interest_score,
            confidence_score=0.98,
        ))

    if body.weather_condition and body.monitored_title_update and body.is_streaming_arrival:
        raw_candidates.append(Candidate(
            candidate_id="preview_weather_conn",
            type=CandidateType.WEATHER_VIEWING_CONNECTION.value,
            title=body.monitored_title_update,
            summary=f"It is currently {body.weather_condition.lower()} outside, and '{body.monitored_title_update}' became available to stream today.",
            source="preview_input",
            required=False,
            importance_score=0.65,
            interest_score=body.user_interest_score,
            confidence_score=0.95,
        ))

    if body.trivia_fact:
        raw_candidates.append(Candidate(
            candidate_id="preview_trivia",
            type=CandidateType.PERSONALIZED_TRIVIA.value,
            title=body.monitored_title_update or "Movie Fact",
            summary=body.trivia_fact,
            source="preview_input",
            required=False,
            importance_score=0.50,
            interest_score=body.user_interest_score,
            confidence_score=0.95,
        ))

    if body.major_news_title:
        raw_candidates.append(Candidate(
            candidate_id="preview_news",
            type=CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS.value,
            title=body.major_news_title,
            summary=f"Major announcement concerning '{body.major_news_title}'.",
            source="preview_input",
            required=False,
            importance_score=0.75,
            interest_score=body.user_interest_score,
            confidence_score=0.90,
        ))

    decision_log, selected_cands = DecisionEngine.evaluate(
        user_id=body.user_id,
        repo=repo,
        tmdb=None,
        raw_candidates=raw_candidates,
        config=cfg,
        prompt_version=prompt_ver,
        random_seed=body.random_seed,
    )

    formatting_items = [{"title": c.title, "summary": c.summary, "type": c.type} for c in selected_cands]
    sample_greeting = await AiAgentService._format_structured_llm_briefing(
        settings={},
        weather_data={"conditions": body.weather_condition, "significant_alert": body.significant_alert},
        briefing_items=formatting_items,
        recent_openings=[],
        prompt_version=prompt_ver,
    )

    log_dict = decision_log.to_dict()
    log_dict["final_response"] = sample_greeting
    log_dict["sanitized_prompt"] = f"Wording Instruction: {prompt_ver.wording_instruction}"

    return {
        "preview_mode": True,
        "random_seed": body.random_seed,
        "decision_log": log_dict,
        "generated_greeting": sample_greeting,
        "config_used": cfg.to_dict(),
        "prompt_version_used": prompt_ver.to_dict(),
    }

