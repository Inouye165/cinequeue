from unittest.mock import MagicMock, patch

import pytest
from app.services.email_service import _send_invite_email_sync, send_invite_email


@pytest.mark.asyncio
async def test_email_service_unconfigured():
    with patch("app.services.email_service.SMTP_HOST", ""):
        success, message = await send_invite_email("test@example.com", "http://localhost:5180", "Admin")
        assert success is False
        assert "not configured" in message


@pytest.mark.asyncio
async def test_email_service_success():
    with (
        patch("app.services.email_service.SMTP_HOST", "smtp.example.com"),
        patch("app.services.email_service.SMTP_PORT", 587),
        patch("app.services.email_service.SMTP_USER", "user"),
        patch("app.services.email_service.SMTP_PASSWORD", "pass"),
        patch("app.services.email_service.smtplib.SMTP") as mock_smtp,
    ):
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server

        success, message = await send_invite_email("test@example.com", "http://localhost:5180", "Admin")
        assert success is True
        assert "successfully sent" in message
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()


@pytest.mark.asyncio
async def test_email_service_failure():
    with (
        patch("app.services.email_service.SMTP_HOST", "smtp.example.com"),
        patch("app.services.email_service.smtplib.SMTP", side_effect=Exception("Connection refused")),
    ):
        success, message = await send_invite_email("test@example.com", "http://localhost:5180", "Admin")
        assert success is False
        assert "Connection refused" in message
