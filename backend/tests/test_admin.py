import time
from unittest.mock import patch, AsyncMock
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client_with_admin_auth():
    """Fixture to provide a test client with auth enabled and reloaded modules."""
    with patch.dict("os.environ", {
        "AUTH_ENABLED": "true",
        "AUTH_MODE": "allowlist",
        "AUTH_ALLOWED_EMAILS": "inouye165@gmail.com,test@example.com",
        "AUTH_ALLOWED_ORIGINS": "https://cinequeue-7tvty3vmvq-uw.a.run.app",
        "ENVIRONMENT": "production",
        "SESSION_COOKIE_SECURE": "true",
        "FIREBASE_API_KEY": "mock_firebase_api_key",
        "ADMIN_USERNAME": "admin",
        "ADMIN_PASSWORD": "admin_secure_pass_2026"
    }):
        import importlib
        import app.config
        importlib.reload(app.config)
        import app.auth
        importlib.reload(app.auth)
        import app.services.admin_auth
        importlib.reload(app.services.admin_auth)
        import app.routers.auth
        importlib.reload(app.routers.auth)
        import app.routers.admin
        importlib.reload(app.routers.admin)
        import app.main
        importlib.reload(app.main)

        with TestClient(app.main.app, base_url="https://testserver") as c:
            app.main.app.state.tmdb = AsyncMock()
            yield c

    # Clean up and restore defaults
    importlib.reload(app.config)
    importlib.reload(app.auth)
    import app.routers.auth
    importlib.reload(app.routers.auth)
    import app.routers.admin
    importlib.reload(app.routers.admin)
    importlib.reload(app.main)


def test_admin_login_success(client_with_admin_auth):
    """Admin logs in successfully with valid credentials."""
    # Get CSRF token
    csrf_res = client_with_admin_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "admin_secure_pass_2026",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify admin session cookie was set
    set_cookies = response.headers.get_list("set-cookie")
    admin_cookie = [c for c in set_cookies if "cinequeue_admin_session" in c]
    assert len(admin_cookie) > 0
    assert "HttpOnly" in admin_cookie[0]


def test_admin_login_failure(client_with_admin_auth):
    """Admin login fails with invalid credentials."""
    csrf_res = client_with_admin_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    response = client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "wrong_password",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 401
    assert "Invalid admin credentials" in response.json()["detail"]


def test_admin_requires_csrf(client_with_admin_auth):
    """Admin login and other state-changing routes require CSRF."""
    response = client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "admin_secure_pass_2026",
            "csrf_token": "invalid_csrf"
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 401


def test_admin_endpoints_require_session(client_with_admin_auth):
    """Accessing admin endpoints without session returns 401."""
    response = client_with_admin_auth.get("/api/admin/me")
    assert response.status_code == 401

    response = client_with_admin_auth.get("/api/admin/requests")
    assert response.status_code == 401


def test_admin_logout_success(client_with_admin_auth):
    """Admin logs out successfully and deletes the session cookie."""
    csrf_res = client_with_admin_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    # 1. Login
    login_res = client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "admin_secure_pass_2026",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert login_res.status_code == 200

    # 2. Check we can access /me
    me_res = client_with_admin_auth.get("/api/admin/me")
    assert me_res.status_code == 200

    # 3. Logout
    logout_res = client_with_admin_auth.post(
        "/api/admin/logout",
        json={
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "success"

    # 4. Check we can no longer access /me
    me_res_after = client_with_admin_auth.get("/api/admin/me")
    assert me_res_after.status_code == 401



def test_admin_user_approval_flow(client_with_admin_auth):
    """Admin can approve, deny, and invite users."""
    csrf_res = client_with_admin_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    # 1. Login as admin to get session cookie
    login_res = client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "admin_secure_pass_2026",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert login_res.status_code == 200

    # 2. Invite a user
    invite_res = client_with_admin_auth.post(
        "/api/admin/invite",
        json={
            "email": "invited_user@example.com",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert invite_res.status_code == 200

    # 3. List requests & check user is invited/approved
    requests_res = client_with_admin_auth.get("/api/admin/requests")
    assert requests_res.status_code == 200
    approvals = requests_res.json()["approvals"]
    invited = [a for a in approvals if a["email"] == "invited_user@example.com"]
    assert len(invited) == 1
    assert invited[0]["status"] == "approved"

    # 4. Revoke/Deny a user
    deny_res = client_with_admin_auth.post(
        "/api/admin/deny",
        json={
            "email": "invited_user@example.com",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert deny_res.status_code == 200

    # Verify they are now revoked
    requests_res = client_with_admin_auth.get("/api/admin/requests")
    approvals = requests_res.json()["approvals"]
    revoked = [a for a in approvals if a["email"] == "invited_user@example.com"]
    assert revoked[0]["status"] == "revoked"


@patch("app.routers.auth.firebase_auth.verify_id_token")
@patch("app.routers.auth.firebase_auth.create_session_cookie")
def test_user_session_requires_approval(mock_create_cookie, mock_verify_token, client_with_admin_auth):
    """Regular user session creation fails if they are pending or revoked, succeeds if approved."""
    csrf_res = client_with_admin_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    # Mock token validation
    mock_verify_token.return_value = {
        "uid": "user_123",
        "email": "new_google_user@example.com",
        "email_verified": True,
        "auth_time": time.time(),
        "name": "Google User"
    }
    mock_create_cookie.return_value = "mock_session_val"

    # 1. Attempt login. Should auto-register as pending and return 403.
    response = client_with_admin_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 403
    assert "pending admin approval" in response.json()["detail"]

    # 2. Login as admin and approve the user
    login_admin = client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "admin_secure_pass_2026",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert login_admin.status_code == 200

    approve_res = client_with_admin_auth.post(
        "/api/admin/approve",
        json={
            "email": "new_google_user@example.com",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert approve_res.status_code == 200

    # 3. Log out admin and try user session creation again. Should succeed.
    client_with_admin_auth.cookies.set("cinequeue_admin_session", "") # clear admin session
    
    response = client_with_admin_auth.post(
        "/api/auth/session",
        json={"id_token": "dummy_token", "csrf_token": csrf_token},
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_login_attempts_logged(client_with_admin_auth):
    """Every attempted login (admin or user, success or fail) must be logged."""
    csrf_res = client_with_admin_auth.get("/api/auth/csrf")
    csrf_token = csrf_res.json()["csrf_token"]

    # Trigger a failed admin login
    client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "wrong_password",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )

    # Trigger a successful admin login
    client_with_admin_auth.post(
        "/api/admin/login",
        json={
            "username": "admin",
            "password": "admin_secure_pass_2026",
            "csrf_token": csrf_token
        },
        headers={"Origin": "https://cinequeue-7tvty3vmvq-uw.a.run.app"}
    )

    # Fetch logs
    logs_res = client_with_admin_auth.get("/api/admin/login-logs")
    assert logs_res.status_code == 200
    logs = logs_res.json()["logs"]

    # We should have at least 2 logs (failed and successful admin logins)
    assert len(logs) >= 2
    assert logs[0]["email"] == "admin"
    assert logs[0]["status"] == "success"
    assert logs[1]["email"] == "admin"
    assert logs[1]["status"] == "failed"
