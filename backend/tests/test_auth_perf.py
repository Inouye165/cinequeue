import json
import logging
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import pytest

from app.auth_perf import log_trace, AUTH_PERFORMANCE_DEBUG

@pytest.fixture
def client():
    from app.main import app
    app.state.tmdb = MagicMock()
    return TestClient(app)

def test_trace_id_extraction_and_propagation(client):
    """Test that X-Auth-Trace-Id request header is extracted and returned in response headers."""
    # Even if unauthorized (401), the middleware should still propagate the headers!
    response = client.get("/api/admin/me", headers={"X-Auth-Trace-Id": "test-trace-uuid-123"})
    
    # Assert trace ID is propagated
    assert response.headers.get("X-Auth-Trace-Id") == "test-trace-uuid-123"
    
    # Assert timing headers exist
    assert "X-Auth-Perf-Token-Verification-Ms" in response.headers
    assert "X-Auth-Perf-Admin-Lookup-Ms" in response.headers

@patch("firebase_admin.auth.verify_id_token")
def test_admin_token_verification_success(mock_verify, client):
    """Test that a valid admin Bearer token returns 200 and timing headers."""
    mock_verify.return_value = {"email": "admin@example.com"}
    
    with patch("app.services.admin_auth.ADMIN_USERNAME", "admin@example.com"):
        response = client.get(
            "/api/admin/me",
            headers={
                "Authorization": "Bearer mock-admin-token",
                "X-Auth-Trace-Id": "test-trace-admin"
            }
        )
        assert response.status_code == 200
        assert response.json() == {"username": "admin@example.com"}
        
        # Verify custom timing headers were populated and trace propagated
        assert response.headers.get("X-Auth-Trace-Id") == "test-trace-admin"
        assert float(response.headers.get("X-Auth-Perf-Token-Verification-Ms", 0)) >= 0
        assert float(response.headers.get("X-Auth-Perf-Admin-Lookup-Ms", 0)) >= 0

@patch("firebase_admin.auth.verify_id_token")
def test_non_admin_token_verification_forbidden(mock_verify, client):
    """Test that a valid non-admin Bearer token returns 403 Forbidden."""
    mock_verify.return_value = {"email": "normal-user@example.com"}
    
    with patch("app.services.admin_auth.ADMIN_USERNAME", "admin@example.com"):
        response = client.get(
            "/api/admin/me",
            headers={"Authorization": "Bearer mock-user-token"}
        )
        assert response.status_code == 403
        assert "Not authorized as an administrator" in response.json()["detail"]

@patch("firebase_admin.auth.verify_id_token")
def test_invalid_token_verification_unauthorized(mock_verify, client):
    """Test that an invalid Bearer token returns 401 Unauthorized."""
    mock_verify.side_effect = Exception("Token expired")
    
    response = client.get(
        "/api/admin/me",
        headers={"Authorization": "Bearer invalid-token"}
    )
    assert response.status_code == 401
    assert "Invalid ID token" in response.json()["detail"]

@patch("app.auth_perf.logger")
def test_logs_disabled_by_default(mock_logger):
    """Test that detailed auth logs are disabled by default unless AUTH_PERFORMANCE_DEBUG is enabled."""
    # Ensure it doesn't log when AUTH_PERFORMANCE_DEBUG is False
    with patch("app.auth_perf.AUTH_PERFORMANCE_DEBUG", False):
        log_trace({"trace_id": "test"}, 200, 10.5, "success")
        mock_logger.info.assert_not_called()

    # Ensure it logs when AUTH_PERFORMANCE_DEBUG is True
    with patch("app.auth_perf.AUTH_PERFORMANCE_DEBUG", True):
        log_trace({
            "trace_id": "test-trace-123",
            "request_id": "test-req-456",
            "route": "/api/admin/me",
            "token_verification_duration_ms": 1.2,
            "admin_lookup_duration_ms": 4.5,
            "authorization_header_present": True,
            "authorization_header_scheme": "Bearer"
        }, 200, 15.6, "success")
        
        mock_logger.info.assert_called_once()
        log_msg = mock_logger.info.call_args[0][1]
        log_json = json.loads(log_msg)
        
        # Verify JSON schema matches exactly what was requested
        assert log_json["traceId"] == "test-trace-123"
        assert log_json["requestId"] == "test-req-456"
        assert log_json["route"] == "/api/admin/me"
        assert log_json["statusCode"] == 200
        assert log_json["totalDurationMs"] == 15.6
        assert log_json["tokenVerificationDurationMs"] == 1.2
        assert log_json["adminLookupDurationMs"] == 4.5
        assert log_json["authorizationHeaderPresent"] is True
        assert log_json["authorizationHeaderScheme"] == "Bearer"
        assert log_json["result"] == "success"
