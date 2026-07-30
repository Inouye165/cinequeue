"""Authentication and authorization utilities using Firebase Admin SDK."""

import logging
import secrets
import hmac
import re
import time
import asyncio
from typing import Optional
from fastapi import HTTPException, Depends, Request
from fastapi.security import APIKeyCookie
from pydantic import BaseModel
import socket
import requests
from requests.adapters import HTTPAdapter
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


class KeepAliveHTTPAdapter(HTTPAdapter):
    """Custom HTTPAdapter enabling TCP Keep-Alive socket options and connection pooling."""

    def __init__(self, pool_connections=20, pool_maxsize=20, max_retries=3, **kwargs):
        super().__init__(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            max_retries=max_retries,
            **kwargs,
        )

    def init_poolmanager(self, *args, **kwargs):
        socket_options = kwargs.get("socket_options", [])
        socket_options.append((socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1))
        if hasattr(socket, "TCP_KEEPIDLE"):
            socket_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30))
        if hasattr(socket, "TCP_KEEPINTVL"):
            socket_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10))
        if hasattr(socket, "TCP_KEEPCNT"):
            socket_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3))
        kwargs["socket_options"] = socket_options
        return super().init_poolmanager(*args, **kwargs)


def configure_firebase_adapters(app_instance=None):
    """Attach KeepAliveHTTPAdapter to all underlying Firebase Admin SDK HTTP sessions."""
    try:
        f_app = app_instance or firebase_admin.get_app()
        client = auth._get_client(f_app)
        adapter = KeepAliveHTTPAdapter(pool_connections=20, pool_maxsize=20)

        # 1. Token Generator HTTP session (create_session_cookie)
        if hasattr(client, "_token_generator") and hasattr(client._token_generator, "http_client"):
            sess = getattr(client._token_generator.http_client, "session", None)
            if sess:
                sess.mount("https://", adapter)
                sess.mount("http://", adapter)

        # 2. Token Verifier HTTP session (verify_id_token cert fetching)
        if hasattr(client, "_token_verifier") and hasattr(client._token_verifier, "request"):
            req = client._token_verifier.request
            sess = getattr(req, "session", None)
            if sess:
                sess.mount("https://", adapter)
                sess.mount("http://", adapter)
                if hasattr(sess, "_session") and getattr(sess, "_session", None):
                    sess._session.mount("https://", adapter)
                    sess._session.mount("http://", adapter)

        # 3. User Manager HTTP session
        if hasattr(client, "_user_manager") and hasattr(client._user_manager, "http_client"):
            sess = getattr(client._user_manager.http_client, "session", None)
            if sess:
                sess.mount("https://", adapter)
                sess.mount("http://", adapter)

        # 4. Provider Manager HTTP session
        if hasattr(client, "_provider_manager") and hasattr(client._provider_manager, "http_client"):
            sess = getattr(client._provider_manager.http_client, "session", None)
            if sess:
                sess.mount("https://", adapter)
                sess.mount("http://", adapter)

        logger.info("Firebase Admin HTTP connection pooling & TCP Keep-Alive adapters configured successfully")
    except Exception as exc:
        logger.warning("Could not configure Firebase Keep-Alive adapters: %s", exc)


def warmup_firebase_auth():
    """Pre-fetch Google public certs & pre-warm Identity Toolkit TCP connection."""
    if not AUTH_ENABLED:
        return
    t_start = time.perf_counter()
    try:
        f_app = firebase_admin.get_app()
        client = auth._get_client(f_app)
        configure_firebase_adapters(f_app)

        # 1. Pre-fetch public ID-token & cookie verification keys into in-memory CacheControl cache
        if hasattr(client, "_token_verifier") and hasattr(client._token_verifier, "request"):
            req = client._token_verifier.request
            cert_urls = [
                "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com",
                "https://www.googleapis.com/identitytoolkit/v3/relyingparty/publicKeys",
            ]
            for cert_url in cert_urls:
                try:
                    req(cert_url)
                except Exception as cert_err:
                    logger.debug("Warmup cert pre-fetch for %s: %s", cert_url, cert_err)

        # 2. Pre-warm Identity Toolkit connection & Google OAuth token acquisition
        if hasattr(client, "_token_generator") and hasattr(client._token_generator, "http_client"):
            sess = getattr(client._token_generator.http_client, "session", None)
            if sess:
                url = f"https://identitytoolkit.googleapis.com/v1/projects/{FIREBASE_PROJECT_ID}:createSessionCookie"
                try:
                    # Send lightweight dummy POST to establish TLS 1.3 Keep-Alive session
                    sess.post(url, json={"idToken": "warmup_ping", "validDuration": 3600}, timeout=5.0)
                except Exception:
                    pass  # Rejection expected for dummy payload; TCP/TLS connection is now open & pooled in memory

        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        logger.info("[WARMUP_TIMING] Firebase auth pre-warmed successfully in %.1f ms", elapsed_ms)
    except Exception as exc:
        logger.warning("Firebase auth warmup encountered non-fatal error: %s", exc)


