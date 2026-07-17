import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyCookie

from app.config import ADMIN_SESSION_COOKIE_NAME, ADMIN_USERNAME

logger = logging.getLogger(__name__)

# Security defaults
PBKDF2_ITERATIONS = 200000

def generate_salt() -> str:
    """Generate a cryptographically secure random salt."""
    return secrets.token_hex(16)

def hash_password(password: str, salt: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256."""
    pwd_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    hashed = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, PBKDF2_ITERATIONS)
    return hashed.hex()

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify password by matching its PBKDF2 hash against stored hash."""
    candidate_hash = hash_password(password, salt)
    return hmac.compare_digest(candidate_hash, password_hash)

def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_hex(32)

# Secure API Cookie Scheme for admin sessions
admin_cookie_scheme = APIKeyCookie(name=ADMIN_SESSION_COOKIE_NAME, auto_error=False)

async def get_current_admin(
    request: Request,
    session_cookie: Optional[str] = Depends(admin_cookie_scheme)
) -> str:
    """
    FastAPI dependency to retrieve and validate the currently logged-in admin.
    Supports either a Bearer Firebase ID token or a session cookie.
    Raises 401 if unauthorized or 403 if authenticated but not an admin.
    """
    auth_header = request.headers.get("Authorization")
    perf = getattr(request.state, "auth_perf", None)

    # 1. Bearer token auth path
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split("Bearer ")[1].strip()
        if not token:
            raise HTTPException(status_code=401, detail="Bearer token is empty")

        tv_start = time.perf_counter()
        if perf:
            perf["timings"]["firebase_token_verification_started"] = tv_start

        try:
            from firebase_admin import auth as firebase_auth
            decoded_token = firebase_auth.verify_id_token(token)
            
            tv_end = time.perf_counter()
            if perf:
                perf["timings"]["firebase_token_verification_completed"] = tv_end
                perf["token_verification_duration_ms"] = (tv_end - tv_start) * 1000.0

            email = decoded_token.get("email")
            if not email:
                raise HTTPException(status_code=401, detail="Invalid token claims: email missing")

            email_normalized = email.strip().lower()
            admin_username_normalized = ADMIN_USERNAME.strip().lower()

            db_start = time.perf_counter()
            if perf:
                perf["timings"]["admin_lookup_started"] = db_start

            repo = request.app.state.watchlist_repo
            db_admin = repo.get_admin_user(email_normalized)
            is_admin = bool(db_admin or email_normalized == admin_username_normalized)

            db_end = time.perf_counter()
            if perf:
                perf["timings"]["admin_lookup_completed"] = db_end
                perf["admin_lookup_duration_ms"] = (db_end - db_start) * 1000.0

            logger.info(
                "Admin lookup via Firebase token for email: %s. DB record found: %s, matches ADMIN_USERNAME: %s, result: %s",
                email_normalized,
                bool(db_admin),
                email_normalized == admin_username_normalized,
                is_admin
            )

            if not is_admin:
                logger.warning("User %s is not an authorized administrator", email_normalized)
                raise HTTPException(status_code=403, detail="Not authorized as an administrator")

            return email_normalized
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Firebase ID token verification failed: %s", e)
            raise HTTPException(status_code=401, detail="Invalid ID token")

    # 2. Traditional Cookie fallback path
    if not session_cookie:
        logger.warning("Admin session cookie is missing")
        raise HTTPException(status_code=401, detail="Admin session required")

    # Time database lookup
    db_start = time.perf_counter()
    if perf:
        perf["timings"]["admin_lookup_started"] = db_start

    repo = request.app.state.watchlist_repo
    session = repo.get_admin_session(session_cookie)

    db_end = time.perf_counter()
    if perf:
        perf["timings"]["admin_lookup_completed"] = db_end
        perf["admin_lookup_duration_ms"] = (db_end - db_start) * 1000.0

    if not session:
        logger.warning("Admin session not found in database")
        raise HTTPException(status_code=401, detail="Invalid admin session")

    # Verify expiration
    expires_at_str = session.get("expires_at")
    if not expires_at_str:
        logger.warning("Admin session missing expires_at field")
        raise HTTPException(status_code=401, detail="Invalid admin session structure")

    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(timezone.utc) > expires_at:
            logger.warning("Admin session has expired")
            # Clean up expired session
            repo.delete_admin_session(session_cookie)
            raise HTTPException(status_code=401, detail="Admin session expired")
    except ValueError as e:
        logger.error("Failed to parse expires_at ISO string: %s", e)
        raise HTTPException(status_code=401, detail="Invalid admin session")

    username = session["username"]
    # Check that this admin user still exists in the database or matches ADMIN_USERNAME
    if not (repo.get_admin_user(username) or username.strip().lower() == ADMIN_USERNAME.strip().lower()):
        logger.warning("Admin session belongs to a deleted/revoked administrator: %s", username)
        repo.delete_admin_session(session_cookie)
        raise HTTPException(status_code=401, detail="Administrator privileges revoked")

    logger.info("Admin session validated for user: %s", username)
    return username
