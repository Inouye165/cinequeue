"""Tests for the backend authentication and authorization flow."""

# pylint: disable=redefined-outer-name,import-outside-toplevel

import time
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_auth():
    """Fixture to provide a test client with mock Firebase Auth enabled."""
    # Force AUTH_ENABLED=True during these tests
    with patch.dict("os.environ", {
        "AUTH_ENABLED": "true",
        "AUTH_MODE": "allowlist",
        "AUTH_ALLOWED_EMAILS": "inouye165@gmail.com",
        "AUTH_ALLOWED_ORIGINS": "https://cinequeue-7tvty3vmvq-uw.a.run.app",
        "ENVIRONMENT": "production",
        "SESSION_COOKIE_SECURE": "true",
        "FIREBASE_API_KEY": "mock_firebase_api_key",
        "ADMIN_PASSWORD": "mock_admin_password_2026"
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
            app.main.app.state.tmdb = AsyncMock()
            yield c

    # Reload only after patch.dict restores the unauthenticated test environment.
    importlib.reload(app.config)
    importlib.reload(app.auth)
    import app.routers.auth
    importlib.reload(app.routers.auth)
    import app.routers.watchlist
    importlib.reload(app.routers.watchlist)
    import app.routers.movies
    importlib.reload(app.routers.movies)
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
        "auth_time": time.time() - 360  # 6 minutes ago
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
    # Mock TMDB details on the active reloaded app instance
    import app.main
    app.main.app.state.tmdb = AsyncMock()
    app.main.app.state.tmdb.get_details = AsyncMock()

    # Use AsyncMock for async methods
    async def mock_get_details(media_type, tmdb_id):
        return {
            "id": tmdb_id,
            "media_type": media_type,
            "title": "Movie A",
            "overview": "Overview A"
        }
    app.main.app.state.tmdb.get_details = mock_get_details

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
    list_res_b = client_with_auth.get(
        "/api/watchlist",
        headers={"Cookie": "__Host-cinequeue_session=session_token_value"}
    )
    assert list_res_b.status_code == 200
    assert len(list_res_b.json()) == 0


def test_production_fails_closed_if_config_missing():
    """Production configuration fails closed on missing parameters."""
    with patch.dict("os.environ", {
        "AUTH_ENABLED": "true",
        "ENVIRONMENT": "production",
        "AUTH_ALLOWED_EMAILS": "",  # Missing allowlist
    }):
        with pytest.raises(ValueError):
            import importlib
            import app.config
            importlib.reload(app.config)


def test_config_auth_domain_local(client_with_auth):
    """Config endpoint returns FIREBASE_AUTH_DOMAIN when PUBLIC_AUTH_DOMAIN is not configured."""
    with patch("app.routers.auth.PUBLIC_AUTH_DOMAIN", ""):
        response = client_with_auth.get("/api/auth/config")
        assert response.status_code == 200
        assert response.json()["authDomain"] == "cinequeue-inouye-2026.firebaseapp.com"


def test_config_auth_domain_production(client_with_auth):
    """Config endpoint always returns FIREBASE_AUTH_DOMAIN for Firebase SDK auth, even when PUBLIC_AUTH_DOMAIN is configured."""
    with patch("app.routers.auth.PUBLIC_AUTH_DOMAIN", "cinequeue-568212960791.us-west1.run.app"):
        response = client_with_auth.get("/api/auth/config")
        assert response.status_code == 200
        assert response.json()["authDomain"] == "cinequeue-inouye-2026.firebaseapp.com"


@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_get(mock_request, client_with_auth):
    """Proxy forwards GET requests transparently, stripping Host, Cookie, and Authorization."""
    import httpx
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b"mocked-redirect-iframe-payload"
    mock_resp.headers = {
        "content-type": "text/html",
        "cache-control": "no-cache",
        "location": "https://google.com/oauth",
        "set-cookie": "state=123"
    }
    mock_request.return_value = mock_resp

    # Make request to proxy with query params and sensitive headers
    response = client_with_auth.get(
        "/__/auth/handler?apiKey=123&state=abc",
        headers={
            "Cookie": "__Host-cinequeue_session=token; cinequeue_csrf=token",
            "Authorization": "Bearer token",
            "X-Custom-Header": "custom-val"
        }
    )

    assert response.status_code == 200
    assert response.content == b"mocked-redirect-iframe-payload"
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["location"] == "https://google.com/oauth"
    assert response.headers["set-cookie"] == "state=123"

    # Assert request call details
    mock_request.assert_called_once()
    called_args, called_kwargs = mock_request.call_args
    assert called_kwargs["method"] == "GET"
    assert called_kwargs["url"] == "https://cinequeue-inouye-2026.firebaseapp.com/__/auth/handler?apiKey=123&state=abc"
    # Ensure Host, Cookie, and Authorization are NOT forwarded
    assert "host" not in called_kwargs["headers"]
    assert "cookie" not in called_kwargs["headers"]
    assert "authorization" not in called_kwargs["headers"]
    # Verify custom headers ARE forwarded
    assert called_kwargs["headers"]["x-custom-header"] == "custom-val"


@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_post(mock_request, client_with_auth):
    """Proxy forwards POST requests transparently preserving the body."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b"success"
    mock_resp.headers = {"content-type": "application/json"}
    mock_request.return_value = mock_resp

    response = client_with_auth.post(
        "/__/auth/handler",
        content=b"post-body-content",
        headers={"Content-Type": "application/octet-stream"}
    )

    assert response.status_code == 200
    assert response.content == b"success"
    called_args, called_kwargs = mock_request.call_args
    assert called_kwargs["method"] == "POST"
    assert called_kwargs["content"] == b"post-body-content"
    assert called_kwargs["headers"]["content-type"] == "application/octet-stream"


def test_firebase_auth_proxy_method_not_allowed(client_with_auth):
    """Proxy rejects non-GET/POST methods with 405 Method Not Allowed."""
    response = client_with_auth.delete("/__/auth/handler")
    assert response.status_code == 405


@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_upstream_failure(mock_request, client_with_auth):
    """Proxy handles upstream failures by returning 502 Bad Gateway."""
    import httpx
    mock_request.side_effect = httpx.RequestError("DNS resolution failed")
    response = client_with_auth.get("/__/auth/handler")
    assert response.status_code == 502


@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_cookie_filtering(mock_request, client_with_auth):
    """Proxy filters out Cinequeue cookies but preserves and forwards other cookies."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b"cookie-ok"
    mock_resp.headers = {"content-type": "text/html"}
    mock_request.return_value = mock_resp

    response = client_with_auth.get(
        "/__/auth/handler",
        headers={
            "Cookie": "__Host-cinequeue_session=val; gaps=123; cinequeue_csrf=val2; custom_cookie=abc"
        }
    )

    assert response.status_code == 200
    called_args, called_kwargs = mock_request.call_args
    # Verify only gaps=123 and custom_cookie=abc are forwarded
    forwarded_cookie = called_kwargs["headers"]["cookie"]
    assert "gaps=123" in forwarded_cookie
    assert "custom_cookie=abc" in forwarded_cookie
    assert "__Host-cinequeue_session" not in forwarded_cookie
    assert "cinequeue_csrf" not in forwarded_cookie


@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_headers_rewriting(mock_request, client_with_auth):
    """Proxy rewrites upstream Location and Set-Cookie Domain attributes."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 302
    mock_resp.content = b""
    mock_resp.headers = {
        "location": "https://cinequeue-inouye-2026.firebaseapp.com/__/auth/handler?state=abc",
        "set-cookie": "GAPS=xyz; Domain=cinequeue-inouye-2026.firebaseapp.com; Path=/; Secure"
    }
    mock_request.return_value = mock_resp

    # Scenario A: PUBLIC_AUTH_DOMAIN is configured (Production)
    with patch("app.main.PUBLIC_AUTH_DOMAIN", "cinequeue-568212960791.us-west1.run.app"):
        response = client_with_auth.get("/__/auth/handler", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "https://cinequeue-568212960791.us-west1.run.app/__/auth/handler?state=abc"
        # Domain should be replaced with PUBLIC_AUTH_DOMAIN
        assert "domain=cinequeue-568212960791.us-west1.run.app" in response.headers["set-cookie"].lower()
        assert "cinequeue-inouye-2026.firebaseapp.com" not in response.headers["set-cookie"].lower()

    # Scenario B: PUBLIC_AUTH_DOMAIN is empty (Local dev / fallback)
    with patch("app.main.PUBLIC_AUTH_DOMAIN", ""):
        response = client_with_auth.get("/__/auth/handler", follow_redirects=False)
        assert response.status_code == 302
        # Location should fallback to request netloc (testserver)
        assert response.headers["location"] == "https://testserver/__/auth/handler?state=abc"
        # Domain should be removed entirely
        assert "domain=" not in response.headers["set-cookie"].lower()

@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_csp_bypass_no_upstream(mock_request, client_with_auth):
    """If Firebase returns no CSP, do not add Cinequeue's CSP to that proxied response."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b"firebase-auth-page"
    mock_resp.headers = {"content-type": "text/html"}
    mock_request.return_value = mock_resp

    response = client_with_auth.get("/__/auth/handler")
    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
    assert "Content-Security-Policy-Report-Only" not in response.headers


@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_csp_bypass_with_upstream(mock_request, client_with_auth):
    """Preserve and return Firebase's upstream Content-Security-Policy header if one is present."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b"firebase-auth-page"
    mock_resp.headers = {
        "content-type": "text/html",
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline';"
    }
    mock_request.return_value = mock_resp

    response = client_with_auth.get("/__/auth/handler")
    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; script-src 'unsafe-inline';"


@patch("httpx.AsyncClient.request")
def test_firebase_auth_proxy_csp_bypass_with_report_only(mock_request, client_with_auth):
    """Also preserve Content-Security-Policy-Report-Only if returned upstream."""
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.content = b"firebase-auth-page"
    mock_resp.headers = {
        "content-type": "text/html",
        "Content-Security-Policy-Report-Only": "default-src 'none'; report-uri /csp-violation"
    }
    mock_request.return_value = mock_resp

    response = client_with_auth.get("/__/auth/handler")
    assert response.status_code == 200
    assert response.headers["Content-Security-Policy-Report-Only"] == "default-src 'none'; report-uri /csp-violation"
    assert "Content-Security-Policy" not in response.headers


def test_normal_route_retains_strict_csp(client_with_auth):
    """Normal Cinequeue routes retain the existing strict CSP."""
    response = client_with_auth.get("/api/health")
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self' https://apis.google.com https://www.gstatic.com" in csp
    # Ensure no global 'unsafe-inline' policy is introduced in script-src.
    directives = [d.strip() for d in csp.split(";")]
    script_src = [d for d in directives if d.startswith("script-src")]
    assert len(script_src) == 1
    assert "'unsafe-inline'" not in script_src[0]


@patch("app.routers.auth.firebase_auth.verify_id_token")
@patch("app.routers.auth.firebase_auth.create_session_cookie")
def test_origin_validation_policy(mock_create_cookie, mock_verify_token):
    """Test all origin validation scenarios for /api/auth/session."""
    import importlib
    import app.config
    import app.routers.auth
    import app.main

    try:
        with patch.dict("os.environ", {
            "AUTH_ENABLED": "true",
            "ENVIRONMENT": "production",
            "AUTH_ALLOWED_EMAILS": "inouye165@gmail.com",
            "AUTH_ALLOWED_ORIGINS": "https://cinequeue-568212960791.us-west1.run.app,http://localhost:5180,http://127.0.0.1:5180",
            "FIREBASE_API_KEY": "mock_firebase_api_key",
            "ADMIN_PASSWORD": "mock_admin_password_2026",
        }):
            importlib.reload(app.config)
            importlib.reload(app.routers.auth)
            importlib.reload(app.main)

            from fastapi.testclient import TestClient
            with TestClient(app.main.app, base_url="https://testserver") as client:
                mock_verify_token.return_value = {
                    "uid": "user_abc",
                    "email": "inouye165@gmail.com",
                    "email_verified": True,
                    "auth_time": time.time(),
                }
                mock_create_cookie.return_value = "mock_session_cookie"

                csrf_res = client.get("/api/auth/csrf")
                csrf_token = csrf_res.json()["csrf_token"]

                # 1. Cloud Run production origin is accepted
                mock_verify_token.reset_mock()
                res = client.post(
                    "/api/auth/session",
                    json={"id_token": "dummy_id_prod", "csrf_token": csrf_token},
                    headers={"Origin": "https://cinequeue-568212960791.us-west1.run.app"}
                )
                assert res.status_code == 200
                mock_verify_token.assert_called_once_with("dummy_id_prod", clock_skew_seconds=60)

                # 2. localhost remains accepted where intended
                mock_verify_token.reset_mock()
                res = client.post(
                    "/api/auth/session",
                    json={"id_token": "dummy_id_local", "csrf_token": csrf_token},
                    headers={"Origin": "http://localhost:5180"}
                )
                assert res.status_code == 200
                mock_verify_token.assert_called_once_with("dummy_id_local", clock_skew_seconds=60)

                # 3. an unknown origin is rejected
                mock_verify_token.reset_mock()
                res = client.post(
                    "/api/auth/session",
                    json={"id_token": "dummy_id_unknown", "csrf_token": csrf_token},
                    headers={"Origin": "https://unknown-domain.com"}
                )
                assert res.status_code == 401
                assert res.json()["detail"] == "Origin not allowed"
                mock_verify_token.assert_not_called()

                # 4. a missing origin is handled according to the existing policy
                mock_verify_token.reset_mock()
                res = client.post(
                    "/api/auth/session",
                    json={"id_token": "dummy_id_missing", "csrf_token": csrf_token}
                )
                assert res.status_code == 401
                assert res.json()["detail"] == "Missing Origin header"
                mock_verify_token.assert_not_called()
    finally:
        # Restore environment settings by reloading after patch is gone
        importlib.reload(app.config)
        importlib.reload(app.routers.auth)
        importlib.reload(app.main)


@patch("app.routers.auth.firebase_auth.verify_id_token")
@patch("app.routers.auth.firebase_auth.create_session_cookie")
def test_approved_user_fresh_login_audit_log(mock_create_cookie, mock_verify_token, client_with_auth):
    """Approved user fresh login creates a success google_login audit log."""
    mock_verify_token.return_value = {
        "uid": "user_approved",
        "email": "inouye165@gmail.com",
        "email_verified": True,
        "auth_time": time.time(),
        "name": "Approved User"
    }
    mock_create_cookie.return_value = "mock_session_val"

    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    res = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "valid_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert res.status_code == 200

    repo = client_with_auth.app.state.watchlist_repo
    logs = repo.list_login_logs(email="inouye165@gmail.com")
    assert len(logs) > 0
    latest = logs[0]
    assert latest["email"] == "inouye165@gmail.com"
    assert latest["status"] == "success"
    assert latest["reason"] == "google_login"


@patch("app.auth.auth.verify_session_cookie")
def test_session_restoration_audit_log(mock_verify_cookie, client_with_auth):
    """Session restoration via GET /api/auth/me creates a success session_restoration audit log."""
    from app.config import SESSION_COOKIE_NAME
    mock_verify_cookie.return_value = {
        "uid": "user_approved",
        "email": "inouye165@gmail.com",
        "name": "Approved User"
    }
    client_with_auth.cookies.set(SESSION_COOKIE_NAME, "valid_session_cookie")

    res = client_with_auth.get("/api/auth/me")
    assert res.status_code == 200

    repo = client_with_auth.app.state.watchlist_repo
    logs = repo.list_login_logs(email="inouye165@gmail.com")
    assert len(logs) > 0
    latest = logs[0]
    assert latest["email"] == "inouye165@gmail.com"
    assert latest["status"] == "success"
    assert latest["reason"] == "session_restoration"


@patch("app.routers.auth.firebase_auth.verify_id_token")
def test_pending_user_login_audit_log(mock_verify_token, client_with_auth):
    """New user first login creates pending_approval audit log and returns 403."""
    mock_verify_token.return_value = {
        "uid": "user_pending",
        "email": "pending_user@example.com",
        "email_verified": True,
        "auth_time": time.time(),
        "name": "Pending User"
    }

    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    res = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "valid_pending_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert res.status_code == 403

    repo = client_with_auth.app.state.watchlist_repo
    logs = repo.list_login_logs(email="pending_user@example.com")
    assert len(logs) > 0
    latest = logs[0]
    assert latest["email"] == "pending_user@example.com"
    assert latest["status"] == "failed"
    assert latest["reason"] == "pending_approval"


@patch("app.routers.auth.firebase_auth.verify_id_token")
def test_revoked_user_login_audit_log(mock_verify_token, client_with_auth):
    """Revoked user login attempt creates revoked_user audit log and returns 403."""
    repo = client_with_auth.app.state.watchlist_repo
    now = repo.utc_now_iso()
    repo.create_user_approval("revoked_user@example.com", "pending", now)
    repo.update_user_approval("revoked_user@example.com", "revoked", now, "admin")

    mock_verify_token.return_value = {
        "uid": "user_revoked",
        "email": "revoked_user@example.com",
        "email_verified": True,
        "auth_time": time.time(),
        "name": "Revoked User"
    }

    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    res = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "valid_revoked_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert res.status_code == 403

    logs = repo.list_login_logs(email="revoked_user@example.com")
    assert len(logs) > 0
    latest = logs[0]
    assert latest["email"] == "revoked_user@example.com"
    assert latest["status"] == "failed"
    assert latest["reason"] == "revoked_user"


def test_csrf_failure_audit_log_unknown_email(client_with_auth):
    """CSRF failure creates audit log with email set to unknown."""
    res = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "token", "csrf_token": "bad_csrf"},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert res.status_code == 401

    repo = client_with_auth.app.state.watchlist_repo
    logs = repo.list_login_logs(email="unknown")
    assert len(logs) > 0
    latest = logs[0]
    assert latest["email"] == "unknown"
    assert latest["status"] == "failed"
    assert latest["reason"] == "csrf_validation_failed"


def test_origin_failure_audit_log_unknown_email(client_with_auth):
    """Origin header failure creates audit log with email set to unknown."""
    csrf_res = client_with_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    res = client_with_auth.post(
        "/api/auth/session",
        json={"id_token": "token", "csrf_token": csrf_token},
        headers={"Origin": "https://disallowed-origin.com"}
    )
    assert res.status_code == 401

    repo = client_with_auth.app.state.watchlist_repo
    logs = repo.list_login_logs(email="unknown")
    assert len(logs) > 0
    latest = logs[0]
    assert latest["email"] == "unknown"
    assert latest["status"] == "failed"
    assert latest["reason"] == "origin_validation_failed"


def test_firestore_audit_write_failure_handling(client_with_auth):
    """Exception inside log_login_attempt is caught gracefully without breaking log_failure response."""
    repo = client_with_auth.app.state.watchlist_repo
    with patch.object(repo, "log_login_attempt", side_effect=Exception("Database connection error")):
        res = client_with_auth.post(
            "/api/auth/session",
            json={"id_token": "token", "csrf_token": "invalid_csrf"},
            headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
        )
        assert res.status_code == 401


def test_admin_log_pagination_and_filtering(client_with_auth):
    """Audit log repository supports limit, status, and email filtering."""
    repo = client_with_auth.app.state.watchlist_repo
    now = repo.utc_now_iso()

    repo.log_login_attempt("user1@example.com", "success", "google_login", "1.1.1.1", "agent", now)
    repo.log_login_attempt("user2@example.com", "failed", "pending_approval", "2.2.2.2", "agent", now)
    repo.log_login_attempt("user1@example.com", "failed", "csrf_validation_failed", "1.1.1.1", "agent", now)

    all_logs = repo.list_login_logs(limit=10)
    assert len(all_logs) >= 3

    u1_logs = repo.list_login_logs(email="user1@example.com")
    assert all(l["email"] == "user1@example.com" for l in u1_logs)

    failed_logs = repo.list_login_logs(status="failed")
    assert all(l["status"] == "failed" for l in failed_logs)

    limit_logs = repo.list_login_logs(limit=2)
    assert len(limit_logs) == 2


@patch("app.auth.auth.verify_session_cookie")
def test_session_restoration_deduplication_within_window(mock_verify_cookie, client_with_auth):
    """First restoration creates record; second within 30 min is deduplicated; third after 30 min creates record."""
    from app.config import SESSION_COOKIE_NAME
    repo = client_with_auth.app.state.watchlist_repo
    repo.create_user_approval("dedup_user@example.com", "approved", repo.utc_now_iso())
    # Reset deduplication cache
    if hasattr(repo, "_restoration_cache"):
        repo._restoration_cache.clear()

    mock_verify_cookie.return_value = {
        "uid": "user_approved",
        "email": "dedup_user@example.com",
        "name": "Approved User"
    }
    client_with_auth.cookies.set(SESSION_COOKIE_NAME, "valid_session_cookie")

    start_time = 1000000.0

    # 1. First call at start_time -> creates log
    with patch("time.time", return_value=start_time):
        res1 = client_with_auth.get("/api/auth/me", headers={"User-Agent": "DeviceA"})
        assert res1.status_code == 200

    logs_1 = repo.list_login_logs(email="dedup_user@example.com", reason="session_restoration")
    assert len(logs_1) == 1

    # 2. Second call 5 minutes later (1000300s) -> deduplicated (no new DB record)
    with patch("time.time", return_value=start_time + 300):
        res2 = client_with_auth.get("/api/auth/me", headers={"User-Agent": "DeviceA"})
        assert res2.status_code == 200

    logs_2 = repo.list_login_logs(email="dedup_user@example.com", reason="session_restoration")
    assert len(logs_2) == 1

    # 3. Third call 31 minutes later (1001860s) -> creates second log record
    with patch("time.time", return_value=start_time + 1860):
        res3 = client_with_auth.get("/api/auth/me", headers={"User-Agent": "DeviceA"})
        assert res3.status_code == 200

    logs_3 = repo.list_login_logs(email="dedup_user@example.com", reason="session_restoration")
    assert len(logs_3) == 2


@patch("app.auth.auth.verify_session_cookie")
def test_two_different_users_restored_independently(mock_verify_cookie, client_with_auth):
    """Two different users calling /api/auth/me are logged independently."""
    from app.config import SESSION_COOKIE_NAME
    repo = client_with_auth.app.state.watchlist_repo
    repo.create_user_approval("user1_dedup@example.com", "approved", repo.utc_now_iso())
    repo.create_user_approval("user2_dedup@example.com", "approved", repo.utc_now_iso())
    if hasattr(repo, "_restoration_cache"):
        repo._restoration_cache.clear()

    # User 1
    mock_verify_cookie.return_value = {"uid": "u1", "email": "user1_dedup@example.com", "name": "User 1"}
    client_with_auth.cookies.set(SESSION_COOKIE_NAME, "session_u1")
    res1 = client_with_auth.get("/api/auth/me", headers={"User-Agent": "SharedBrowser"})
    assert res1.status_code == 200

    # User 2
    mock_verify_cookie.return_value = {"uid": "u2", "email": "user2_dedup@example.com", "name": "User 2"}
    client_with_auth.cookies.set(SESSION_COOKIE_NAME, "session_u2")
    res2 = client_with_auth.get("/api/auth/me", headers={"User-Agent": "SharedBrowser"})
    assert res2.status_code == 200

    logs_u1 = repo.list_login_logs(email="user1_dedup@example.com")
    logs_u2 = repo.list_login_logs(email="user2_dedup@example.com")
    assert len(logs_u1) == 1
    assert len(logs_u2) == 1


@patch("app.auth.auth.verify_session_cookie")
def test_two_different_devices_same_user_logged(mock_verify_cookie, client_with_auth):
    """Same user restoring from two different user agents creates records for each device."""
    from app.config import SESSION_COOKIE_NAME
    repo = client_with_auth.app.state.watchlist_repo
    repo.create_user_approval("multidevice@example.com", "approved", repo.utc_now_iso())
    if hasattr(repo, "_restoration_cache"):
        repo._restoration_cache.clear()

    mock_verify_cookie.return_value = {"uid": "u1", "email": "multidevice@example.com", "name": "Multi Device"}
    client_with_auth.cookies.set(SESSION_COOKIE_NAME, "session_val")

    # Device 1: Mobile
    res1 = client_with_auth.get("/api/auth/me", headers={"User-Agent": "MobileSafari/1.0"})
    assert res1.status_code == 200

    # Device 2: Desktop
    res2 = client_with_auth.get("/api/auth/me", headers={"User-Agent": "ChromeDesktop/1.0"})
    assert res2.status_code == 200

    logs = repo.list_login_logs(email="multidevice@example.com")
    assert len(logs) == 2


def test_failed_auth_attempts_never_deduplicated(client_with_auth):
    """Repeated failed authentication attempts are never deduplicated or suppressed."""
    # Attempt 1 invalid CSRF
    res1 = client_with_auth.post("/api/auth/session", json={"id_token": "tok", "csrf_token": "bad1"})
    assert res1.status_code == 401

    # Attempt 2 invalid CSRF
    res2 = client_with_auth.post("/api/auth/session", json={"id_token": "tok", "csrf_token": "bad2"})
    assert res2.status_code == 401

    repo = client_with_auth.app.state.watchlist_repo
    failed_logs = repo.list_login_logs(status="failed", reason="csrf_validation_failed")
    assert len(failed_logs) >= 2


@patch("app.auth.auth.verify_session_cookie")
def test_deduplication_error_fails_safe(mock_verify_cookie, client_with_auth):
    """If should_deduplicate_session_restoration raises an Exception, /api/auth/me still returns 200 OK."""
    from app.config import SESSION_COOKIE_NAME
    repo = client_with_auth.app.state.watchlist_repo
    repo.create_user_approval("failsafe@example.com", "approved", repo.utc_now_iso())

    mock_verify_cookie.return_value = {"uid": "u1", "email": "failsafe@example.com", "name": "Failsafe User"}
    client_with_auth.cookies.set(SESSION_COOKIE_NAME, "valid_cookie")

    with patch.object(repo, "should_deduplicate_session_restoration", side_effect=Exception("Cache error")):
        res = client_with_auth.get("/api/auth/me")
        assert res.status_code == 200
        assert res.json()["email"] == "failsafe@example.com"


def test_reason_filtering_in_repository(client_with_auth):
    """Verify repo.list_login_logs filters accurately by reason."""
    repo = client_with_auth.app.state.watchlist_repo
    now = repo.utc_now_iso()

    repo.log_login_attempt("filter_test@example.com", "success", "google_login", "127.0.0.1", "ua", now)
    repo.log_login_attempt("filter_test@example.com", "success", "session_restoration", "127.0.0.1", "ua", now)
    repo.log_login_attempt("filter_test@example.com", "failed", "pending_approval", "127.0.0.1", "ua", now)

    google_logs = repo.list_login_logs(email="filter_test@example.com", reason="google_login")
    assert len(google_logs) == 1
    assert google_logs[0]["reason"] == "google_login"

    restoration_logs = repo.list_login_logs(email="filter_test@example.com", reason="session_restoration")
    assert len(restoration_logs) == 1
    assert restoration_logs[0]["reason"] == "session_restoration"

