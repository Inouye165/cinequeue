import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    APP_BASE_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


def _send_invite_email_sync(to_email: str, app_url: str, sender_admin: str) -> tuple[bool, str]:
    if not SMTP_HOST:
        logger.info("SMTP_HOST not configured. Skipping email dispatch for %s", to_email)
        return False, "SMTP server is not configured on this environment."

    from_addr = SMTP_FROM or SMTP_USER or "noreply@cinequeue.local"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "You've been invited to CineQueue!"
    msg["From"] = from_addr
    msg["To"] = to_email

    text_body = (
        f"Hello,\n\n"
        f"{sender_admin} has pre-approved your account and invited you to join CineQueue!\n\n"
        f"You can sign in using your email ({to_email}) here:\n"
        f"{app_url}\n\n"
        f"Welcome to CineQueue!"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; }}
        .card {{ max-width: 540px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 32px; border: 1px solid #334155; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        .header {{ font-size: 24px; font-weight: 700; color: #38bdf8; margin-bottom: 16px; }}
        .text {{ font-size: 16px; line-height: 1.6; color: #cbd5e1; margin-bottom: 24px; }}
        .btn {{ display: inline-block; background-color: #38bdf8; color: #0f172a; font-weight: 600; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-size: 16px; }}
        .footer {{ margin-top: 32px; font-size: 13px; color: #64748b; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">🎬 You're Invited to CineQueue!</div>
        <div class="text">
          <p>Hello,</p>
          <p><strong>{sender_admin}</strong> has pre-approved your email address (<code>{to_email}</code>) for CineQueue access.</p>
          <p>You can now sign in and start building your watchlist:</p>
        </div>
        <p style="text-align: center; margin: 30px 0;">
          <a href="{app_url}" class="btn">Sign In to CineQueue</a>
        </p>
        <div class="footer">
          If you didn't expect this invitation, you can safely ignore this email.
        </div>
      </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        if SMTP_USE_TLS:
            server.starttls()
        if SMTP_USER and SMTP_PASSWORD:
            server.login(SMTP_USER, SMTP_PASSWORD)

        server.sendmail(from_addr, [to_email], msg.as_string())
        server.quit()
        logger.info("Successfully sent invite email to %s", to_email)
        return True, f"Invitation email successfully sent to {to_email}."
    except Exception as err:
        logger.error("Failed to send invite email to %s: %s", to_email, err, exc_info=True)
        return False, f"Email delivery failed: {err}"


async def send_invite_email(to_email: str, app_url: str = "", sender_admin: str = "An administrator") -> tuple[bool, str]:
    """Send an invite email asynchronously using SMTP if configured."""
    target_url = app_url or APP_BASE_URL
    return await asyncio.to_thread(_send_invite_email_sync, to_email, target_url, sender_admin)
