import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel

from app.config import (
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
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

    if admin_user:
        if verify_password(body.password, admin_user["password_hash"], admin_user["salt"]):
            success = True
    elif body.username == ADMIN_USERNAME and body.password == ADMIN_PASSWORD:
        # Fallback to env default if DB user not initialized or matches default
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
) -> dict[str, str]:
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
    return {"status": "success"}

@router.get("/login-logs")
async def get_login_logs(
    request: Request,
    current_admin: str = Depends(get_current_admin)
) -> dict[str, Any]:
    repo = request.app.state.watchlist_repo
    logs = repo.list_login_logs(limit=100)
    return {"logs": logs}
