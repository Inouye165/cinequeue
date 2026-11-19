"""Shared pure normalization and default helpers across repository backends."""

from datetime import datetime, timezone
from typing import Any

DEFAULT_TIMEZONE = "America/Los_Angeles"


def format_rated_ago(timestamp_str: str | None, now: datetime | None = None) -> str:
    """Format an ISO timestamp as a human-readable relative age string."""
    if not timestamp_str:
        return "recently"
    ref_now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(timestamp_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        seconds = int((ref_now - dt).total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            mins = seconds // 60
            return f"{mins} min{'s' if mins > 1 else ''} ago"
        if seconds < 86400:
            hrs = seconds // 3600
            return f"{hrs} hour{'s' if hrs > 1 else ''} ago"
        if seconds < 2592000:
            days = seconds // 86400
            return f"{days} day{'s' if days > 1 else ''} ago"
        if seconds < 31536000:
            months = seconds // 2592000
            return f"{months} month{'s' if months > 1 else ''} ago"
        yrs = seconds // 31536000
        return f"{yrs} year{'s' if yrs > 1 else ''} ago"
    except Exception:
        return "recently"


def default_agent_settings(user_id: str, updated_at: str) -> dict[str, Any]:
    """Return the canonical default AI agent settings payload."""
    return {
        "user_id": user_id,
        "personality_preset": "cinephile",
        "custom_prompt": "",
        "location": "",
        "timezone": DEFAULT_TIMEZONE,
        "user_timezone": DEFAULT_TIMEZONE,
        "notify_on_login": True,
        "auto_add_mentioned": True,
        "track_price_drops": True,
        "auto_speak_briefing": False,
        "updated_at": updated_at,
    }


def normalize_agent_settings(
    user_id: str, settings: dict[str, Any], updated_at: str
) -> dict[str, Any]:
    """Normalize persisted or incoming AI agent settings dictionaries."""
    if "timezone" in settings and settings["timezone"] is not None:
        tz = str(settings["timezone"]).strip()
    elif "user_timezone" in settings and settings["user_timezone"] is not None:
        tz = str(settings["user_timezone"]).strip()
    else:
        tz = DEFAULT_TIMEZONE
    return {
        "user_id": user_id,
        "personality_preset": settings.get("personality_preset", "cinephile"),
        "custom_prompt": settings.get("custom_prompt", "") or "",
        "location": (settings.get("location") or "").strip(),
        "timezone": tz,
        "user_timezone": tz,
        "notify_on_login": bool(settings.get("notify_on_login", True)),
        "auto_add_mentioned": bool(settings.get("auto_add_mentioned", True)),
        "track_price_drops": bool(settings.get("track_price_drops", True)),
        "auto_speak_briefing": bool(settings.get("auto_speak_briefing", False)),
        "updated_at": updated_at,
    }


def default_sports_preferences(user_id: str) -> dict[str, Any]:
    """Return the canonical default sports preferences payload."""
    return {
        "user_id": user_id,
        "streaming_services": [],
        "tracked_teams": [],
        "show_in_queue": True,
        "setup_completed": False,
        "updated_at": None,
    }
