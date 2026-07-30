import base64
import datetime
import json
import logging
import time
import re
import asyncio
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, Depends, BackgroundTasks
from pydantic import BaseModel
from firebase_admin import auth as firebase_auth

from app.config import (
    AUTH_ENABLED,
    AUTH_MODE,
    AUTH_ALLOWED_EMAILS,
    AUTH_ALLOWED_ORIGINS,
    FIREBASE_PROJECT_ID,
    FIREBASE_API_KEY,
    FIREBASE_AUTH_DOMAIN,
    PUBLIC_AUTH_DOMAIN,
    FIREBASE_APP_ID,
    FIREBASE_MESSAGING_SENDER_ID,
    SESSION_COOKIE_DAYS,
    SESSION_COOKIE_SECURE,
    SESSION_COOKIE_NAME,
)
from app.auth import (
    CurrentUser,
    generate_csrf_token,
    verify_csrf_token,
    get_current_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

class SessionRequest(BaseModel):
    id_token: str
    csrf_token: str

class LogoutRequest(BaseModel):
    csrf_token: str

def validate_origin(request: Request):
    """Validate the Origin header against exact configured allowlist in production."""
    if not AUTH_ENABLED:
        return

    origin = request.headers.get("origin")
    if origin:
        normalized_origin = origin.rstrip("/")
        if normalized_origin not in AUTH_ALLOWED_ORIGINS:
            logger.warning("Origin validation failed: %s not in %s", origin, AUTH_ALLOWED_ORIGINS)
            raise HTTPException(status_code=401, detail="Origin not allowed")
    else:
        logger.warning("Origin header is missing for state-changing operation")
        raise HTTPException(status_code=401, detail="Missing Origin header")

def validate_csrf(request: Request, request_csrf: str):
    """Validate CSRF token against the cookie value."""
    cookie_csrf = request.cookies.get("cinequeue_csrf")
    if not request_csrf or not cookie_csrf or not verify_csrf_token(request_csrf, cookie_csrf):
        logger.warning("CSRF token mismatch or missing: request=%s, cookie=%s", request_csrf, cookie_csrf)
        raise HTTPException(status_code=401, detail="CSRF validation failed")

@router.get("/config")
async def get_config():
    """Return only public Firebase configuration."""
    return {
        "apiKey": FIREBASE_API_KEY,
        "authDomain": PUBLIC_AUTH_DOMAIN or FIREBASE_AUTH_DOMAIN,
        "projectId": FIREBASE_PROJECT_ID,
        "appId": FIREBASE_APP_ID,
        "messagingSenderId": FIREBASE_MESSAGING_SENDER_ID,
    }

@router.get("/csrf")
async def get_csrf(response: Response):
    """Generate and set a readable CSRF token cookie and return it."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    token = generate_csrf_token()
    
    # Secure=True in production, False in dev. HttpOnly=False so JS can read it.
    response.set_cookie(
        key="cinequeue_csrf",
        value=token,
        httponly=False,
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    return {"csrf_token": token}

def extract_client_ip(request: Request) -> str:
    """Safely extract client IP address, handling Cloud Run X-Forwarded-For proxies."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first_ip = forwarded.split(",")[0].strip()
        if first_ip:
            return first_ip
    return request.client.host if request.client else "unknown"

def log_auth_audit_event(
    request: Request,
    endpoint: str,
    email: str,
    auth_result: str,
    reason: str,
    audit_write_attempted: bool,
    audit_write_result: str,
    http_status: int,
    correlation_id: str,
):
    repo = getattr(request.app.state, "watchlist_repo", None) if hasattr(request.app, "state") else None
    target_db = getattr(repo, "db_name", "firestore/login_logs") if repo else "unknown/login_logs"
    logger.info(
        "[AUTH_AUDIT] correlation_id=%s endpoint=%s email=%s result=%s reason=%s audit_attempted=%s audit_result=%s db_target=%s http_status=%d",
        correlation_id,
        endpoint,
        email or "unknown",
        auth_result,
        reason,
        str(audit_write_attempted).lower(),
        audit_write_result,
        target_db,
        http_status,
    )

@router.post("/session")
async def create_session(
    body: SessionRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
):
    """Exchange Firebase ID token for a secure session cookie."""
    t_start = time.perf_counter()
    correlation_id = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:12]

    if not AUTH_ENABLED:
        log_auth_audit_event(
            request=request,
            endpoint="/api/auth/session",
            email="unknown",
            auth_result="success",
            reason="auth_disabled",
            audit_write_attempted=False,
            audit_write_result="skipped",
            http_status=200,
            correlation_id=correlation_id,
        )
        return {"status": "ok", "message": "Auth is disabled"}

    repo = request.app.state.watchlist_repo
    ip_address = extract_client_ip(request)
    user_agent = request.headers.get("user-agent", "unknown")
    timestamp = repo.utc_now_iso()

    def log_failure(email_addr: str, fail_reason: str, http_status: int = 401):
        target_email = email_addr or "unknown"
        write_attempted = True
        write_result = "success"
        try:
            repo.log_login_attempt(
                email=target_email,
                status="failed",
                reason=fail_reason,
                ip_address=ip_address,
                user_agent=user_agent,
                timestamp=timestamp,
            )
        except Exception as log_err:
            write_result = "failed"
            logger.error("Failed to write login failure audit log: %s", log_err)

        log_auth_audit_event(
            request=request,
            endpoint="/api/auth/session",
            email=target_email,
            auth_result="failed",
            reason=fail_reason,
            audit_write_attempted=write_attempted,
            audit_write_result=write_result,
            http_status=http_status,
            correlation_id=correlation_id,
        )

    # Stage 2: CSRF Validation
    t_stage1 = time.perf_counter()
    try:
        validate_csrf(request, body.csrf_token)
    except Exception as e:
        logger.warning("Session Creation Stage 2: CSRF validation failed: %s", e)
        log_failure("unknown", "csrf_validation_failed", 401)
        raise

    # Stage 3: Origin Validation
    try:
        validate_origin(request)
    except Exception as e:
        logger.warning("Session Creation Stage 3: Origin validation failed: %s", e)
        log_failure("unknown", "origin_validation_failed", 401)
        raise

    # Stage 3.5: Early auth_time pre-check (decode JWT payload without verification)
    try:
        payload_part = body.id_token.split(".")[1]
        padding = 4 - len(payload_part) % 4
        if padding != 4:
            payload_part += "=" * padding
        unverified_payload = json.loads(base64.urlsafe_b64decode(payload_part))
        pre_auth_time = unverified_payload.get("auth_time")
        if pre_auth_time:
            pre_age = time.time() - pre_auth_time
            if pre_age > 5 * 60:
                pre_email = unverified_payload.get("email", "unknown").strip().lower()
                logger.warning(
                    "Session Creation Stage 3.5: auth_time is %.0f seconds old — rejecting immediately",
                    pre_age,
                )
                log_failure(pre_email, "auth_time_expired_precheck", 401)
                raise HTTPException(
                    status_code=401,
                    detail="Authentication time is too old. Please sign in again.",
                )
    except HTTPException:
        raise
    except Exception as pre_err:
        logger.debug("Stage 3.5 pre-check failed (non-fatal): %s", pre_err)

    # Stage 4: Firebase ID-token verification
    t_stage3 = time.perf_counter()
    decoded_token = None
    try:
        decoded_token = firebase_auth.verify_id_token(body.id_token, clock_skew_seconds=60)
    except Exception as e:
        if "Token used too early" in str(e):
            match = re.search(r"Token used too early,\s*(\d+)\s*<\s*(\d+)", str(e))
            sleep_time = 5.0
            drift_val = "unknown"
            if match:
                local_time_val = int(match.group(1))
                token_time_val = int(match.group(2))
                drift_seconds = token_time_val - local_time_val
                drift_val = str(drift_seconds)
                sleep_time = float(drift_seconds) + 1.0
            
            logger.warning(
                "Session Creation Stage 4: Token used too early due to clock skew (%s seconds drift). Retrying in %s seconds...",
                drift_val, sleep_time
            )
            await asyncio.sleep(sleep_time)
            try:
                decoded_token = firebase_auth.verify_id_token(body.id_token, clock_skew_seconds=60)
            except Exception as retry_err:
                log_failure("unknown", "clock_skew_verification_failed", 401)
                raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")
        else:
            logger.error("Session Creation Stage 4: Firebase ID-token verification failed: %s", e)
            log_failure("unknown", "invalid_id_token", 401)
            raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")

    t_stage4 = time.perf_counter()
    email = decoded_token.get("email", "").strip().lower() if decoded_token else "unknown"

    # Stage 5: auth_time freshness validation
    try:
        auth_time = decoded_token.get("auth_time")
        if not auth_time:
            log_failure(email, "auth_time_missing", 401)
            raise HTTPException(status_code=401, detail="Authentication time is too old")
        age = time.time() - auth_time
        if age > 5 * 60:
            logger.warning("Session Creation Stage 5: ID token auth_time is too old: %s", auth_time)
            log_failure(email, "auth_time_expired", 401)
            raise HTTPException(status_code=401, detail="Authentication time is too old")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Session Creation Stage 5 failed: %s", e)
        log_failure(email, "auth_time_validation_failed", 401)
        raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")

    # Stage 6: email_verified validation
    try:
        email_verified = decoded_token.get("email_verified")
        if not email_verified:
            logger.warning("Session Creation Stage 6: Email is not verified for %s", email)
            log_failure(email, "email_not_verified", 401)
            raise HTTPException(status_code=401, detail="Email is not verified. Please verify your email before signing in.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Session Creation Stage 6 failed: %s", e)
        log_failure(email, "email_verified_check_failed", 401)
        raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")

    # Stage 7: Email DB Authorization
    t_stage6 = time.perf_counter()
    try:
        approval = repo.get_user_approval(email)
        if not approval:
            if AUTH_MODE == "allowlist" and email in AUTH_ALLOWED_EMAILS:
                repo.create_user_approval(email, "approved", timestamp)
                repo.update_user_approval(email, "approved", timestamp, "system_allowlist")
                approval = {"email": email, "status": "approved"}
            else:
                repo.create_user_approval(email, "pending", timestamp)
                approval = {"email": email, "status": "pending"}

        status = approval.get("status")
        if status == "pending":
            log_failure(email, "pending_approval", 403)
            raise HTTPException(status_code=403, detail="Your login request is pending admin approval.")
        elif status == "revoked":
            log_failure(email, "revoked_user", 403)
            raise HTTPException(status_code=403, detail="Your access has been revoked by an administrator.")
        elif status != "approved":
            log_failure(email, f"unauthorized_status_{status}", 403)
            raise HTTPException(status_code=403, detail="Forbidden: User is not authorized")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Session Creation Stage 7 failed: %s", e)
        log_failure(email, "db_authorization_failed", 401)
        raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")

    t_stage7 = time.perf_counter()

    # Stage 8: Firebase session-cookie creation
    try:
        expires_in = datetime.timedelta(days=SESSION_COOKIE_DAYS)
        session_cookie = firebase_auth.create_session_cookie(body.id_token, expires_in=expires_in)
    except Exception as e:
        logger.error("Session Creation Stage 8 failed: %s", e)
        log_failure(email, "session_cookie_creation_failed", 401)
        raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")

    t_stage8 = time.perf_counter()

    # Stage 9: Cookie response creation
    try:
        max_age = SESSION_COOKIE_DAYS * 24 * 60 * 60
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_cookie,
            httponly=True,
            secure=SESSION_COOKIE_SECURE,
            samesite="lax",
            path="/",
            max_age=max_age,
        )
        
        # Log successful login
        try:
            repo.log_login_attempt(
                email=email,
                status="success",
                reason="google_login",
                ip_address=ip_address,
                user_agent=user_agent,
                timestamp=timestamp,
            )
        except Exception as log_err:
            logger.error("Failed to write login success audit log: %s", log_err)

        log_auth_audit_event(
            request=request,
            endpoint="/api/auth/session",
            email=email,
            auth_result="success",
            reason="google_login",
            audit_write_attempted=True,
            audit_write_result="success",
            http_status=200,
            correlation_id=correlation_id,
        )

        t_end = time.perf_counter()
        total_ms = (t_end - t_start) * 1000.0
        verify_token_ms = (t_stage4 - t_stage3) * 1000.0
        db_approval_ms = (t_stage7 - t_stage6) * 1000.0
        create_cookie_ms = (t_stage8 - t_stage7) * 1000.0

        logger.info(
            "[SESSION_TIMING] total_ms=%.1f verify_token_ms=%.1f db_approval_ms=%.1f create_cookie_ms=%.1f email=%s",
            total_ms,
            verify_token_ms,
            db_approval_ms,
            create_cookie_ms,
            email,
        )

        response.headers["X-Session-Timing-Total-Ms"] = f"{total_ms:.1f}"
        response.headers["X-Session-Timing-Verify-Token-Ms"] = f"{verify_token_ms:.1f}"
        response.headers["X-Session-Timing-Db-Approval-Ms"] = f"{db_approval_ms:.1f}"
        response.headers["X-Session-Timing-Create-Cookie-Ms"] = f"{create_cookie_ms:.1f}"

        return {"status": "success"}
    except Exception as e:
        logger.error("Session Creation Stage 9 failed: %s", e)
        log_failure(email, "cookie_response_failed", 401)
        raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")

