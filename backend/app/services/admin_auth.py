import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyCookie

from app.config import ADMIN_SESSION_COOKIE_NAME

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
    Raises 401 if unauthorized or if session is expired.
    """
    if not session_cookie:
        logger.warning("Admin session cookie is missing")
        raise HTTPException(status_code=401, detail="Admin session required")

    repo = request.app.state.watchlist_repo
    session = repo.get_admin_session(session_cookie)
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

    return session["username"]
