import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from firebase_admin import auth as firebase_auth

from app.main import app
from app.config import SESSION_COOKIE_NAME

@pytest.fixture
def client_with_auth():
    # Force AUTH_ENABLED=True during these tests
    with patch.dict("os.environ", {
        "AUTH_ENABLED": "true",
        "AUTH_MODE": "allowlist",
        "AUTH_ALLOWED_EMAILS": "inouye165@gmail.com",
        "AUTH_ALLOWED_ORIGINS": "https://cinequeue-7tvty3vmvq-uw.a.run.app",
        "ENVIRONMENT": "production",
        "SESSION_COOKIE_SECURE": "true"
    }):
        # Reload app configurations to pick up env vars
        import importlib
        import app.config
        importlib.reload(app.config)
        import app.auth
        importlib.reload(app.auth)
        import app.routers.auth
        importlib.reload(app.routers.auth)
        import app.routers.watchlist
        importlib.reload(app.routers.watchlist)
        import app.routers.movies
        importlib.reload(app.routers.movies)
        
        # We need to reload main to recreate App and mount new route dependencies
        import app.main
        importlib.reload(app.main)
        
        with TestClient(app.main.app, base_url="https://testserver") as c:
            yield c
            
        # Restore configuration to defaults
        importlib.reload(app.config)
        importlib.reload(app.auth)
        import app.routers.auth
        importlib.reload(app.routers.auth)
        import app.routers.watchlist
        importlib.reload(app.routers.watchlist)
        import app.routers.movies
        importlib.reload(app.routers.movies)
        importlib.reload(app.auth)
        importlib.reload(app.main)

def test_health_remains_public(client_with_auth):
    """Health endpoint remains public when auth is enabled."""
    response = client_with_auth.get("/api/health")
    assert response.status_code == 200

def test_endpoints_require_authentication(client_with_auth):
    """Application endpoints require authentication."""
    # Search
    response = client_with_auth.get("/api/search?q=matrix")
    assert response.status_code == 401
    
    # Watchlist
    response = client_with_auth.get("/api/watchlist")
    assert response.status_code == 401

def test_csrf_generation(client_with_auth):
    """CSRF endpoint generates token and sets cookie."""
    response = client_with_auth.get("/api/auth/csrf")
    assert response.status_code == 200
    data = response.json()
    assert "csrf_token" in data
    assert "cinequeue_csrf" in response.cookies
    assert response.cookies["cinequeue_csrf"] == data["csrf_token"]

@patch("app.routers.auth.firebase_auth.verify_id_token")
@patch("app.routers.auth.firebase_auth.create_session_cookie")
def test_session_creation_success(mock_create_cookie, mock_verify_token, client_with_auth):
    """Allowlisted user succeeds session creation, secure cookie attributes verified."""
    mock_verify_token.return_value = {
        "uid": "user_abc",
        "email": "inouye165@gmail.com",
        "email_verified": True,
        "auth_time": time.time(),
        "name": "Inouye Test",
        "picture": "http://example.com/pic.jpg"
    }
    mock_create_cookie.return_value = "mocked_session_cookie_value"

    # Get CSRF
    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_id_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify cookie attributes using raw set-cookie header
    set_cookies = response.headers.get_list("set-cookie")
    session_cookie = [c for c in set_cookies if "__Host-cinequeue_session" in c]
    assert len(session_cookie) > 0
    cookie_str = session_cookie[0]
    assert "mocked_session_cookie_value" in cookie_str
    assert "HttpOnly" in cookie_str
    assert "Secure" in cookie_str
    assert "SameSite=lax" in cookie_str or "samesite=lax" in cookie_str.lower()
    assert "Path=/" in cookie_str
    assert "Domain=" not in cookie_str


@patch("app.routers.auth.firebase_auth.verify_id_token")
def test_session_creation_rejects_non_allowlist(mock_verify_token, client_with_auth):
    """Valid Google user not in allowlist gets 403."""
    mock_verify_token.return_value = {
        "uid": "stranger_abc",
        "email": "stranger@gmail.com",
        "email_verified": True,
        "auth_time": time.time()
    }

    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_id_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 403

@patch("app.routers.auth.firebase_auth.verify_id_token")
def test_session_creation_rejects_unverified_email(mock_verify_token, client_with_auth):
    """Unverified email gets 401."""
    mock_verify_token.return_value = {
        "uid": "user_abc",
        "email": "inouye165@gmail.com",
        "email_verified": False,
        "auth_time": time.time()
    }

    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_id_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 401

@patch("app.routers.auth.firebase_auth.verify_id_token")
def test_session_creation_rejects_old_auth_time(mock_verify_token, client_with_auth):
    """Old auth_time (>5 mins) gets 401."""
    mock_verify_token.return_value = {
        "uid": "user_abc",
        "email": "inouye165@gmail.com",
        "email_verified": True,
        "auth_time": time.time() - 360 # 6 minutes ago
    }

    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_id_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 401

def test_session_creation_requires_valid_csrf(client_with_auth):
    """Session creation fails with mismatched CSRF."""
    response = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_id_token", "csrf_token": "wrong_token"},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 401

def test_session_creation_rejects_mismatched_origin(client_with_auth):
    """Session creation rejects invalid Origin."""
    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_id_token", "csrf_token": csrf_token},
        headers={"Origin": "https://malicious.com"}
    )
    assert response.status_code == 401