@router.get("/me", response_model=CurrentUser)
async def get_me(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Retrieve minimal current user details if authenticated, recording session restoration in access audit log in background."""
    t_start = time.perf_counter()
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    correlation_id = request.headers.get("x-correlation-id") or uuid.uuid4().hex[:12]
    repo = getattr(request.app.state, "watchlist_repo", None) if hasattr(request.app, "state") else None

    if repo and current_user and current_user.email:
        ip_address = extract_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        timestamp = repo.utc_now_iso()
        
        def async_log_session_restoration():
            try:
                is_dup = repo.should_deduplicate_session_restoration(
                    email=current_user.email,
                    user_agent=user_agent,
                    ip_address=ip_address,
                    window_seconds=1800,
                )
                if not is_dup:
                    repo.log_login_attempt(
                        email=current_user.email,
                        status="success",
                        reason="session_restoration",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        timestamp=timestamp,
                    )
            except Exception as log_err:
                logger.error("Failed to write session restoration audit log: %s", log_err)

        background_tasks.add_task(async_log_session_restoration)

    log_auth_audit_event(
        request=request,
        endpoint="/api/auth/me",
        email=current_user.email if current_user else "unknown",
        auth_result="success",
        reason="session_restoration",
        audit_write_attempted=True,
        audit_write_result="background_queued",
        http_status=200,
        correlation_id=correlation_id,
    )

    t_end = time.perf_counter()
    total_ms = (t_end - t_start) * 1000.0
    response.headers["X-Me-Timing-Total-Ms"] = f"{total_ms:.1f}"
    logger.info("[ME_TIMING] total_ms=%.1f email=%s", total_ms, current_user.email if current_user else "unknown")

    return current_user

@router.post("/logout")
async def logout(body: LogoutRequest, request: Request, response: Response):
    """Log out the current user, clearing session and CSRF cookies."""
    # 1. Require CSRF validation
    validate_csrf(request, body.csrf_token)

    # 2. Validate Origin
    validate_origin(request)

    # 3. Clear session cookie
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
    )

    # 4. Clear CSRF cookie
    response.delete_cookie(
        key="cinequeue_csrf",
        path="/",
        secure=SESSION_COOKIE_SECURE,
        samesite="lax",
    )

    return {"status": "success"}
