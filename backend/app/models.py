from datetime import date, datetime
from typing import Any


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def days_until(release_date: str | None) -> int | None:
    target = parse_date(release_date)
    if not target:
        return None
    delta = (target - date.today()).days
    return delta


def days_label(days: int | None) -> str:
    if days is None:
        return "Date TBA"
    if days < 0:
        return ""
    if days == 0:
        return "Out today"
    if days == 1:
        return "1 day away"
    if days >= 30:
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} away"
    if days >= 14:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} away"
    if days >= 7:
        weeks = days // 7
        remaining_days = days % 7
        if remaining_days > 0:
            return f"{weeks} week{'s' if weeks > 1 else ''} {remaining_days} day{'s' if remaining_days > 1 else ''} away"
        return f"{weeks} week{'s' if weeks > 1 else ''} away"
    return f"{days} days away"


def poster_url(path: str | None, size: str = "w342") -> str | None:
    if not path:
        return None
    return f"https://image.tmdb.org/t/p/{size}{path}"


def enrich_media_item(item: dict[str, Any], media_type: str) -> dict[str, Any]:
    release = item.get("release_date") or item.get("first_air_date")
    days = days_until(release)
    return {
        "id": item["id"],
        "media_type": media_type,
        "title": item.get("title") or item.get("name"),
        "overview": item.get("overview", ""),
        "poster_url": poster_url(item.get("poster_path")),
        "backdrop_url": poster_url(item.get("backdrop_path"), "w780"),
        "release_date": release,
        "days_away": days,
        "days_label": days_label(days),
        "vote_average": item.get("vote_average"),
        "vote_count": item.get("vote_count"),
        "popularity": item.get("popularity"),
    }
