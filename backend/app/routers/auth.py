import datetime
import logging
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, Depends
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
        if origin not in AUTH_ALLOWED_ORIGINS:
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
        "authDomain": FIREBASE_AUTH_DOMAIN,
        "projectId": FIREBASE_PROJECT_ID,
        "appId": FIREBASE_APP_ID,
        "messagingSenderId": FIREBASE_MESSAGING_SENDER_ID,
    }

@router.get("/csrf")
async def get_csrf(response: Response):
    """Generate and set a readable CSRF token cookie and return it."""
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

@router.post("/session")
async def create_session(body: SessionRequest, request: Request, response: Response):
    """Exchange Firebase ID token for a secure session cookie."""
    # 1. Verify CSRF
    validate_csrf(request, body.csrf_token)

    # 2. Validate Origin
    validate_origin(request)

    if not AUTH_ENABLED:
        # If authentication is disabled, we don't proceed with Firebase verification
        return {"status": "ok", "message": "Auth is disabled"}

    try:
        # 3. Verify Firebase ID token
        # This checks the token signature and expiration
        decoded_token = firebase_auth.verify_id_token(body.id_token)
        
        # 4. Require auth_time no older than 5 minutes
        auth_time = decoded_token.get("auth_time")
        if not auth_time or (time.time() - auth_time) > 5 * 60:
            logger.warning("ID token auth_time is too old: %s", auth_time)
            raise HTTPException(status_code=401, detail="Authentication time is too old")

        # 5. Require email_verified=true
        if not decoded_token.get("email_verified"):
            logger.warning("Email is not verified for user: %s", decoded_token.get("email"))
            raise HTTPException(status_code=401, detail="Email is not verified")

        # 6. Normalize email to lowercase
        email = decoded_token.get("email", "").strip().lower()

        # 7. Apply authorization check
        if AUTH_MODE == "allowlist":
            if email not in AUTH_ALLOWED_EMAILS:
                logger.warning("User %s is not authorized under allowlist", email)
                raise HTTPException(status_code=403, detail="Forbidden: User is not authorized")

        # 9. Create session cookie lasting five days
        expires_in = datetime.timedelta(days=SESSION_COOKIE_DAYS)
        session_cookie = firebase_auth.create_session_cookie(body.id_token, expires_in=expires_in)

        # 10. Set the secure HTTP-only cookie
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
        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Session creation failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid ID token or session generation failed")

@router.get("/me", response_model=CurrentUser)
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    """Retrieve minimal current user details if authenticated."""
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