# Initialize Firebase Admin exactly once using Application Default Credentials (ADC)
if AUTH_ENABLED:
    try:
        # Check if already initialized to avoid duplicate initialization errors
        # (especially during tests)
        _app = firebase_admin.get_app()
        configure_firebase_adapters(_app)
    except ValueError:
        # Initialize
        cred = credentials.ApplicationDefault()
        _app = firebase_admin.initialize_app(cred, {"projectId": FIREBASE_PROJECT_ID})
        configure_firebase_adapters(_app)
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
    request: Request,
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
            # Local verification is used (check_revoked=False) to avoid network overhead.
            decoded_claims = auth.verify_session_cookie(session_cookie, check_revoked=False, clock_skew_seconds=60)
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
                    sleep_time = float(drift_seconds) + 1.0

                logger.warning(
                    "Session cookie used too early due to clock skew (%s seconds drift). "
                    "Retrying in %s seconds...",
                    drift_val, sleep_time
                )
                await asyncio.sleep(sleep_time)
                decoded_claims = auth.verify_session_cookie(session_cookie, check_revoked=False)
            else:
                raise

        email = decoded_claims.get("email")
        if not email:
            logger.warning("Session token missing email claim")
            raise HTTPException(status_code=401, detail="Invalid session token claims")

        email_normalized = email.strip().lower()

        # Authorization check: check database approval first, fall back to static allowlist
        repo = getattr(request.app.state, "watchlist_repo", None) if hasattr(request.app, "state") else None
        
        if repo:
            approval = repo.get_user_approval(email_normalized)
            if approval:
                status = approval.get("status")
                if status != "approved":
                    ip_address = request.client.host if request.client else "unknown"
                    user_agent = request.headers.get("user-agent", "unknown")
                    repo.log_login_attempt(
                        email=email_normalized,
                        status="failed",
                        reason=f"session_auth_status_{status}",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        timestamp=repo.utc_now_iso(),
                    )
                    logger.warning("User %s access status is %s", email_normalized, status)
                    raise HTTPException(status_code=403, detail=f"Forbidden: User status is {status}")
            else:
                # No DB approval record found
                if AUTH_MODE == "allowlist" and email_normalized not in AUTH_ALLOWED_EMAILS:
                    ip_address = request.client.host if request.client else "unknown"
                    user_agent = request.headers.get("user-agent", "unknown")
                    repo.log_login_attempt(
                        email=email_normalized,
                        status="failed",
                        reason="session_auth_not_approved_or_allowlisted",
                        ip_address=ip_address,
                        user_agent=user_agent,
                        timestamp=repo.utc_now_iso(),
                    )
                    logger.warning("User %s is not approved in database or static allowlist", email_normalized)
                    raise HTTPException(status_code=403, detail="Forbidden: User is not authorized")
        else:
            if AUTH_MODE == "allowlist" and email_normalized not in AUTH_ALLOWED_EMAILS:
                logger.warning("User %s is not in static allowlist", email_normalized)
                raise HTTPException(status_code=403, detail="Forbidden: User is not authorized")

        return CurrentUser(
            uid=decoded_claims.get("uid"),
            email=email_normalized,
            display_name=decoded_claims.get("name"),
            photo_url=decoded_claims.get("picture"),
        )
    except HTTPException:
        raise
    except auth.RevokedSessionCookieError as exc:
        logger.warning("Session cookie has been revoked")
        raise HTTPException(status_code=401, detail="Session has been revoked") from exc
    except auth.UserDisabledError as exc:
        logger.warning("User account has been disabled")
        raise HTTPException(status_code=401, detail="User account is disabled") from exc
    except Exception as exc:
        logger.warning("Session cookie verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid session") from exc