@patch("app.auth.auth.verify_session_cookie")
def test_me_endpoint_success(mock_verify_cookie, client_with_auth):
    """Verified session user retrieved successfully."""
    mock_verify_cookie.return_value = {
        "uid": "user_abc",
        "email": "inouye165@gmail.com",
        "email_verified": True,
        "name": "Inouye Test",
        "picture": "http://example.com/pic.jpg"
    }

    response = client_with_auth.get(
        "/api/auth/me",
        headers={"Cookie": "__Host-cinequeue_session=session_token_value"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["uid"] == "user_abc"
    assert data["email"] == "inouye165@gmail.com"
    assert data["display_name"] == "Inouye Test"
    # Never return all Firebase token claims
    assert "email_verified" not in data

@patch("app.auth.auth.verify_session_cookie")
def test_me_endpoint_invalid_cookie(mock_verify_cookie, client_with_auth):
    """Invalid session cookie returns 401."""
    mock_verify_cookie.side_effect = Exception("invalid cookie")

    response = client_with_auth.get(
        "/api/auth/me",
        headers={"Cookie": "__Host-cinequeue_session=invalid_token"}
    )
    assert response.status_code == 401

@patch("app.auth.auth.verify_session_cookie")
def test_me_endpoint_revoked_cookie(mock_verify_cookie, client_with_auth):
    """Revoked session cookie returns 401."""
    from firebase_admin.auth import RevokedSessionCookieError
    mock_verify_cookie.side_effect = RevokedSessionCookieError("Session cookie was revoked.")

    response = client_with_auth.get(
        "/api/auth/me",
        headers={"Cookie": "__Host-cinequeue_session=revoked_token"}
    )
    assert response.status_code == 401

@patch("app.auth.auth.verify_session_cookie")
def test_me_endpoint_disabled_user(mock_verify_cookie, client_with_auth):
    """Disabled user account returns 401."""
    from firebase_admin.auth import UserDisabledError
    mock_verify_cookie.side_effect = UserDisabledError("User was disabled.")

    response = client_with_auth.get(
        "/api/auth/me",
        headers={"Cookie": "__Host-cinequeue_session=disabled_token"}
    )
    assert response.status_code == 401

def test_logout_requires_csrf(client_with_auth):
    """Logout endpoint requires valid CSRF."""
    response = client_with_auth.post(
        "/api/auth/logout",
        json={"csrf_token": "invalid"},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 401

def test_logout_clears_cookies(client_with_auth):
    """Logout endpoint clears cookies Instruction: verify clear headers."""
    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_auth.post(
        "/api/auth/logout",
        json={"csrf_token": csrf_token},
        headers={
            "Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app",
            "Cookie": f"__Host-cinequeue_session=session_value; cinequeue_csrf={csrf_token}"
        }
    )
    assert response.status_code == 200
    
    # Verify set-cookie header clears the session cookie
    set_cookies = response.headers.get_list("set-cookie")
    session_cookie = [c for c in set_cookies if "__Host-cinequeue_session" in c]
    assert len(session_cookie) > 0
    cookie_str = session_cookie[0]
    assert "Max-Age=0" in cookie_str or "expires=Thu, 01 Jan 1970 00:00:00 GMT" in cookie_str

@patch("app.auth.auth.verify_session_cookie")
def test_user_watchlist_isolation(mock_verify_cookie, client_with_auth):
    """Ensure User A cannot read or mutate User B data."""
    # Mock authentication for User A
    mock_verify_cookie.return_value = {
        "uid": "user_A",
        "email": "inouye165@gmail.com",
        "email_verified": True
    }

    # Add item to User A's watchlist
    # Mock TMDB details
    app.state.tmdb = MagicMock()
    app.state.tmdb.get_details = MagicMock()
    
    # Use AsyncMock for async methods
    async def mock_get_details(media_type, tmdb_id):
        return {
            "id": tmdb_id,
            "media_type": media_type,
            "title": "Movie A",
            "overview": "Overview A"
        }
    app.state.tmdb.get_details = mock_get_details
    
    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    add_res = client_with_auth.post(
        "/api/watchlist",
        json={"media_type": "movie", "tmdb_id": 111, "title": "Movie A"},
        headers={
            "X-CSRF-Token": csrf_token,
            "Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app",
            "Cookie": f"__Host-cinequeue_session=session_token_value; cinequeue_csrf={csrf_token}"
        }
    )
    assert add_res.status_code == 200

    # Retrieve User A's watchlist
    list_res = client_with_auth.get(
        "/api/watchlist",
        headers={"Cookie": "__Host-cinequeue_session=session_token_value"}
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1
    assert list_res.json()[0]["tmdb_id"] == 111

    # Switch identity to User B
    mock_verify_cookie.return_value = {
        "uid": "user_B",
        "email": "inouye165@gmail.com",
        "email_verified": True
    }
    
    # Retrieve User B's watchlist (should be empty!)
    list_res_B = client_with_auth.get(
        "/api/watchlist",
        headers={"Cookie": "__Host-cinequeue_session=session_token_value"}
    )
    assert list_res_B.status_code == 200
    assert len(list_res_B.json()) == 0

def test_production_fails_closed_if_config_missing():
    """Production configuration fails closed on missing parameters."""
    with patch.dict("os.environ", {
        "AUTH_ENABLED": "true",
        "ENVIRONMENT": "production",
        "AUTH_ALLOWED_EMAILS": "", # Missing allowlist
    }):
        with pytest.raises(ValueError):
            import importlib
            import app.config
            importlib.reload(app.config)
