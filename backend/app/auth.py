"""Authentication and authorization utilities using Firebase Admin SDK."""

import logging
import secrets
import hmac
import re
import time
from typing import Optional
from fastapi import HTTPException, Depends
from fastapi.security import APIKeyCookie
from pydantic import BaseModel
import firebase_admin
from firebase_admin import auth, credentials

from app.config import (
    AUTH_ENABLED,
    AUTH_MODE,
    AUTH_ALLOWED_EMAILS,
    FIREBASE_PROJECT_ID,
    SESSION_COOKIE_NAME,
)

logger = logging.getLogger(__name__)

# Initialize Firebase Admin exactly once using Application Default Credentials (ADC)
if AUTH_ENABLED:
    try:
        # Check if already initialized to avoid duplicate initialization errors
        # (especially during tests)
        firebase_admin.get_app()
    except ValueError:
        # Initialize
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        logger.info(
            "Firebase Admin SDK initialized successfully for project: %s",
            FIREBASE_PROJECT_ID
        )


class CurrentUser(BaseModel):
    """Pydantic model representing the authenticated current user."""
    uid: str
    email: str
    display_name: Optional[str] = None
    photo_url: Optional[str] = None


# Secure session cookie setup
session_cookie_scheme = APIKeyCookie(name=SESSION_COOKIE_NAME, auto_error=False)


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(token_a: str, token_b: str) -> bool:
    """Compare two CSRF tokens in constant-time."""
    if not token_a or not token_b:
        return False
    return hmac.compare_digest(token_a, token_b)


async def get_current_user(
    session_cookie: Optional[str] = Depends(session_cookie_scheme)
) -> CurrentUser:
    """
    FastAPI dependency to retrieve the authenticated user.
    If AUTH_ENABLED is False, returns a mock user.
    """
    if not AUTH_ENABLED:
        return CurrentUser(
            uid="local_test_user",
            email="local@test.com",
            display_name="Local Developer",
            photo_url=None
        )

    if not session_cookie:
        logger.warning("Missing session cookie")
        raise HTTPException(status_code=401, detail="Session cookie is missing")

    try:
        try:
            # Verify the session cookie, checking for revoked or disabled sessions.
            # This will query the Identity Platform backend and respects the
            # roles/firebaseauth.viewer permission.
            decoded_claims = auth.verify_session_cookie(session_cookie, check_revoked=True)
        except Exception as e:  # pylint: disable=broad-exception-caught
            if "Token used too early" in str(e):
                match = re.search(r"Token used too early,\s*(\d+)\s*<\s*(\d+)", str(e))
                sleep_time = 5.0
                drift_val = "unknown"
                if match:
                    local_time_val = int(match.group(1))
                    token_time_val = int(match.group(2))
                    drift_seconds = token_time_val - local_time_val
                    drift_val = str(drift_seconds)
                    sleep_time = float(drift_seconds) + 2.0

                logger.warning(
                    "Session cookie used too early due to clock skew (%s seconds drift). "
                    "Retrying in %s seconds...",
                    drift_val, sleep_time
                )
                time.sleep(sleep_time)
                decoded_claims = auth.verify_session_cookie(session_cookie, check_revoked=True)
            else:
                raise

        email = decoded_claims.get("email")
        if not email:
            logger.warning("Session token missing email claim")
            raise HTTPException(status_code=401, detail="Invalid session token claims")

        email_normalized = email.strip().lower()

        # Authorization check
        if AUTH_MODE == "allowlist":
            if email_normalized not in AUTH_ALLOWED_EMAILS:
                logger.warning("User %s is not in the allowlist", email_normalized)
                raise HTTPException(status_code=403, detail="Forbidden: User is not authorized")

        return CurrentUser(
            uid=decoded_claims.get("uid"),
            email=email_normalized,
            display_name=decoded_claims.get("name"),
            photo_url=decoded_claims.get("picture"),
        )
    except auth.RevokedSessionCookieError as exc:
        logger.warning("Session cookie has been revoked")
        raise HTTPException(status_code=401, detail="Session has been revoked") from exc
    except auth.UserDisabledError as exc:
        logger.warning("User account has been disabled")
        raise HTTPException(status_code=401, detail="User account is disabled") from exc
    except Exception as exc:
        logger.warning("Session cookie verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid session") from exc
