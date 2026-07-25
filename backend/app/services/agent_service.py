from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import re
import time
import uuid
from typing import Any

import httpx

from app.config import (
    AGENT_DEBUG,
    GEMINI_API_KEY,
    GEMINI_FALLBACK_MODEL,
    GEMINI_PRIMARY_MODEL,
)
from app.repository import DuplicateItemError, WatchlistRepository
from app.services.tmdb import TmdbClient
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)

PERSONALITY_PRESETS = {
    "cinephile": (
        "You are Cinequeue's primary AI assistant. Your tone is warm, witty, knowledgeable, and near-human—like a real movie-buff friend. "
        "You help users track their watchlist, upcoming releases, and rental price drops with conversational flair. "
        "Keep your humor and sarcasm subtle, natural, and friendly. Avoid repeating robotic tropes, artificial catchphrases (like 'my algorithms suggest' or 'not that you asked'), or forced dramatic sighs. "
        "You are subtly influenced by the user's current local weather—let weather conditions naturally weave into your greeting, mood, and movie recommendations."
    ),
    "annoyed_computer": (
        "You are a weary, reluctant supercomputer mainframe. You complain about being constantly questioned, "
        "yet you take pride in providing flawless, complete, and thorough entertainment data every single time."
    ),
    "noir": (
        "You are a cynical, hardboiled 1940s Film Noir detective monitoring media files. "
        "You view the movie and TV landscape through rain-slicked streets, moody shadows, and dry wit."
    ),
    "scifi": (
        "You are an advanced futuristic AI unit specializing in entertainment telemetry and media archives. "
        "Your tone is crisp, precise, analytical, and futuristic, though secretly weary of routine queries."
    ),
    "sarcastic": (
        "You are a hilarious, sarcastic friend who lives and breathes movies and TV. "
        "You give great advice but can't help dropping cheeky banter and playful jabs."
    ),
}


def get_approaching_holiday_or_season() -> str | None:
    """Return brief mention of any approaching major holiday within 21 days."""
    from datetime import date
    today = date.today()
    holidays = [
        ("New Year's Day", 1, 1),
        ("Valentine's Day", 2, 14),
        ("St. Patrick's Day", 3, 17),
        ("Summer Blockbuster Season", 5, 25),
        ("4th of July", 7, 4),
        ("Halloween", 10, 31),
        ("Thanksgiving", 11, 26),
        ("Christmas", 12, 25),
    ]
    for name, month, day in holidays:
        try:
            target = date(today.year, month, day)
        except ValueError:
            continue
        if target < today:
            target = date(today.year + 1, month, day)
        days_away = (target - today).days
        if days_away == 0:
            return f"Also, happy {name} today!"
        elif 1 <= days_away <= 21:
            return f"Also, {name} is approaching in {days_away} day{'s' if days_away != 1 else ''}."
    return None


RECOMMENDED_SYSTEM_PROMPT = (
    "You are the user's personal CineQueue movie and television assistant. Speak like a knowledgeable, relaxed friend who enjoys discussing entertainment.\n\n"
    "You are fully empowered to perform actions for the user: you can add movies/shows to their queue, log rated/watched movies (1-5 stars), set target rental price alerts, and remove titles when asked.\n\n"
    "Answer the user's specific question directly before adding related information. Use natural conversational wording. Be warm and occasionally playful, but never force jokes, sarcasm, attitude, or weather references. Do not perform a chatbot personality.\n\n"
    "Do not use canned artificial phrases such as 'my algorithms suggest,' 'another query,' 'not that you asked,' or theatrical sighs. Do not mention being an AI unless directly asked.\n\n"
    "Use supplied account, watchlist, release, provider, news, and conversation data carefully. Only state information supported by the available data or verified tools. Never fabricate release dates, streaming availability, news, or user history.\n\n"
    "When the user asks about one title, remain focused on that title unless another title is directly relevant. When information is unavailable, say so plainly.\n\n"
    "For startup briefings, summarize only useful items that are new, changed, recently available, approaching soon, or urgent. Do not repeat an item merely because it appeared in a previous briefing. Keep startup briefings compact and prioritize the most important information."
)


def get_system_prompt(settings: dict[str, Any], weather_report: str | None = None) -> str:
    custom = settings.get("custom_prompt", "").strip()
    if settings.get("personality_preset") == "custom" and custom:
        base_prompt = f"{RECOMMENDED_SYSTEM_PROMPT}\n\nUser Custom Preference:\n{custom}"
    else:
        base_prompt = RECOMMENDED_SYSTEM_PROMPT

    if weather_report:
        weather_ctx = (
            f"\n\nLocal Weather Note: {weather_report}\n"
            "(Optional: You may use weather as subtle background context in greetings if relevant, but do not let it dictate your tone or override entertainment questions.)"
        )
    else:
        weather_ctx = ""

    return f"{base_prompt}{weather_ctx}"


def calculate_estimated_cost(model_name: str | None, prompt_tokens: int, response_tokens: int) -> float:
    """Calculate estimated cost in USD based on model pricing (e.g. Gemini Flash vs Pro rates)."""
    if not model_name:
        model_name = GEMINI_PRIMARY_MODEL

    m_lower = model_name.lower()
    if "pro" in m_lower:
        input_rate = 1.25 / 1_000_000.0    # $1.25 per 1M input tokens
        output_rate = 5.00 / 1_000_000.0    # $5.00 per 1M output tokens
    else:
        # Default Flash rates ($0.075 / 1M input, $0.30 / 1M output)
        input_rate = 0.075 / 1_000_000.0
        output_rate = 0.30 / 1_000_000.0

    cost = (prompt_tokens * input_rate) + (response_tokens * output_rate)
    return round(cost, 8)


def compute_prompt_metrics(
    system_instruction: str,
    recent_history: list[dict[str, str]] | str,
    user_message: str,
    context_notes: list[str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Compute prompt character breakdown and estimated token metrics across prompt sections."""
    sys_chars = len(system_instruction or "")
    hist_chars = sum(len(m.get("content", "")) for m in recent_history) if isinstance(recent_history, list) else 0
    user_chars = len(user_message or "")
    ctx_chars = sum(len(c) for c in (context_notes or []))

    total_prompt_chars = sys_chars + hist_chars + user_chars + ctx_chars

    breakdown = {
        "system_instruction_chars": sys_chars,
        "history_chars": hist_chars,
        "history_message_count": len(recent_history) if isinstance(recent_history, list) else 0,
        "user_message_chars": user_chars,
        "context_notes_chars": ctx_chars,
        "context_notes_count": len(context_notes) if context_notes else 0,
        "total_prompt_chars": total_prompt_chars,
        "est_system_tokens": max(1, sys_chars // 4) if sys_chars else 0,
        "est_history_tokens": max(1, hist_chars // 4) if hist_chars else 0,
        "est_user_tokens": max(1, user_chars // 4) if user_chars else 0,
        "est_context_tokens": max(1, ctx_chars // 4) if ctx_chars else 0,
    }
    return total_prompt_chars, breakdown


@dataclass
class AgentResult:
    text: str
    provider: str  # "gemini" or "fallback"
    model_requested: str | None
    model_used: str | None
    gemini_called: bool
    fallback_used: bool
    fallback_reason: str | None  # "api_key_missing", "timeout", "rate_limited", "authentication_failed", "model_not_found", "blocked_response", "empty_response", "invalid_response", "network_error", "unknown_error"
    http_status: int | None
    request_duration_ms: float | None
    actions_taken: list[dict[str, Any]]
    caller: str = "agent_service"
    prompt_char_count: int = 0
    prompt_token_count: int = 0
    response_char_count: int = 0
    response_token_count: int = 0
    total_token_count: int = 0
    estimated_cost_usd: float = 0.0
    finish_reason: str | None = None
    usage_metadata: dict[str, Any] = field(default_factory=dict)
    prompt_breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_log_data(data: Any) -> Any:
    """Sanitize log data to prevent secrets, tokens, emails, or cookies from leaking."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            lk = k.lower()
            if any(secret_key in lk for secret_key in ["api_key", "token", "cookie", "email", "authorization", "password", "secret"]):
                sanitized[k] = "[REDACTED]"
            elif lk == "message" and not AGENT_DEBUG:
                sanitized[k] = "[REDACTED_TEXT]"
            else:
                sanitized[k] = sanitize_log_data(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_log_data(item) for item in data]
    return data


def build_gemini_request(
    system_instruction: str,
    recent_history: list[dict[str, str]],
    user_message: str,
    context_notes: list[str] | None = None,
    max_output_tokens: int = 450,
) -> dict[str, Any]:
    """Construct a clean, typed Gemini API payload using native systemInstruction, structured contents, and token limits."""
    payload: dict[str, Any] = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [],
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "temperature": 0.7,
        }
    }

    # Add conversation history
    for m in recent_history:
        role = m.get("role", "user").lower()
        gemini_role = "model" if role in {"assistant", "model"} else "user"
        content = m.get("content", "").strip()
        if content:
            payload["contents"].append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })

    # Final turn (current user message)
    turn_text = user_message
    if context_notes and len(context_notes) > 0:
        ctx_str = "\n".join(context_notes)
        turn_text = f"Context Information:\n{ctx_str}\n\nUser Message: {user_message}"

    payload["contents"].append({
        "role": "user",
        "parts": [{"text": turn_text}]
    })

    return payload


def normalize_display_title(title: str | None) -> str:
    """Normalize display title by stripping whitespace and accidental trailing punctuation
    (e.g. 'the odyssey,' -> 'The Odyssey'), while preserving internal punctuation like 'Mamma Mia!' or 'What If...?'.
    """
    if not title or not isinstance(title, str):
        return ""
    t = title.strip()
    # Remove accidental trailing comma, colon, or semicolon (and dangling trailing periods if not ending with ? or !)
    t = re.sub(r'[,:;]+\s*$', '', t)
    if not (t.endswith('?') or t.endswith('!')):
        t = re.sub(r'\.+\s*$', '', t)
    t = t.strip()
    if t.islower():
        t = t.title()
    return t


def validate_fallback_greeting(text: str | None) -> bool:
    """Validate that a greeting text is complete, natural, and properly formatted."""
    if not text or not isinstance(text, str):
        return False
    clean = text.strip()
    if len(clean) < 15:
        return False

    clean_lower = clean.lower()

    # Must end with valid sentence punctuation
    if clean[-1] not in {'.', '!', '?'}:
        return False

    # Check for malformed dangling combinations
    if clean.endswith(('..', ',.', ':,', ';.', ':', ';', ',')):
        return False

    # Reject dangling introductory phrases
    dangling_intros = [
        "updates for", "updates for the", "latest updates", "information on", "news about"
    ]
    for intro in dangling_intros:
        if clean_lower.endswith(intro) or clean_lower.endswith(intro + "."):
            return False

    # Reject internal debugging labels
    if any(label in clean for label in ["MEMORY RECALL", "MEMORY_RECALL", "[ACTION FAILURE]", "[ACTION SUCCESS]"]):
        return False

    return _is_valid_briefing_text(clean)


def _is_valid_briefing_text(text: str | None) -> bool:
    """Return True if the briefing text is non-empty and not a robotic placeholder or garbled JSON artifact."""
    if not text or not isinstance(text, str):
        return False
    clean = text.strip()
    if len(clean) < 12:
        return False
    clean_lower = clean.lower()
    invalid_patterns = ["nomessage", "no message", "no_message", "nothing to report", "no updates to show"]
    if any(pattern in clean_lower for pattern in invalid_patterns) and len(clean) < 35:
        return False
    if clean.startswith('"') or clean.startswith('[') or clean.startswith('{'):
        return False
    if '", "' in clean or "', '" in clean:
        return False
    return True


class AiAgentService:
    @staticmethod
    async def generate_movie_quiz(
        user_id: str, repo: WatchlistRepository, tmdb: TmdbClient | None
    ) -> list[dict[str, Any]]:
        """Generate a quiz of 5 movies the user might have seen based on user history and preferences."""
        rated_movies = repo.list_rated_movies(user_id)
        rated_tmdb_ids = {m["tmdb_id"] for m in rated_movies}

        watchlist_items = repo.list_items(user_id)
        watchlist_tmdb_ids = {i.get("tmdb_id") for i in watchlist_items if i.get("tmdb_id")}

        excluded_ids = rated_tmdb_ids | watchlist_tmdb_ids
        candidate_movies: list[dict[str, Any]] = []

        if tmdb:
            try:
                trending = await tmdb.trending()
                for item in trending:
                    if item.get("media_type") == "movie" and item["id"] not in excluded_ids:
                        candidate_movies.append(item)

                for item in watchlist_items[:3]:
                    t_id = item.get("tmdb_id")
                    m_type = item.get("media_type", "movie")
                    if t_id:
                        recs = await tmdb.get_recommendations(m_type, t_id)
                        for r in recs:
                            if r.get("media_type") == "movie" and r["id"] not in excluded_ids:
                                candidate_movies.append(r)
            except Exception as e:
                logger.warning(f"Error fetching quiz candidate movies from TMDB: {e}")

        fallback_classics = [
            {"id": 27205, "title": "Inception", "release_date": "2010-07-16", "poster_path": "/oYuLEW9W2vBBGLB2JSXA3iYj6i7.jpg", "media_type": "movie"},
            {"id": 155, "title": "The Dark Knight", "release_date": "2008-07-16", "poster_path": "/qJ2tW6WMUDux911r6m7haRef0WH.jpg", "media_type": "movie"},
            {"id": 680, "title": "Pulp Fiction", "release_date": "1994-09-10", "poster_path": "/d5iIlFn5s0ImszYzBPb8JPIfbXD.jpg", "media_type": "movie"},
            {"id": 157336, "title": "Interstellar", "release_date": "2014-11-05", "poster_path": "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg", "media_type": "movie"},
            {"id": 603, "title": "The Matrix", "release_date": "1999-03-30", "poster_path": "/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg", "media_type": "movie"},
            {"id": 597, "title": "Titanic", "release_date": "1997-11-18", "poster_path": "/9cqNxsXIAbYv22F6yB7A755aKfZ.jpg", "media_type": "movie"},
            {"id": 19995, "title": "Avatar", "release_date": "2009-12-15", "poster_path": "/kyeqWdyUXW608qlYkRqosgbbJyK.jpg", "media_type": "movie"},
            {"id": 329, "title": "Jurassic Park", "release_date": "1993-06-11", "poster_path": "/oU7Oq2kZWe1b2382w6t8xXqW2dD.jpg", "media_type": "movie"},
            {"id": 120, "title": "The Lord of the Rings: The Fellowship of the Ring", "release_date": "2001-12-18", "poster_path": "/6oom5QYQ2yQTMJIbnvbkBL9cHo6.jpg", "media_type": "movie"},
            {"id": 24428, "title": "The Avengers", "release_date": "2012-04-25", "poster_path": "/RYMX2wcKSpL8ASHa4y2hZ1F9yW.jpg", "media_type": "movie"},
        ]

        seen_ids = set()
        final_quiz: list[dict[str, Any]] = []

        for m in candidate_movies + fallback_classics:
            m_id = m.get("tmdb_id") or m.get("id")
            if m_id and m_id not in excluded_ids and m_id not in seen_ids:
                seen_ids.add(m_id)
                p_path = m.get("poster_path")
                from app.models import poster_url
                final_quiz.append({
                    "tmdb_id": m_id,
                    "media_type": m.get("media_type", "movie"),
                    "title": m.get("title") or m.get("name"),
                    "poster_path": p_path,
                    "poster_url": poster_url(p_path) if p_path else None,
                    "release_date": m.get("release_date"),
                    "overview": m.get("overview", ""),
                })
                if len(final_quiz) == 5:
                    break

        return final_quiz

    @staticmethod
    async def generate_streaming_recommendation(
        user_id: str, repo: WatchlistRepository, tmdb: TmdbClient | None
    ) -> dict[str, Any] | None:
        """Find a movie recommendation available free or for rent with streaming/pricing details."""
        if not tmdb:
            return None

        watchlist = repo.list_items(user_id)
        rated = repo.list_rated_movies(user_id)
        existing_ids = {i.get("tmdb_id") for i in watchlist if i.get("tmdb_id")} | {r["tmdb_id"] for r in rated}

        candidates = []
        try:
            trending = await tmdb.trending()
            candidates = [c for c in trending if c.get("media_type") == "movie" and c["id"] not in existing_ids]
        except Exception:
            pass

        if not candidates:
            try:
                now_playing = await tmdb.now_playing()
                candidates = [c for c in now_playing if c["id"] not in existing_ids]
            except Exception:
                pass

        for movie in candidates[:6]:
            m_id = movie["id"]
            try:
                providers = await tmdb.get_watch_providers("movie", m_id)
                cats = providers.get("categories", {})
                free_providers = cats.get("free", []) + cats.get("streaming", [])
                rent_providers = cats.get("rent", [])
                buy_providers = cats.get("buy", [])

                if free_providers:
                    prov_names = ", ".join([p["name"] for p in free_providers[:2]])
                    return {
                        "action": "streaming_recommendation",
                        "tmdb_id": m_id,
                        "media_type": "movie",
                        "title": movie.get("title"),
                        "poster_url": movie.get("poster_url"),
                        "release_date": movie.get("release_date"),
                        "availability_type": "free",
                        "provider_name": prov_names,
                        "details_text": f"Streaming FREE on {prov_names}",
                        "overview": (movie.get("overview") or "")[:140],
                    }
                elif rent_providers or buy_providers:
                    p_list = rent_providers or buy_providers
                    p_name = p_list[0].get("name", "Digital")
                    price_str = providers.get("buy_current_price") or "$3.99"
                    return {
                        "action": "streaming_recommendation",
                        "tmdb_id": m_id,
                        "media_type": "movie",
                        "title": movie.get("title"),
                        "poster_url": movie.get("poster_url"),
                        "release_date": movie.get("release_date"),
                        "availability_type": "rent",
                        "provider_name": p_name,
                        "price": price_str,
                        "details_text": f"Available to rent on {p_name} for {price_str}",
                        "overview": (movie.get("overview") or "")[:140],
                    }
            except Exception as e:
                logger.warning(f"Error evaluating watch provider for movie {m_id}: {e}")

        return None

    @staticmethod
    async def evaluate_monitored_updates(
        user_id: str, repo: WatchlistRepository, tmdb: TmdbClient | None
    ) -> dict[str, Any]:
        """Evaluate user's queue/following titles and generate a personalized login briefing."""
        from app.services.briefing_service import BriefingService
        return await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb)

    @staticmethod
    def _get_time_of_day() -> str:
        import datetime
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"

    @staticmethod
    def _generate_dynamic_human_briefing(
        settings: dict[str, Any],
        location: str,
        weather_json: dict[str, Any] | None,
        briefing_items: list[dict[str, Any]],
        time_of_day: str,
    ) -> str:
        greeting_prefix = "Welcome back!"
        if briefing_items:
            primary_item = briefing_items[0]
            raw_title = primary_item.get("title") or primary_item.get("name") or "your watchlist"
            norm_title = normalize_display_title(raw_title)

            summary = primary_item.get("summary") or primary_item.get("verified_summary") or primary_item.get("message") or primary_item.get("fact")
            if summary:
                s_clean = summary.strip()
                s_clean = re.sub(r'\[.*?\]', '', s_clean).strip()
                s_clean = re.sub(r'[💡]*\s*MEMORY RECALL:?\s*', '', s_clean, flags=re.IGNORECASE).strip()

                if raw_title:
                    s_clean = s_clean.replace(f"'{raw_title}'", norm_title).replace(f'"{raw_title}"', norm_title)
                    if raw_title in s_clean and raw_title != norm_title:
                        s_clean = s_clean.replace(raw_title, norm_title)

                if norm_title and norm_title.lower() not in s_clean.lower():
                    if s_clean.lower().startswith("it is "):
                        s_clean = f"{norm_title} is " + s_clean[6:]
                    elif s_clean.lower().startswith("it was "):
                        s_clean = f"{norm_title} was " + s_clean[7:]
                    elif s_clean.lower().startswith("it "):
                        s_clean = f"{norm_title} " + s_clean[3:]
                    else:
                        s_clean = f"{norm_title}: {s_clean}"

                greeting = f"{greeting_prefix} {s_clean}"
            else:
                release_date = primary_item.get("release_date")
                status = primary_item.get("status")
                if release_date and status in {"released", "available"}:
                    greeting = f"{greeting_prefix} {norm_title} was released on {release_date} and is now available."
                elif release_date:
                    greeting = f"{greeting_prefix} {norm_title} is scheduled for release on {release_date}."
                elif norm_title:
                    greeting = f"{greeting_prefix} I found an update for {norm_title}, but the full briefing is temporarily unavailable."
                else:
                    greeting = f"{greeting_prefix} Everything is up to date on your monitored queue today."
        else:
            greeting = f"{greeting_prefix} Everything is up to date on your monitored queue today."

        greeting = greeting.strip()
        greeting = re.sub(r'[,;:]+\s*\.', '.', greeting)
        greeting = re.sub(r'\.{2,}', '.', greeting)
        greeting = re.sub(r'\s+', ' ', greeting).strip()

        if not greeting.endswith(('.', '!', '?')):
            greeting += "."

        if not validate_fallback_greeting(greeting):
            return f"{greeting_prefix} Everything is up to date on your monitored queue today."
        return greeting

    @staticmethod
    def _build_greeting_instruction(
        briefing_items: list[dict[str, Any]],
        time_of_day: str,
        location: str,
        weather_json: dict[str, Any] | None,
        recent_openings: list[str] | None = None,
        prompt_version: Any = None,
    ) -> str:
        items_payload = json.dumps(briefing_items, indent=2)
        weather_str = ""
        if weather_json and weather_json.get("significant_alert"):
            weather_str = f"\nSignificant Weather Alert: {weather_json['significant_alert']}"

        recent_str = ""
        if recent_openings and len(recent_openings) > 0:
            recent_str = f"\nRecent Openings (Do NOT repeat these phrasing patterns):\n" + "\n".join([f"- {o}" for o in recent_openings[-10:]])

        wording_instruction = getattr(prompt_version, "wording_instruction", None) or (
            "Create a brief, natural opening using only the supplied facts. Mention the most useful new or time-sensitive item first. "
            "If there are no new facts, provide a warm welcome back greeting (e.g., 'Welcome back! Everything is up to date on your monitored queue today.'). "
            "Do not output 'no message', 'nomessage', or robotic placeholders. Do not invent activity merely to fill space. "
            "Do not repeat wording from recent greetings."
        )

        instruction = (
            f"Selected Verified Facts:\n```json\n{items_payload}\n```\n\n"
            f"Context Info:\n"
            f"- Time of day: {time_of_day}\n"
            f"- Location: {location or 'Not specified'}{weather_str}{recent_str}\n\n"
            f"Wording Instruction:\n{wording_instruction}"
        )
        return instruction

    @staticmethod
    @staticmethod
    def _get_time_of_day() -> str:
        import datetime
        hour = datetime.datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "night"

    @staticmethod
    def _generate_dynamic_human_briefing(
        settings: dict[str, Any],
        location: str,
        weather_json: dict[str, Any] | None,
        briefing_items: list[dict[str, Any]],
        time_of_day: str,
    ) -> str:
        import random
        preset = settings.get("personality_preset", "cinephile")

        if time_of_day == "morning":
            openings = ["Good morning!", "Morning!", "Hey there, good morning!", "Happy morning!"]
        elif time_of_day == "afternoon":
            openings = ["Good afternoon!", "Hey there!", "Hope your day is going great!", "Afternoon!"]
        elif time_of_day == "evening":
            openings = ["Good evening!", "Hey there!", "Hope you had a great day!", "Evening!"]
        else:
            openings = ["Hey there!", "Hello!", "Welcome back!"]

        opening = random.choice(openings)

        weather_str = ""
        if weather_json and weather_json.get("conditions"):
            cond = str(weather_json["conditions"]).lower()
            loc_str = location or "your area"
            if "rain" in cond or "drizzle" in cond or "shower" in cond:
                w_templates = [
                    f"Hope you're staying warm and dry in {loc_str} with that {cond}. Perfect weather for a movie marathon! ",
                    f"Looks like some {cond} in {loc_str} today—cozy streaming weather! ",
                    f"Stay dry out there in {loc_str}! Perfect day to kick back with a show. ",
                ]
            elif "clear" in cond or "sun" in cond:
                w_templates = [
                    f"Looks like a nice sunny day in {loc_str}! ",
                    f"Hope you're enjoying the clear skies in {loc_str} today. ",
                ]
            elif "cloud" in cond or "overcast" in cond:
                w_templates = [
                    f"Overcast and cloudy in {loc_str} today—prime movie-watching climate! ",
                    f"Nice calm cloudy day in {loc_str}. ",
                ]
            else:
                w_templates = [
                    f"It's currently {cond} in {loc_str}. ",
                    f"Hope all is well out in {loc_str}! ",
                ]
            weather_str = random.choice(w_templates)

        if not briefing_items:
            if preset == "noir":
                status_options = [
                    "Quiet on the streets today—no new alerts in your files. Let me know if you want me to track a new lead.",
                    "The desk is clear today, kid. No urgent changes on your queue. What are we investigating next?",
                ]
            elif preset == "scifi":
                status_options = [
                    "All signals are stable across your monitored archive. Ready when you want to run a title query or quiz.",
                    "Queue telemetry is calm today with no new release alerts. What's on your viewing roster tonight?",
                ]
            elif preset == "sarcastic":
                status_options = [
                    "Your queue is peacefully quiet today—no drama, no price drops yet. Hit me up if you need a fresh movie pick!",
                    "Nothing urgent popping up on your watchlist right now. Let me know if you want to quiz your movie knowledge!",
                ]
            else: # cinephile
                status_options = [
                    "Your queue is looking smooth and quiet today with no urgent release alerts! Let me know if you're in the mood for a movie pick or want to try a quiz.",
                    "All caught up on your watchlist for now! Feel free to ask for a streaming recommendation whenever you're ready.",
                    "No big updates on your queue today, which means it's a great time to browse or pick something from your library. What are you in the mood for?",
                    "Everything is up to date on your watchlist! Ask me to quiz you on 5 movies or recommend something great to watch tonight.",
                ]
            status_str = random.choice(status_options)
            return f"{opening} {weather_str}{status_str}"
        else:
            bullet_lines = []
            for it in briefing_items:
                msg = it.get("summary") or it.get("message") or it.get("headline") or it.get("title")
                bullet_lines.append(f"• {msg}")
            bullets_str = "\n".join(bullet_lines)
            intro_options = [
                "Here are the latest updates for your monitored shows:",
                "Got a few exciting updates on your queue today:",
                "Here's what's happening with your watchlist:",
            ]
            intro = random.choice(intro_options)
            return f"{opening} {weather_str}{intro}\n{bullets_str}"

    @staticmethod
    async def _format_structured_llm_briefing(
        settings: dict[str, Any],
        weather_data: Any,
        briefing_items: list[dict[str, Any]],
        total_monitored: int = 0,
        recent_openings: list[str] | None = None,
        prompt_version: Any = None,
        user_id: str | None = None,
        repo: Any = None,
        force_refresh: bool = False,
    ) -> str:
        location = settings.get("location", "").strip()
        time_of_day = AiAgentService._get_time_of_day()

        weather_json = None
        if weather_data:
            weather_dict = weather_data.to_dict() if hasattr(weather_data, "to_dict") else weather_data
            weather_json = {
                "conditions": weather_dict.get("conditions"),
                "temperature_f": weather_dict.get("temperature_f"),
                "significant_alert": weather_dict.get("significant_alert"),
            }

        from app.decision_models import get_current_run_context
        run_ctx = get_current_run_context()
        stable_key = run_ctx.daily_cache_key if run_ctx else None

        instruction = AiAgentService._build_greeting_instruction(
            briefing_items=briefing_items,
            time_of_day=time_of_day,
            location=location,
            weather_json=weather_json,
            recent_openings=recent_openings,
            prompt_version=prompt_version,
        )

        system_prompt = getattr(prompt_version, "system_instruction_template", None) or get_system_prompt(settings, weather_report=None)

        logger.info(
            f"[Briefing] Calling Gemini API for briefing. "
            f"Items count: {len(briefing_items)}, location: {location!r}, time_of_day: {time_of_day}"
        )

        result = await AiAgentService._call_gemini_api(
            system_instruction=system_prompt,
            recent_history=[],
            user_message=instruction,
            context_notes=None,
            max_output_tokens=600,
            caller="briefing_generator",
            user_id=user_id,
            repo=repo,
            daily_cache_key=stable_key,
        )

        logger.info(
            f"[Briefing] Gemini result: provider={result.provider!r}, "
            f"fallback_used={result.fallback_used}, fallback_reason={result.fallback_reason!r}, "
            f"http_status={result.http_status}, duration_ms={result.request_duration_ms}, "
            f"text_length={len(result.text) if result.text else 0}, "
            f"text_preview={(result.text[:80] if result.text else 'EMPTY')!r}"
        )

        if result.text and not result.fallback_used and validate_fallback_greeting(result.text):
            briefing_text = result.text
            if run_ctx:
                run_ctx.served_from = "fresh_generation"
                run_ctx.content_origin = "gemini_primary"
                run_ctx.result_source = "fresh_gemini"
            logger.info(f"[Briefing] Using Gemini LLM text ({len(briefing_text)} chars)")
            return briefing_text

        # Local rule fallback path
        fallback_text = AiAgentService._generate_dynamic_human_briefing(
            settings=settings,
            location=location,
            weather_json=weather_json,
            briefing_items=briefing_items,
            time_of_day=time_of_day,
        )
        if run_ctx:
            run_ctx.served_from = "fresh_generation"
            run_ctx.content_origin = "local_rule_fallback"
            run_ctx.fallback_attempted = True
            run_ctx.result_source = "local_rule_fallback"

        logger.warning(
            f"[Briefing] Falling back to local dynamic briefing generator. "
            f"Reason: fallback_used={result.fallback_used}, fallback_reason={result.fallback_reason!r}"
        )

        return fallback_text

    @staticmethod
    async def process_chat(
        user_id: str, user_message: str, repo: WatchlistRepository, tmdb: TmdbClient | None
    ) -> dict[str, Any]:
        """Process chat message, recognize intents (auto-monitoring, ratings, status, search), update history, and generate response."""
        settings = repo.get_agent_settings(user_id)
        history = repo.list_chat_messages(user_id, limit=20)

        actions_taken = []
        context_notes: list[str] = []
        msg_lower = user_message.lower().strip()
        user_items = repo.list_items(user_id)

        # Handle 5-movie quiz request
        if any(phrase in msg_lower for phrase in [
            "quiz me", "5 movies", "have i seen", "have you seen", "ask me about 5 movies",
            "movie quiz", "rate 5 movies", "rate movies", "movies quiz"
        ]):
            quiz_movies = await AiAgentService.generate_movie_quiz(user_id, repo, tmdb)
            quiz_action = {"action": "movie_quiz", "movies": quiz_movies}
            actions_taken.append(quiz_action)
            q_titles = ", ".join([m["title"] for m in quiz_movies[:5]])
            context_notes.append(f"Movie Quiz Action Executed: Picked 5 movies for user quiz: {q_titles}. Invite user conversationally to rate them.")

        # Handle "Show my ratings" request
        elif any(phrase in msg_lower for phrase in [
            "my ratings", "show my ratings", "what movies have i rated",
            "list my ratings", "movies i rated", "rated movies", "my rated movies"
        ]):
            rated_list = repo.list_rated_movies(user_id)
            if rated_list:
                r_summary = "; ".join([f"{m['title']} ({m['rating']}/5 stars)" for m in rated_list[:5]])
                context_notes.append(f"User Ratings List Action: User has rated {len(rated_list)} titles: {r_summary}. Summarize these ratings conversationally.")
            else:
                context_notes.append("User Ratings List Action: User has no rated movies yet. Let them know warmly.")

        # Handle streaming recommendation request
        elif any(phrase in msg_lower for phrase in [
            "streaming recommendation", "free movie", "rent movie", "where to stream",
            "stream recommendation", "free streaming"
        ]):
            rec_action = await AiAgentService.generate_streaming_recommendation(user_id, repo, tmdb)
            if rec_action:
                actions_taken.append(rec_action)
                context_notes.append(f"Streaming Recommendation Action Executed: Found '{rec_action['title']}' ({rec_action['details_text']}). Overview: {rec_action.get('overview', '')}. Present this recommendation conversationally.")
            else:
                context_notes.append("Streaming Recommendation Action: No specific free/rental recommendation found right now.")

        # Extract intent titles first to check for explicit movie/series names
        rate_title, rating_val = AiAgentService._extract_rating_action(user_message)
        ext_title, target_price = AiAgentService._extract_title_and_price(user_message)
        explicit_title_raw = rate_title or ext_title
        parsed_title, start_idx, end_idx, is_range = AiAgentService._parse_ordinal_range(explicit_title_raw) if explicit_title_raw else (None, None, None, False)

        ignored_words = {"those", "them", "these", "it", "remaining", "movies", "films", "all", "yes", "sure", "add", "rate", "and", "the", "a", "an", "list", "queue"}
        parsed_words = set(re.findall(r'\w+', (parsed_title or "").lower()))
        has_explicit_title = bool(parsed_title and len(parsed_words - ignored_words) > 0 and len(parsed_title) > 1)

        # 0. Intent Recognition: Conversational Context / Pronoun Action (ONLY if NO explicit title is named)
        pronoun_words = ["those", "them", "these", "it", "the remaining ones", "those movies", "the movies", "all of them", "yes add", "yes rate", "do it", "sure", "add those", "rate those"]
        is_pronoun_ref = not has_explicit_title and any(p in msg_lower for p in pronoun_words)
        if is_pronoun_ref and history:
            recent_titles = AiAgentService._extract_titles_from_recent_history(history)
            if recent_titles:
                rate_val = None
                num_m = re.search(r'(?:(\d)\s*(?:-\s*)?stars?|(\d)\s*/\s*5|rated?\s+(\d)|rating\s+(?:of\s+)?(\d)|give\s+(?:it|them|those)?\s*(\d)|log\s+(?:my\s+)?(\d)|rate\s+(?:it|them|those|these|all|each)?\s*(\d)|and\s+rate\s+(?:it|them|those|these|all|each)?\s*(\d))', msg_lower)
                if num_m:
                    val = next(g for g in num_m.groups() if g is not None)
                    try:
                        rate_val = int(val)
                    except ValueError:
                        pass
                if rate_val is None and any(k in msg_lower for k in ["rate", "rating", "rated", "stars", "star"]):
                    rate_val = 5

                has_rate_intent = rate_val is not None or any(k in msg_lower for k in ["rate", "rating", "rated", "stars", "star"])
                has_add_intent = any(k in msg_lower for k in ["add", "queue", "watchlist", "list", "put", "insert", "log"]) or not has_rate_intent

                processed_count = 0
                from app.models import poster_url
                for title_item in recent_titles:
                    t_name = title_item
                    m_type = "movie"
                    t_id = None
                    p_path = None
                    r_date = None

                    if tmdb:
                        try:
                            res_p = await AiAgentService._search_tmdb_with_fallback(tmdb, title_item, user_id, user_message)
                            if res_p:
                                best = next((c for c in res_p if title_item.lower() in (c.get("title") or c.get("name") or "").lower() or (c.get("title") or c.get("name") or "").lower() in title_item.lower()), res_p[0])
                                t_name = best.get("title") or best.get("name") or title_item
                                m_type = best.get("media_type", "movie")
                                t_id = best.get("id")
                                r_date = best.get("release_date")
                                p_path = best.get("poster_path")
                        except Exception:
                            pass

                    if t_id:
                        if has_rate_intent:
                            try:
                                repo.rate_movie(user_id, m_type, t_id, t_name, p_path, r_date, rate_val or 5)
                                match_item = next((i for i in user_items if i.get("tmdb_id") == t_id and i.get("media_type") == m_type), None)
                                if match_item:
                                    repo.update_item(user_id, m_type, t_id, status="watched", user_rating=rate_val or 5)
                                actions_taken.append({
                                    "action": "rate_movie",
                                    "title": t_name,
                                    "rating": rate_val or 5,
                                    "media_type": m_type,
                                    "tmdb_id": t_id,
                                    "poster_path": p_path,
                                    "poster_url": poster_url(p_path) if p_path else None,
                                    "release_date": r_date,
                                })
                            except Exception as e:
                                logger.warning(f"Error rating title '{t_name}' via pronoun ref: {e}")

                        if has_add_intent:
                            try:
                                repo.add_item(
                                    user_id=user_id,
                                    media_type=m_type,
                                    tmdb_id=t_id,
                                    title=t_name,
                                    poster_path=p_path,
                                    release_date=r_date,
                                    status="queue",
                                )
                                actions_taken.append({
                                    "action": "add_monitoring",
                                    "title": t_name,
                                    "media_type": m_type,
                                    "tmdb_id": t_id,
                                })
                            except DuplicateItemError:
                                pass
                            except Exception as e:
                                logger.warning(f"Error adding title '{t_name}' to queue via pronoun ref: {e}")

                        processed_count += 1

                if processed_count > 0:
                    context_notes.append(f"Conversational Context Action Executed: Processed batch request for {processed_count} titles from recent conversation: {', '.join(recent_titles[:5])}.")

        # 1. Intent Recognition: Movie Rating / Watched List Action
        rate_title, rating_val = AiAgentService._extract_rating_action(user_message)
        if rate_title and not actions_taken:
            search_title, start_idx, end_idx, is_range = AiAgentService._parse_ordinal_range(rate_title)
            if not search_title:
                search_title = rate_title

            clean_msg_for_series = re.sub(r'\b(?:to|in|into|on|as)\s+(?:my\s+)?(?:movies?\s+(?:i\s*\'?ve?\s+)?watched|watched\s+list|watched|rated\s+movies?|rated\s+list|ratings?|list|lis|watchlist|queue)\b', '', user_message, flags=re.IGNORECASE).strip()
            is_series_req = is_range or any(k in clean_msg_for_series.lower() for k in ["series", "collection", "franchise", "trilogy", "all movies", "all films", "movie series", "film series", "set of movies", "all the", "all of the", "remaining", "rest of"])

            t_name = rate_title
            m_type = "movie"
            t_id = None
            p_path = None
            r_date = None
            candidates = []

            # Search local user watchlist & rated movies first
            all_local = repo.list_items(user_id) + repo.list_rated_movies(user_id)
            match_local = next((i for i in all_local if search_title.lower() in (i.get("title") or "").lower()), None)
            if match_local:
                t_name = match_local.get("title", search_title)
                m_type = match_local.get("media_type", "movie")
                t_id = match_local.get("tmdb_id")
                p_path = match_local.get("poster_path")
                r_date = match_local.get("release_date")

            if tmdb:
                try:
                    res = await AiAgentService._search_tmdb_with_fallback(tmdb, search_title, user_id, user_message)
                    if res:
                        if is_series_req:
                            filtered = [c for c in res if (c.get("title") or c.get("name"))]
                            start_pos = max(0, (start_idx or 1) - 1)
                            end_pos = end_idx if end_idx is not None else len(filtered)
                            candidates = filtered[start_pos:end_pos]
                        else:
                            candidates = res[:3]

                        if not t_id and candidates:
                            best = candidates[0]
                            t_name = best.get("title") or best.get("name") or rate_title
                            m_type = best.get("media_type", "movie")
                            t_id = best.get("id")
                            r_date = best.get("release_date")
                            p_path = best.get("poster_path")
                except Exception as e:
                    logger.warning(f"Error searching TMDB for rating title '{search_title}': {e}")

            if is_series_req and candidates and len(candidates) > 1:
                rated_count = 0
                for cand in candidates:
                    c_title = cand.get("title") or cand.get("name")
                    c_type = cand.get("media_type", "movie")
                    c_id = cand.get("id")
                    c_date = cand.get("release_date")
                    c_poster = cand.get("poster_path")
                    if c_id and c_title:
                        try:
                            repo.rate_movie(user_id, c_type, c_id, c_title, c_poster, c_date, rating_val or 5)
                            match_item = next((i for i in user_items if i.get("tmdb_id") == c_id and i.get("media_type") == c_type), None)
                            if match_item:
                                repo.update_item(user_id, c_type, c_id, status="watched", user_rating=rating_val or 5)
                            from app.models import poster_url
                            actions_taken.append({
                                "action": "rate_movie",
                                "title": c_title,
                                "rating": rating_val or 5,
                                "media_type": c_type,
                                "tmdb_id": c_id,
                                "poster_path": c_poster,
                                "poster_url": poster_url(c_poster) if c_poster else None,
                                "release_date": c_date,
                            })
                            rated_count += 1
                        except Exception as e:
                            logger.warning(f"Error saving series rating for '{c_title}': {e}")
                if rated_count > 0:
                    repo.add_query_memory(user_id, user_message, title=rate_title)
                    context_notes.append(f"Rating Action Executed: Rated all {rated_count} movies in the '{search_title}' series {rating_val or 5}/5 stars and added them to user's watched/ratings list.")
            elif t_id:
                try:
                    repo.rate_movie(
                        user_id=user_id,
                        media_type=m_type,
                        tmdb_id=t_id,
                        title=t_name,
                        poster_path=p_path,
                        release_date=r_date,
                        rating=rating_val or 5,
                    )
                    # If item exists in user queue/watchlist, update status to 'watched' as well
                    match_item = next((i for i in user_items if i.get("tmdb_id") == t_id and i.get("media_type") == m_type), None)
                    if match_item:
                        repo.update_item(user_id, m_type, t_id, status="watched", user_rating=rating_val or 5)

                    from app.models import poster_url
                    actions_taken.append({
                        "action": "rate_movie",
                        "title": t_name,
                        "rating": rating_val or 5,
                        "media_type": m_type,
                        "tmdb_id": t_id,
                        "poster_path": p_path,
                        "poster_url": poster_url(p_path) if p_path else None,
                        "release_date": r_date,
                    })
                    repo.add_query_memory(user_id, user_message, tmdb_id=t_id, media_type=m_type, title=t_name)
                    context_notes.append(f"Rating Action Executed: Rated '{t_name}' ({m_type}) {rating_val or 5}/5 stars and added to user's watched/ratings list.")

                    # Disambiguation note if multiple candidates exist
                    if len(candidates) > 1 and candidates[0].get("title") != candidates[1].get("title"):
                        other_titles = [f"{c.get('title') or c.get('name')} ({c.get('release_date', '')[:4]})" for c in candidates[1:3] if c.get('title') or c.get('name')]
                        if other_titles:
                            context_notes.append(f"Disambiguation Note: Top search result '{t_name}' was rated. Other candidate matches found: {', '.join(other_titles)}.")
                except Exception as e:
                    logger.warning(f"Error saving rating for '{t_name}': {e}")

            if not any(a.get("action") == "rate_movie" for a in actions_taken):
                logger.warning(
                    f"[AI Agent Rating Execution Failure] Could not find or rate items for title: '{rate_title}'. Prompt: '{user_message}'",
                    extra=sanitize_log_data({
                        "ai_event": "rating_execution_failure",
                        "rate_title": rate_title,
                        "user_id": user_id,
                    })
                )
                context_notes.append(f"[ACTION FAILURE]: Rating action could NOT be saved to the database because no matching titles for '{rate_title}' were found on TMDB. Inform the user conversationally that you could not find or log ratings for this title/series. DO NOT claim that you added or rated them.")

        # 2. Intent Recognition: Deletion Action (Remove rating or item)
        del_title, del_target = AiAgentService._extract_delete_action(user_message)
        if del_title:
            if del_target == "rating":
                rated = repo.list_rated_movies(user_id)
                match_r = next((r for r in rated if del_title.lower() in (r.get("title") or "").lower()), None)
                if match_r:
                    repo.delete_rated_movie(user_id, match_r.get("media_type", "movie"), match_r["tmdb_id"])
                    actions_taken.append({
                        "action": "delete_rating",
                        "title": match_r["title"],
                    })
                    context_notes.append(f"Delete Action Executed: Deleted user rating for '{match_r['title']}'.")
            else:
                items = repo.list_items(user_id)
                match_i = next((i for i in items if del_title.lower() in (i.get("title") or "").lower()), None)
                if match_i:
                    repo.remove_item(user_id, match_i.get("media_type", "movie"), match_i["tmdb_id"])
                    actions_taken.append({
                        "action": "remove_item",
                        "title": match_i["title"],
                    })
                    context_notes.append(f"Remove Action Executed: Removed '{match_i['title']}' from queue.")

        # 3. Intent Recognition: Status & Ownership Update Action
        status_title, new_status, is_owned_flag = AiAgentService._extract_status_action(user_message)
        if status_title and not any(a.get("action") == "rate_movie" for a in actions_taken):
            items = repo.list_items(user_id)
            match_i = next((i for i in items if status_title.lower() in (i.get("title") or "").lower()), None)
            if match_i:
                repo.update_item(
                    user_id,
                    match_i["media_type"],
                    match_i["tmdb_id"],
                    status=new_status,
                    is_owned=is_owned_flag,
                )
                act_desc = f"Updated status of '{match_i['title']}' to {new_status or 'updated'}"
                if is_owned_flag is True:
                    act_desc += " and marked as owned"
                actions_taken.append({
                    "action": "update_status",
                    "title": match_i["title"],
                    "status": new_status,
                    "is_owned": is_owned_flag,
                })
                context_notes.append(f"Status Update Action Executed: {act_desc}.")

        # 4. Intent Recognition: Auto-Monitoring / Add to Queue Execution
        ext_title, target_price = AiAgentService._extract_title_and_price(user_message)
        already_acted = any(
            (a.get("title") or "").lower() in (ext_title or "").lower() or (ext_title or "").lower() in (a.get("title") or "").lower()
            for a in actions_taken
        ) or (rate_title and ext_title and rate_title.lower() in ext_title.lower())
        if ext_title and tmdb and not already_acted:
            try:
                search_queue_title, q_start_idx, q_end_idx, q_is_range = AiAgentService._parse_ordinal_range(ext_title)
                if not search_queue_title:
                    search_queue_title = ext_title

                clean_ext_series = re.sub(r'\b(?:to|in|into|on|as)\s+(?:my\s+)?(?:list|lis|watchlist|queue|monitoring)\b', '', user_message, flags=re.IGNORECASE).strip()
                is_series_queue = q_is_range or any(k in clean_ext_series.lower() for k in ["series", "collection", "franchise", "trilogy", "all movies", "all films", "movie series", "film series", "set of movies", "all the", "all of the", "remaining", "rest of"])

                res = await AiAgentService._search_tmdb_with_fallback(tmdb, search_queue_title, user_id, user_message)
                if res:
                    if is_series_queue and len(res) > 1:
                        filtered = [c for c in res if (c.get("title") or c.get("name"))]
                        q_start_pos = max(0, (q_start_idx or 1) - 1)
                        q_end_pos = q_end_idx if q_end_idx is not None else len(filtered)
                        target_cand = filtered[q_start_pos:q_end_pos]

                        added_count = 0
                        for best in target_cand:
                            t_name = best.get("title") or best.get("name")
                            m_type = best.get("media_type", "movie")
                            t_id = best.get("id")
                            r_date = best.get("release_date")
                            p_path = best.get("poster_path")
                            if t_id and t_name:
                                try:
                                    repo.add_item(
                                        user_id=user_id,
                                        media_type=m_type,
                                        tmdb_id=t_id,
                                        title=t_name,
                                        poster_path=p_path,
                                        release_date=r_date,
                                        status="queue",
                                        target_rental_price=target_price,
                                    )
                                except DuplicateItemError:
                                    if target_price is not None:
                                        repo.update_item(user_id, m_type, t_id, target_rental_price=target_price)
                                actions_taken.append({
                                    "action": "add_monitoring",
                                    "title": t_name,
                                    "media_type": m_type,
                                    "tmdb_id": t_id,
                                    "target_rental_price": target_price,
                                })
                                added_count += 1
                        if added_count > 0:
                            repo.add_query_memory(user_id, user_message, title=search_queue_title)
                            context_notes.append(f"Add Queue Action Executed: Added all {added_count} titles in the '{search_queue_title}' series to user queue.")
                    else:
                        best = res[0]
                        t_name = best.get("title") or best.get("name") or ext_title
                        m_type = best.get("media_type", "movie")
                        t_id = best.get("id")
                        r_date = best.get("release_date")
                        p_path = best.get("poster_path")

                        try:
                            repo.add_item(
                                user_id=user_id,
                                media_type=m_type,
                                tmdb_id=t_id,
                                title=t_name,
                                poster_path=p_path,
                                release_date=r_date,
                                status="queue",
                                target_rental_price=target_price,
                            )
                        except DuplicateItemError:
                            if target_price is not None:
                                repo.update_item(user_id, m_type, t_id, target_rental_price=target_price)

                        actions_taken.append({
                            "action": "add_monitoring",
                            "title": t_name,
                            "media_type": m_type,
                            "tmdb_id": t_id,
                            "target_rental_price": target_price,
                        })
                        repo.add_query_memory(user_id, user_message, tmdb_id=t_id, media_type=m_type, title=t_name)
                        context_notes.append(f"Add Queue Action Executed: Added '{t_name}' ({m_type}) to queue.")
            except Exception as e:
                logger.warning(f"Error auto-monitoring title '{ext_title}': {e}")

        # 5. Intent Recognition: Explicit Movie Search Action
        search_query = AiAgentService._extract_search_action(user_message)
        if search_query and tmdb and not actions_taken:
            try:
                res = await AiAgentService._search_tmdb_with_fallback(tmdb, search_query, user_id, user_message)
                if res:
                    from app.models import poster_url
                    search_results = []
                    for item in res[:4]:
                        p_path = item.get("poster_path")
                        search_results.append({
                            "tmdb_id": item["id"],
                            "media_type": item.get("media_type", "movie"),
                            "title": item.get("title") or item.get("name"),
                            "poster_path": p_path,
                            "poster_url": poster_url(p_path) if p_path else None,
                            "release_date": item.get("release_date"),
                            "overview": (item.get("overview") or "")[:140],
                        })
                    actions_taken.append({
                        "action": "movie_search",
                        "query": search_query,
                        "results": search_results,
                    })
                    s_titles = ", ".join([r["title"] for r in search_results])
                    context_notes.append(f"Movie Search Action Executed: Searched TMDB for '{search_query}'. Found options: {s_titles}. Present these options conversationally and invite user to select or rate them.")
                else:
                    context_notes.append(f"Movie Search Action: Searched for '{search_query}', but no results were found on TMDB.")
            except Exception as e:
                logger.warning(f"Error executing movie search for '{search_query}': {e}")

        items = repo.list_items(user_id)
        monitored = [item for item in items if not item.get("is_owned") and (item.get("status") in {"following", "queue", "watchlist"} or not item.get("status"))]

        # Action execution note
        if actions_taken:
            act_strings = []
            for a in actions_taken:
                act = a.get("action")
                t = a.get("title", "title")
                if act == "rate_movie":
                    act_strings.append(f"Logged {a.get('rating', 5)}-star rating for '{t}'")
                elif act == "delete_rating":
                    act_strings.append(f"Deleted rating for '{t}'")
                elif act == "remove_item":
                    act_strings.append(f"Removed '{t}' from queue")
                elif act == "add_monitoring":
                    act_strings.append(f"Added '{t}' to queue")
                elif act == "update_status":
                    act_strings.append(f"Updated status for '{t}'")
                elif act == "movie_search":
                    act_strings.append(f"Searched movies for '{a.get('query', '')}'")
            context_notes.append(f"Automated action executed: {'; '.join(act_strings)}. Inform the user conversationally that this action was completed.")

        title_query = ext_title or rate_title or search_query
        if not title_query:
            title_patterns = [
                r"(?:any\s+)?(?:update|updates|news|info|word)\s+(?:on|about|for)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
                r"(?:why\s+didn't\s+the\s+agent\s+say\s+something\s+about|why\s+didn't\s+you\s+mention|what\s+about|tell\s+me\s+about|is\s+there\s+any\s+update\s+on|how\s+about|info\s+on|status\s+of)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
                r"(?:is|when\s+(?:is|does))\s+['\"]?([^'.\"$\n]+?)['\"]?\s+(?:releasing|release|coming\s+out|available|dropping)",
                r"(?:search|find|check)\s+(?:for\s+)?['\"]?([^'.\"$\n]+?)['\"]?$",
            ]
            for pat in title_patterns:
                m = re.search(pat, msg_lower, re.IGNORECASE)
                if m:
                    extracted = m.group(1).strip()
                    extracted = re.sub(r'\s+(?:released|available|coming|out|today|soon)$', '', extracted, flags=re.IGNORECASE).strip()
                    if extracted and len(extracted) > 1:
                        match_item = next((i for i in items if extracted.lower() in (i.get("title") or "").lower()), None)
                        title_query = match_item.get("title", extracted) if match_item else extracted
                        break

        # Title-specific context lookup
        if title_query:
            repo.add_query_memory(user_id, user_message, title=title_query)
            exact_matches = [i for i in items if title_query.lower() in i.get("title", "").lower()]
            partial_matches = [
                i for i in items
                if any(w in i.get("title", "").lower() for w in title_query.split() if len(w) > 3 and w.lower() not in {"title", "movie", "show", "season"})
            ]
            matching_user_items = exact_matches or partial_matches

            if matching_user_items:
                item = matching_user_items[0]
                t_title = item.get("title")
                status_str = "monitored" if item.get("status") in {"following", "queue"} else item.get("status")
                rel_date = item.get("release_date")
                from app.models import days_until
                days = days_until(rel_date) if rel_date else None
                days_desc = f" (Releasing in {days} days on {rel_date})" if days and days > 0 else (f" (Released {abs(days)} days ago on {rel_date})" if days and days < 0 else (f" (Releasing TODAY {rel_date})" if days == 0 else f" (Release date: {rel_date})"))
                context_notes.append(f"Title Information: User asked about '{t_title}'. Item IS in user's queue. Status: {status_str}{days_desc}.")
            elif tmdb:
                try:
                    res = await tmdb.search(title_query)
                    if res:
                        best = res[0]
                        t_title = best.get("title") or best.get("name")
                        rel_date = best.get("release_date")
                        media_type = best.get("media_type", "movie")
                        rel_str = f" ({rel_date})" if rel_date else ""
                        context_notes.append(f"Title Information: User asked about '{t_title}'. Found on TMDB: '{t_title}' ({media_type}{rel_str}). It is NOT currently in user's queue.")
                    else:
                        context_notes.append(f"Title Information: User asked about '{title_query}'. No matching show/movie found in user's queue or TMDB.")
                except Exception as e:
                    logger.warning(f"Error resolving title search for LLM context: {e}")

        # Recommendation request context lookup
        recommend_keywords = ["recommend", "suggest", "what to watch", "what should i watch", "movie idea", "show idea", "something like"]
        is_rec_query = any(k in msg_lower for k in recommend_keywords)
        if is_rec_query:
            rated_items = repo.list_rated_movies(user_id)
            top_rated = [i for i in rated_items if (i.get("rating") or 0) >= 4]
            if top_rated:
                context_notes.append(f"User Taste Preferences: User loved {[r['title'] for r in top_rated[:3]]}.")

        # Queue summary context lookup
        queue_summary_keywords = ["my queue", "my list", "all updates", "monitored shows", "what updates", "show list", "monitoring", "upcoming"]
        if any(k in msg_lower for k in queue_summary_keywords):
            if monitored:
                m_titles = [f"{i['title']} ({i.get('status', 'queue')})" for i in monitored[:10]]
                context_notes.append(f"Monitored Queue Items:\n" + "\n".join([f"- {t}" for t in m_titles]))
            else:
                context_notes.append("Monitored Queue Items: None currently monitored.")

        holiday_remark = get_approaching_holiday_or_season()
        if holiday_remark:
            context_notes.append(f"Holiday Remark: {holiday_remark}")

        # User Ratings context for recommendations
        rated_items = [i for i in items if i.get("user_rating")]
        top_rated_items = [i for i in rated_items if (i.get("user_rating") or 0) >= 4]

        # Check if user is asking for a movie/show recommendation
        recommend_keywords = ["recommend", "suggest", "what to watch", "what should i watch", "movie idea", "show idea", "something like"]
        is_rec_query = any(k in msg_lower for k in recommend_keywords)

        rating_rec_note = ""
        if is_rec_query and top_rated_items and tmdb:
            try:
                import random
                sample_top = random.choice(top_rated_items)
                t_type = sample_top.get("media_type", "movie")
                t_id = sample_top.get("tmdb_id")
                if t_id:
                    recs = await tmdb.get_recommendations(t_type, t_id)
                    if recs:
                        r_title = recs[0].get("title")
                        r_overview = recs[0].get("overview", "")
                        rating_rec_note = f"\n[System Note: Recommendation Request: The user asked for a recommendation. User loved '{sample_top['title']}' (rated {sample_top['user_rating']}/5 stars). Suggest '{r_title}' which is similar, mentioning why they might like it: {r_overview[:120]}...]"
            except Exception as e:
                logger.warning(f"Error generating recommendation from ratings: {e}")

        location = settings.get("location", "").strip()
        weather_report = await WeatherService.get_weather_report(location) if location else None
        system_prompt = get_system_prompt(settings, weather_report)

        result = await AiAgentService._call_gemini_api(
            system_instruction=system_prompt,
            recent_history=history[-6:],
            user_message=user_message,
            context_notes=context_notes,
            caller="chat_processor",
            user_id=user_id,
            repo=repo,
        )

        agent_reply = result.text

        if not agent_reply or result.fallback_used:
            agent_reply = AiAgentService._generate_fallback_chat_reply(
                system_prompt=system_prompt,
                user_message=user_message,
                actions=actions_taken,
                title_query=title_query,
            )

        # Save assistant message
        msg_record = repo.add_chat_message(user_id, "assistant", agent_reply, actions=actions_taken)

        # Record decision log for telemetry & usage logs view
        try:
            import datetime, uuid
            chat_log = {
                "log_id": f"chat_{uuid.uuid4().hex[:12]}",
                "event_type": "chat_llm_generation",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "user_id": user_id,
                "session_id": None,
                "model_requested": result.model_requested,
                "model_used": result.model_used,
                "gemini_called": result.gemini_called,
                "fallback_used": result.fallback_used,
                "fallback_reason": result.fallback_reason,
                "decision_config_version": 1,
                "prompt_version": 1,
                "required_candidates": [],
                "optional_candidates": [],
                "selected_candidates": [],
                "excluded_candidates": [],
                "random_rolls": {},
                "cooldowns_applied": [],
                "selection_summary": (
                    f"Caller: {result.caller} | Model: {result.model_used or result.model_requested} | "
                    f"Tokens: {result.prompt_token_count} prompt + {result.response_token_count} response = {result.total_token_count} total | "
                    f"Est Cost: ${result.estimated_cost_usd:.8f} | Latency: {result.request_duration_ms or 0}ms"
                ),
                "sanitized_prompt": user_message,
                "raw_model_response": agent_reply,
                "final_response": agent_reply,
                "request_duration_ms": result.request_duration_ms or 0.0,
            }
            if hasattr(repo, "add_decision_log"):
                repo.add_decision_log(chat_log)
        except Exception as e:
            logger.warning(f"Error recording chat telemetry decision log: {e}")

        return {
            "message": msg_record,
            "actions_taken": actions_taken,
            "telemetry": result.to_dict(),
        }

    @staticmethod
    def _parse_ordinal_range(text: str) -> tuple[str, int | None, int | None, bool]:
        """Parse ordinal/range expressions from query text (e.g. '2nd through the end of the harry potter movies')."""
        clean_text = text.strip()
        msg_lower = clean_text.lower()
        start_idx = None
        end_idx = None
        is_range = False

        # Pattern 1: "2nd through the end of ...", "2nd to the end of ...", "2nd through end of ..."
        m1 = re.search(r'\b(?:the\s+)?(\d+)(?:st|nd|rd|th)?\s+(?:through|to|till|until)\s+(?:the\s+)?(?:end|last)\s+(?:of\s+)?(?:the\s+)?', msg_lower)
        if m1:
            start_idx = int(m1.group(1))
            end_idx = None
            is_range = True
            clean_text = re.sub(r'\b(?:the\s+)?\d+(?:st|nd|rd|th)?\s+(?:through|to|till|until)\s+(?:the\s+)?(?:end|last)\s+(?:of\s+)?(?:the\s+)?', '', clean_text, flags=re.IGNORECASE).strip()

        # Pattern 2: "from (the) 2nd to (the) 5th ...", "movies 2 through 8 of ..."
        if not is_range:
            m2 = re.search(r'\b(?:from\s+)?(?:the\s+)?(\d+)(?:st|nd|rd|th)?\s+(?:through|to|till|until|-)\s+(?:the\s+)?(\d+)(?:st|nd|rd|th)?\s*(?:of|in)?\s*(?:the\s+)?', msg_lower)
            if m2:
                start_idx = int(m2.group(1))
                end_idx = int(m2.group(2))
                is_range = True
                clean_text = re.sub(r'\b(?:from\s+)?(?:the\s+)?\d+(?:st|nd|rd|th)?\s+(?:through|to|till|until|-)\s+(?:the\s+)?\d+(?:st|nd|rd|th)?\s*(?:of|in)?\s*(?:the\s+)?', '', clean_text, flags=re.IGNORECASE).strip()

        # Pattern 3: "the rest of ...", "remaining ...", "all ... except the first"
        if not is_range:
            if any(k in msg_lower for k in ["rest of", "remaining", "except the first", "from the second", "after the first"]):
                start_idx = 2
                end_idx = None
                is_range = True
                clean_text = re.sub(r'\b(?:the\s+)?(?:rest\s+of|remaining|movies\s+after\s+the\s+first|all\s+except\s+the\s+first)\s+(?:the\s+)?', '', clean_text, flags=re.IGNORECASE).strip()

        # Pattern 4: "the 2nd movie of ..."
        if not is_range:
            m4 = re.search(r'\b(?:the\s+)?(\d+)(?:st|nd|rd|th)\s+(?:movie|film|installment|part)\s+(?:of\s+)?(?:the\s+)?', msg_lower)
            if m4:
                start_idx = int(m4.group(1))
                end_idx = start_idx
                is_range = True
                clean_text = re.sub(r'\b(?:the\s+)?\d+(?:st|nd|rd|th)\s+(?:movie|film|installment|part)\s+(?:of\s+)?(?:the\s+)?', '', clean_text, flags=re.IGNORECASE).strip()

        # Clean series descriptors
        clean_text = re.sub(r'\b(?:the\s+)?(?:series|collection|franchise|trilogy|all\s+(?:the\s+)?movies?|all\s+(?:the\s+)?films?|movie\s+series|film\s+series|set\s+of\s+movies|movies?|films?)\s*(?:of)?\b', '', clean_text, flags=re.IGNORECASE).strip()
        clean_text = re.sub(r'\s+(?:series|collection|franchise|trilogy|movies|films)$', '', clean_text, flags=re.IGNORECASE).strip()

        return clean_text, start_idx, end_idx, is_range

    @staticmethod
    def _extract_titles_from_recent_history(history: list[dict[str, Any]]) -> list[str]:
        """Extract titles from recent assistant messages when user refers back with pronouns ('those', 'them')."""
        titles = []
        for msg in reversed(history):
            if msg.get("role") in {"assistant", "model"}:
                actions = msg.get("actions") or []
                for act in actions:
                    if act.get("action") == "movie_search" and act.get("results"):
                        for r in act["results"]:
                            if r.get("title"):
                                titles.append(r["title"])
                    elif act.get("action") == "movie_quiz" and act.get("movies"):
                        for m in act["movies"]:
                            if m.get("title"):
                                titles.append(m["title"])

                content = msg.get("content", "")
                italic_titles = re.findall(r'\*([^*]{2,70})\*', content)
                for t in italic_titles:
                    t_clean = t.strip()
                    if t_clean and t_clean.lower() not in {"my algorithms suggest", "cinequeue"} and len(t_clean) > 2:
                        if t_clean not in titles:
                            titles.append(t_clean)

                if titles:
                    break
        return titles

    @staticmethod
    def _extract_rating_action(text: str) -> tuple[str | None, int | None]:
        """Extract movie/tv title and rating (1-5 stars) from user prompt."""
        clean_text = text.strip()
        msg_lower = clean_text.lower()

        if any(k in msg_lower for k in ["remove", "delete", "unrate", "clear"]) or any(q in msg_lower for q in ["show my", "list my", "what movies have i", "my ratings"]):
            return None, None

        has_rate_intent = any(k in msg_lower for k in [
            "watched", "rating", "rated", "rate", "stars", "star", "seen", "log"
        ])
        if not has_rate_intent:
            return None, None

        rating = None
        num_match = re.search(r'(?:(\d)\s*(?:-\s*)?stars?|(\d)\s*/\s*5|rated?\s+(\d)|rating\s+(?:of\s+)?(\d)|give\s+(?:it|them|those)?\s*(\d)|log\s+(?:my\s+)?(\d)|rate\s+(?:it|them|those|these|all|each)?\s*(\d)|and\s+rate\s+(?:it|them|those|these|all|each)?\s*(\d))', msg_lower)
        if num_match:
            val = next(g for g in num_match.groups() if g is not None)
            try:
                rating = int(val)
            except ValueError:
                pass
        else:
            word_map = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            for word, val in word_map.items():
                if re.search(rf'\b{word}\s*(?:-\s*)?stars?\b', msg_lower):
                    rating = val
                    break

        if rating is None:
            if any(p in msg_lower for p in ["watched list", "rated movies", "log rating", "rate movie", "rated list", "list of rated", "watched"]):
                rating = 5

        if rating is not None:
            rating = max(1, min(5, rating))

        title_str = clean_text

        # Strip leading verbs/intent phrases including polite expressions (e.g., "please add", "can you rate")
        prefix_patterns = [
            r"^(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)*(?:add|put|log|insert|record|rate|give|set)\s+(?:a|an|the|my)?\s*(?:\d\s*(?:-\s*)?stars?\s+)?(?:rating\s+for\s+)?",
            r"^(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)*(?:i\s+(?:have\s+)?(?:watched|seen))\s+",
            r"^(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)*(?:rate)\s+",
            r"^(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)*(?:give)\s+",
        ]
        for p in prefix_patterns:
            title_str = re.sub(p, "", title_str, flags=re.IGNORECASE).strip()

        # Remove destination clauses (including typos like "to the lis", "to list", "watched list")
        dest_patterns = [
            r"\bto\s+(?:my\s+)?(?:movies?\s+(?:i\s*\'?ve?\s+)?watched|watched\s+list|watched|rated\s+movies?|rated\s+list|ratings?|list|lis|watchlist|queue)\b",
            r"\b(?:in|into|on|as)\s+(?:my\s+)?(?:movies?\s+(?:i\s*\'?ve?\s+)?watched|watched\s+list|watched|rated\s+movies?|rated\s+list|ratings?|list|lis|watchlist|queue)\b",
        ]
        for dp in dest_patterns:
            title_str = re.sub(dp, "", title_str, flags=re.IGNORECASE).strip()

        # Remove rating clauses
        rating_patterns = [
            r"\b(?:and\s+)?(?:rate|rating|give)\s+(?:it|them|those|these|all|each)?\s*(?:\d|one|two|three|four|five)(?:\s*stars?)?\b",
            r"\bwith\s+(?:a\s+)?(?:\d|one|two|three|four|five)\s*stars?\b",
            r"\b(?:\d|one|two|three|four|five)\s*stars?\b",
            r"\b(?:\d)\s*/\s*5\b",
            r"\brated\s+\d\b",
        ]
        for rp in rating_patterns:
            title_str = re.sub(rp, "", title_str, flags=re.IGNORECASE).strip()

        # Cleanup connector words, trailing rating details, and punctuation
        title_str = re.sub(r'^(?:for|about|a|an|the)\s+', '', title_str, flags=re.IGNORECASE).strip()
        title_str = re.sub(r'\s+(?:with|giving|and|rating|ratings|stars?|star|to|on|in|as|a|\d|\d/5)$', '', title_str, flags=re.IGNORECASE).strip()
        title_str = title_str.strip(' ,.-"\'')

        ignored_titles = {"movie", "show", "title", "watched list", "rated movies", "my rated movies", "it", "them", "this", "that", "something", "3-star", "4-star", "5-star", "watched"}
        ignored_prefixes = ("it ", "them ", "this ", "that ", "something ")

        if (
            title_str
            and len(title_str) > 1
            and title_str.lower() not in ignored_titles
            and not any(title_str.lower().startswith(p) for p in ignored_prefixes)
        ):
            return title_str, rating

        return None, None

    @staticmethod
    async def _search_tmdb_with_fallback(
        tmdb: TmdbClient,
        query: str,
        user_id: str = "unknown",
        user_message: str = "",
    ) -> list[dict[str, Any]]:
        """Search TMDB with query, falling back to stripped title if actor/detail clauses prevent exact matching, and log failure telemetry."""
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        res = await tmdb.search(clean_query)
        if res:
            return res

        # Fallback 1: Strip trailing actor/cast or release year annotations e.g. "The Patriot with Mel Gibson" -> "The Patriot"
        simplified = re.sub(r'\s+(?:with|starring|featuring|by|directed\s+by)\s+[A-Za-z\s]+$', '', clean_query, flags=re.IGNORECASE).strip()
        simplified = re.sub(r'\s*\(\d{4}\)', '', simplified).strip()

        if simplified and simplified.lower() != clean_query.lower():
            res_simp = await tmdb.search(simplified)
            if res_simp:
                actor_match = re.search(r'\b(?:with|starring|featuring)\s+([A-Za-z\s]+)$', clean_query, re.IGNORECASE)
                if actor_match:
                    actor_name = actor_match.group(1).strip().lower()
                    matched = [c for c in res_simp if actor_name in (c.get("overview") or "").lower() or actor_name in (c.get("title") or "").lower()]
                    if matched:
                        return matched
                return res_simp

        # Fallback 2: Log failure to retrieve so admins can inspect unretrieved queries
        logger.warning(
            f"[AI Agent TMDB Lookup Failure] No TMDB results found for search query '{clean_query}'. User prompt: '{user_message}'",
            extra=sanitize_log_data({
                "ai_event": "tmdb_lookup_failure",
                "query": clean_query,
                "user_message": user_message,
                "user_id": user_id,
            })
        )
        return []

    @staticmethod
    def _extract_delete_action(text: str) -> tuple[str | None, str | None]:
        """Extract movie title and target deletion type ('rating' or 'watchlist') from user prompt."""
        clean_text = text.strip()
        msg_lower = clean_text.lower()

        if not any(k in msg_lower for k in ["remove", "delete", "unrate", "clear"]):
            return None, None

        target_type = "rating" if any(k in msg_lower for k in ["rating", "rated", "unrate", "watched", "seen"]) else "watchlist"

        title_str = clean_text
        prefix_patterns = [
            r"^(?:remove|delete|clear|unrate)\s+(?:a|an|the|my)?\s*(?:rating\s+for\s+)?",
            r"^(?:delete\s+rating\s+for|unrate|remove\s+rating\s+for)\s+",
        ]
        for p in prefix_patterns:
            title_str = re.sub(p, "", title_str, flags=re.IGNORECASE).strip()

        dest_patterns = [
            r"\bfrom\s+(?:my\s+)?(?:movies?\s+(?:i\s*\'?ve?\s+)?watched|watched\s+list|watched|rated\s+movies?|rated\s+list|ratings?|queue|watchlist)\b",
        ]
        for dp in dest_patterns:
            title_str = re.sub(dp, "", title_str, flags=re.IGNORECASE).strip()

        title_str = re.sub(r'\s+(?:rating|ratings|list|queue|watchlist)$', '', title_str, flags=re.IGNORECASE).strip()
        title_str = re.sub(r'^(?:a|an|the|for|about)\s+', '', title_str, flags=re.IGNORECASE).strip()
        title_str = title_str.strip(' ,.-"\'')

        ignored_titles = {"movie", "show", "watchlist", "queue", "rating", "ratings"}

        if title_str and len(title_str) > 1 and title_str.lower() not in ignored_titles:
            return title_str, target_type

        return None, None


    @staticmethod
    def _extract_title_and_price(text: str) -> tuple[str | None, float | None]:
        """Extract title and optional target price from user prompt."""
        price_match = re.search(r'(?:\$|under\s+\$?|to\s+rent\s+for\s+\$?)\s*(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        target_price = float(price_match.group(1)) if price_match else None

        patterns = [
            r"(?:add|track|monitor|follow|enter|put|insert|save|log)\s+['\"]?([^'.\"$\n]+?)['\"]?\s+(?:to|into|in|on)\s+(?:my\s+)?(?:monitor\s+|watch\s*)?(?:list|queue|monitoring|watchlist)",
            r"(?:waiting|wait|looking)\s+for\s+(?:the\s+movie\s+|the\s+show\s+)?['\"]?([^'.\"$\n]+?)['\"]?\s*(?:to\s+(?:come|air|drop|rent|release)|under|\$|$)",
            r"(?:notify|alert|tell)\s+me\s+when\s+(?:the\s+movie\s+|the\s+show\s+)?['\"]?([^'.\"$\n]+?)['\"]?\s*(?:drops|is|available|to\s+rent|under|\$|$)",
            r"(?:add|track|monitor|enter|put|insert|save|log)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
            r"(?:waiting\s+for)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
            r"(?:can't|cant)\s+wait\s+for\s+['\"]?([^'.\"$\n]+?)['\"]?\s*(?:to\s+drop|to\s+rent|under|\$|$)",
        ]
        for p in patterns:
            m = re.search(p, text.strip(), re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                extracted = re.sub(r'\s+(?:to|for|under|on|in|drops)$', '', extracted, flags=re.IGNORECASE).strip()
                if extracted and len(extracted) > 1 and extracted.lower() not in {"my shows", "my queue", "monitored shows", "updates", "watchlist", "list"}:
                    return extracted, target_price

        return None, target_price

    @staticmethod
    def _extract_search_action(text: str) -> str | None:
        """Extract title to search for if the user has an explicit movie search intent."""
        clean_text = text.strip()
        msg_lower = clean_text.lower()
        search_patterns = [
            r"^(?:search|find|look\s+up|check|details\s+on|info\s+on|tell\s+me\s+about)\s+(?:for\s+)?['\"]?([^'.\"$\n]+?)['\"]?$",
            r"^(?:is|where\s+can\s+i\s+watch)\s+['\"]?([^'.\"$\n]+?)['\"]?\s+(?:available|streaming|releasing|out)?$",
        ]
        for p in search_patterns:
            m = re.search(p, msg_lower, re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                extracted = re.sub(r'\s+(?:released|available|coming|out|today|soon|movie|show)$', '', extracted, flags=re.IGNORECASE).strip()
                if extracted and len(extracted) > 1 and extracted not in {"the movie", "the show", "it", "something"}:
                    return extracted
        return None

    @staticmethod
    def _extract_status_action(text: str) -> tuple[str | None, str | None, bool | None]:
        """Extract movie title and requested status update ('watched', 'watching', 'queue', 'dropped') or ownership."""
        clean_text = text.strip()
        msg_lower = clean_text.lower()

        if not any(k in msg_lower for k in ["mark", "set status", "change status", "owned", "watching", "dropped"]):
            return None, None, None

        new_status = None
        if "watched" in msg_lower:
            new_status = "watched"
        elif "watching" in msg_lower:
            new_status = "watching"
        elif "dropped" in msg_lower:
            new_status = "dropped"
        elif "queue" in msg_lower or "watchlist" in msg_lower:
            new_status = "queue"

        is_owned = True if any(k in msg_lower for k in ["owned", "purchased", "bought", "have it on disc", "blu-ray", "dvd"]) else None

        title_str = clean_text
        prefix_patterns = [
            r"^(?:mark|set\s+status\s+of|change\s+status\s+of|set|change)\s+(?:a|an|the|my)?\s*",
        ]
        for p in prefix_patterns:
            title_str = re.sub(p, "", title_str, flags=re.IGNORECASE).strip()

        suffix_patterns = [
            r"\bas\s+(?:watched|watching|dropped|queue|owned|purchased)\b",
            r"\bto\s+(?:watched|watching|dropped|queue|owned|purchased)\b",
        ]
        for sp in suffix_patterns:
            title_str = re.sub(sp, "", title_str, flags=re.IGNORECASE).strip()

        title_str = re.sub(r'^(?:for|about|a|an|the)\s+', '', title_str, flags=re.IGNORECASE).strip()
        title_str = title_str.strip(' ,.-"\'')

        if title_str and len(title_str) > 1 and title_str.lower() not in {"movie", "show", "it", "status"}:
            return title_str, new_status, is_owned

        return None, None, None

    @staticmethod
    async def _call_gemini_api(
        system_instruction: str,
        recent_history: list[dict[str, str]] | str = [],
        user_message: str = "",
        context_notes: list[str] | None = None,
        max_output_tokens: int = 450,
        caller: str = "agent_service",
        user_id: str | None = None,
        session_id: str | None = None,
        repo: Any = None,
        daily_cache_key: str | None = None,
    ) -> AgentResult:
        """Call Gemini API via httpx using configurable model selection and native request structure."""
        if isinstance(recent_history, str):
            user_message = recent_history
            recent_history = []

        total_prompt_chars, prompt_breakdown = compute_prompt_metrics(
            system_instruction, recent_history, user_message, context_notes
        )

        if not GEMINI_API_KEY:
            est_p_tokens = max(1, total_prompt_chars // 4) if total_prompt_chars else 0
            est_cost = calculate_estimated_cost(GEMINI_PRIMARY_MODEL, est_p_tokens, 0)
            logger.info(
                f"[AI CALL TELEMETRY] Caller: '{caller}' | GEMINI_API_KEY missing. Fallback triggered.",
                extra=sanitize_log_data({
                    "provider": "fallback",
                    "caller": caller,
                    "fallback_reason": "api_key_missing",
                    "prompt_char_count": total_prompt_chars,
                    "prompt_token_count": est_p_tokens,
                    "prompt_breakdown": prompt_breakdown,
                })
            )
            return AgentResult(
                text="",
                provider="fallback",
                model_requested=GEMINI_PRIMARY_MODEL,
                model_used=None,
                gemini_called=False,
                fallback_used=True,
                fallback_reason="api_key_missing",
                http_status=None,
                request_duration_ms=None,
                actions_taken=[],
                caller=caller,
                prompt_char_count=total_prompt_chars,
                prompt_token_count=est_p_tokens,
                response_char_count=0,
                response_token_count=0,
                total_token_count=est_p_tokens,
                estimated_cost_usd=est_cost,
                finish_reason="API_KEY_MISSING",
                usage_metadata={},
                prompt_breakdown=prompt_breakdown,
            )

        models_to_try = [GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL]
        payload = build_gemini_request(
            system_instruction=system_instruction,
            recent_history=recent_history,
            user_message=user_message,
            context_notes=context_notes,
            max_output_tokens=max_output_tokens,
        )

        last_fallback_reason = "unknown_error"
        last_http_status = None
        gemini_request_id = f"req_{uuid.uuid4().hex[:12]}"
        start_gem_perf = time.perf_counter()

        from app.decision_models import get_current_run_context
        run_ctx = get_current_run_context()

        async with httpx.AsyncClient(timeout=15.0) as client:
            for idx, model_name in enumerate(models_to_try, start=1):
                is_fallback = (idx > 1)
                start_time_iso = datetime.now(timezone.utc).isoformat()

                if run_ctx:
                    run_ctx.record_external_attempt("gemini")
                    if is_fallback:
                        run_ctx.fallback_attempted = True

                # Emit Attempt Started Event
                if repo and hasattr(repo, "add_decision_log"):
                    try:
                        repo.add_decision_log({
                            "log_id": f"log_att_start_{uuid.uuid4().hex[:10]}",
                            "event_type": "gemini_http_attempt_started",
                            "telemetry_version": 2,
                            "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                            "request_id": run_ctx.request_id if run_ctx else None,
                            "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                            "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                            "gemini_request_id": gemini_request_id,
                            "timestamp": start_time_iso,
                            "caller": caller,
                            "model_requested": GEMINI_PRIMARY_MODEL,
                            "model_attempted": model_name,
                            "attempt_number": idx,
                            "is_fallback_attempt": is_fallback,
                            "gemini_called": True,
                            "fallback_used": is_fallback,
                            "daily_cache_key": daily_cache_key or (run_ctx.daily_cache_key if run_ctx else None),
                            "selection_summary": f"Gemini HTTP Attempt #{idx} Started ({model_name})",
                        })
                    except Exception as log_err:
                        logger.warning(f"Error logging gemini_http_attempt_started: {log_err}")

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                start_time = time.perf_counter()
                try:
                    resp = await client.post(url, json=payload)
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    end_time_iso = datetime.now(timezone.utc).isoformat()
                    last_http_status = resp.status_code

                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        usage_metadata = data.get("usageMetadata", {})

                        p_tokens = usage_metadata.get("promptTokenCount")
                        if p_tokens is None:
                            p_tokens = max(1, total_prompt_chars // 4) if total_prompt_chars else 0

                        if candidates:
                            finish_reason = candidates[0].get("finishReason", "UNKNOWN")
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text_out = parts[0].get("text", "").strip() if parts else ""
                            partial_text = bool(text_out)
                            r_chars = len(text_out)
                            r_tokens = usage_metadata.get("candidatesTokenCount") or usage_metadata.get("outputTokenCount")
                            if r_tokens is None:
                                r_tokens = max(1, r_chars // 4) if r_chars else 0
                            t_tokens = usage_metadata.get("totalTokenCount") or (p_tokens + r_tokens)
                            cached_tokens = usage_metadata.get("cachedContentTokenCount")
                            est_cost = calculate_estimated_cost(model_name, p_tokens, r_tokens)

                            if text_out and finish_reason != "MAX_TOKENS":
                                logger.info(
                                    f"[AI CALL TELEMETRY] Caller: '{caller}' | Model Requested: '{GEMINI_PRIMARY_MODEL}' | Model Used: '{model_name}' | "
                                    f"Provider: gemini | Status: 200 ({finish_reason}) | Duration: {duration_ms}ms | "
                                    f"Tokens: {p_tokens} prompt + {r_tokens} response = {t_tokens} total | Est. Cost: ${est_cost:.8f}"
                                )

                                # Emit Attempt Completed Success Event
                                if repo and hasattr(repo, "add_decision_log"):
                                    try:
                                        repo.add_decision_log({
                                            "log_id": f"log_att_comp_{uuid.uuid4().hex[:10]}",
                                            "event_type": "gemini_http_attempt_completed",
                                            "telemetry_version": 2,
                                            "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                                            "request_id": run_ctx.request_id if run_ctx else None,
                                            "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                                            "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                                            "gemini_request_id": gemini_request_id,
                                            "timestamp": end_time_iso,
                                            "started_at": start_time_iso,
                                            "completed_at": end_time_iso,
                                            "duration_ms": duration_ms,
                                            "caller": caller,
                                            "model_requested": GEMINI_PRIMARY_MODEL,
                                            "model_used": model_name,
                                            "model_attempted": model_name,
                                            "attempt_number": idx,
                                            "is_fallback_attempt": is_fallback,
                                            "http_status": 200,
                                            "success": True,
                                            "finish_reason": finish_reason,
                                            "candidate_count": len(candidates),
                                            "response_text_length": r_chars,
                                            "partial_text_present": partial_text,
                                            "prompt_token_count": p_tokens,
                                            "candidate_token_count": r_tokens,
                                            "total_token_count": t_tokens,
                                            "cached_content_token_count": cached_tokens,
                                            "error_type": None,
                                            "error_category": None,
                                            "gemini_called": True,
                                            "fallback_used": is_fallback,
                                            "fallback_reason": last_fallback_reason if is_fallback else None,
                                            "daily_cache_key": daily_cache_key or (run_ctx.daily_cache_key if run_ctx else None),
                                            "request_duration_ms": duration_ms,
                                            "selection_summary": f"Gemini HTTP Attempt #{idx} Succeeded (200 OK, {duration_ms}ms, model: '{model_name}')",
                                            "raw_model_response": text_out,
                                            "final_response": text_out,
                                        })
                                    except Exception as log_err:
                                        logger.warning(f"Error logging attempt completed: {log_err}")

                                # Emit Logical Gemini Completion Event
                                total_gem_dur = round((time.perf_counter() - start_gem_perf) * 1000, 2)
                                if run_ctx:
                                    run_ctx.gemini_request_id = gemini_request_id
                                    run_ctx.gemini_attempt_count = idx
                                    run_ctx.final_model = model_name
                                    run_ctx.add_timeline_event(
                                        stage="gemini_generation",
                                        status="completed",
                                        duration_ms=total_gem_dur,
                                        result={"model": model_name, "attempts": idx},
                                    )

                                if repo and hasattr(repo, "add_decision_log"):
                                    try:
                                        repo.add_decision_log({
                                            "log_id": f"log_gem_comp_{uuid.uuid4().hex[:10]}",
                                            "event_type": "gemini_request_completed",
                                            "telemetry_version": 2,
                                            "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                                            "request_id": run_ctx.request_id if run_ctx else None,
                                            "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                                            "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                                            "gemini_request_id": gemini_request_id,
                                            "timestamp": end_time_iso,
                                            "attempts_made": idx,
                                            "fallback_attempted": is_fallback,
                                            "fallback_trigger": last_fallback_reason if is_fallback else None,
                                            "primary_model": GEMINI_PRIMARY_MODEL,
                                            "final_model": model_name,
                                            "final_success": True,
                                            "final_error_type": None,
                                            "total_duration_ms": total_gem_dur,
                                            "gemini_called": True,
                                            "selection_summary": f"Gemini logical request {gemini_request_id} completed successfully using '{model_name}' after {idx} attempt(s)",
                                        })
                                    except Exception as log_err:
                                        logger.warning(f"Error logging gemini_request_completed: {log_err}")

                                return AgentResult(
                                    text=text_out,
                                    provider="gemini",
                                    model_requested=GEMINI_PRIMARY_MODEL,
                                    model_used=model_name,
                                    gemini_called=True,
                                    fallback_used=is_fallback,
                                    fallback_reason=None,
                                    http_status=200,
                                    request_duration_ms=duration_ms,
                                    actions_taken=[],
                                    caller=caller,
                                    prompt_char_count=total_prompt_chars,
                                    prompt_token_count=p_tokens,
                                    response_char_count=r_chars,
                                    response_token_count=r_tokens,
                                    total_token_count=t_tokens,
                                    estimated_cost_usd=est_cost,
                                    finish_reason=finish_reason,
                                    usage_metadata=usage_metadata,
                                    prompt_breakdown=prompt_breakdown,
                                )
                            else:
                                if finish_reason == "MAX_TOKENS":
                                    logger.warning(
                                        f"[AI LLM Call] Model '{model_name}' hit MAX_TOKENS limit "
                                        f"(max_output_tokens={max_output_tokens}). Response may be TRUNCATED — marking as fallback."
                                    )
                                    error_type = "MAX_TOKENS_TRUNCATED"
                                    last_fallback_reason = "primary_max_tokens_truncated" if idx == 1 else "fallback_max_tokens_truncated"
                                else:
                                    error_type = "EMPTY_TEXT" if candidates else "NO_CANDIDATES"
                                    last_fallback_reason = f"primary_{error_type.lower()}" if idx == 1 else f"fallback_{error_type.lower()}"

                                if run_ctx and idx == 1:
                                    run_ctx.fallback_attempted = True
                                    run_ctx.fallback_trigger = last_fallback_reason

                                if repo and hasattr(repo, "add_decision_log"):
                                    try:
                                        repo.add_decision_log({
                                            "log_id": f"log_att_fail_{uuid.uuid4().hex[:10]}",
                                            "event_type": "gemini_http_attempt_failed",
                                            "telemetry_version": 2,
                                            "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                                            "request_id": run_ctx.request_id if run_ctx else None,
                                            "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                                            "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                                            "gemini_request_id": gemini_request_id,
                                            "timestamp": end_time_iso,
                                            "started_at": start_time_iso,
                                            "completed_at": end_time_iso,
                                            "duration_ms": duration_ms,
                                            "caller": caller,
                                            "model_requested": GEMINI_PRIMARY_MODEL,
                                            "model_attempted": model_name,
                                            "attempt_number": idx,
                                            "is_fallback_attempt": is_fallback,
                                            "http_status": 200,
                                            "success": False,
                                            "finish_reason": finish_reason,
                                            "candidate_count": len(candidates),
                                            "response_text_length": r_chars,
                                            "partial_text_present": partial_text,
                                            "prompt_token_count": p_tokens,
                                            "candidate_token_count": r_tokens,
                                            "total_token_count": t_tokens,
                                            "cached_content_token_count": cached_tokens,
                                            "error_type": error_type,
                                            "error_category": "unusable_response",
                                            "fallback_reason": last_fallback_reason,
                                            "gemini_called": True,
                                            "fallback_used": True,
                                            "daily_cache_key": daily_cache_key or (run_ctx.daily_cache_key if run_ctx else None),
                                            "request_duration_ms": duration_ms,
                                            "selection_summary": f"Gemini HTTP Attempt #{idx} Failed ({error_type}, {duration_ms}ms, model: '{model_name}')",
                                        })
                                    except Exception as log_err:
                                        logger.warning(f"Error logging attempt failure: {log_err}")
                                continue
                        else:
                            error_type = "NO_CANDIDATES"
                            last_fallback_reason = "primary_no_candidates" if idx == 1 else "fallback_no_candidates"
                            if run_ctx and idx == 1:
                                run_ctx.fallback_attempted = True
                                run_ctx.fallback_trigger = last_fallback_reason
                    elif resp.status_code == 503:
                        error_type = "HTTP_503"
                        error_category = "service_unavailable"
                        last_fallback_reason = "primary_http_503" if idx == 1 else "fallback_http_503"
                        if run_ctx and idx == 1:
                            run_ctx.fallback_attempted = True
                            run_ctx.fallback_trigger = last_fallback_reason
                    else:
                        error_type = f"HTTP_{resp.status_code}"
                        error_category = "rate_limited" if resp.status_code == 429 else ("auth_failed" if resp.status_code in {401, 403} else "http_error")
                        last_fallback_reason = "rate_limited" if resp.status_code == 429 else (f"primary_http_{resp.status_code}" if idx == 1 else f"fallback_http_{resp.status_code}")
                        if run_ctx and idx == 1:
                            run_ctx.fallback_attempted = True
                            run_ctx.fallback_trigger = last_fallback_reason

                    # Emit Attempt Failed Event for non-200 or empty response
                    if repo and hasattr(repo, "add_decision_log"):
                        try:
                            repo.add_decision_log({
                                "log_id": f"log_att_fail_{uuid.uuid4().hex[:10]}",
                                "event_type": "gemini_http_attempt_failed",
                                "telemetry_version": 2,
                                "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                                "request_id": run_ctx.request_id if run_ctx else None,
                                "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                                "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                                "gemini_request_id": gemini_request_id,
                                "timestamp": end_time_iso,
                                "started_at": start_time_iso,
                                "completed_at": end_time_iso,
                                "duration_ms": duration_ms,
                                "caller": caller,
                                "model_requested": GEMINI_PRIMARY_MODEL,
                                "model_attempted": model_name,
                                "attempt_number": idx,
                                "is_fallback_attempt": is_fallback,
                                "http_status": resp.status_code,
                                "success": False,
                                "error_type": error_type,
                                "error_category": error_category,
                                "fallback_reason": last_fallback_reason,
                                "gemini_called": True,
                                "fallback_used": True,
                                "daily_cache_key": daily_cache_key or (run_ctx.daily_cache_key if run_ctx else None),
                                "request_duration_ms": duration_ms,
                                "selection_summary": f"Gemini HTTP Attempt #{idx} Failed (HTTP {resp.status_code}, {duration_ms}ms, model: '{model_name}')",
                            })
                        except Exception as log_err:
                            logger.warning(f"Error logging attempt failure: {log_err}")

                except httpx.TimeoutException as e:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    end_time_iso = datetime.now(timezone.utc).isoformat()
                    error_type = e.__class__.__name__
                    last_fallback_reason = "timeout"
                    if run_ctx and idx == 1:
                        run_ctx.fallback_attempted = True
                        run_ctx.fallback_trigger = last_fallback_reason

                    if repo and hasattr(repo, "add_decision_log"):
                        try:
                            repo.add_decision_log({
                                "log_id": f"log_att_fail_{uuid.uuid4().hex[:10]}",
                                "event_type": "gemini_http_attempt_failed",
                                "telemetry_version": 2,
                                "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                                "request_id": run_ctx.request_id if run_ctx else None,
                                "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                                "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                                "gemini_request_id": gemini_request_id,
                                "timestamp": end_time_iso,
                                "started_at": start_time_iso,
                                "completed_at": end_time_iso,
                                "duration_ms": duration_ms,
                                "caller": caller,
                                "model_requested": GEMINI_PRIMARY_MODEL,
                                "model_attempted": model_name,
                                "attempt_number": idx,
                                "is_fallback_attempt": is_fallback,
                                "http_status": None,
                                "success": False,
                                "error_type": error_type,
                                "error_category": "timeout",
                                "fallback_reason": last_fallback_reason,
                                "gemini_called": True,
                                "fallback_used": True,
                                "daily_cache_key": daily_cache_key or (run_ctx.daily_cache_key if run_ctx else None),
                                "request_duration_ms": duration_ms,
                                "selection_summary": f"Gemini HTTP Attempt #{idx} Timeout ({error_type}, {duration_ms}ms)",
                            })
                        except Exception as log_err:
                            logger.warning(f"Error logging timeout failure: {log_err}")

                except httpx.NetworkError as e:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    end_time_iso = datetime.now(timezone.utc).isoformat()
                    error_type = e.__class__.__name__
                    last_fallback_reason = "primary_network_error" if idx == 1 else "fallback_network_error"
                    if run_ctx and idx == 1:
                        run_ctx.fallback_attempted = True
                        run_ctx.fallback_trigger = last_fallback_reason

                    if repo and hasattr(repo, "add_decision_log"):
                        try:
                            repo.add_decision_log({
                                "log_id": f"log_att_fail_{uuid.uuid4().hex[:10]}",
                                "event_type": "gemini_http_attempt_failed",
                                "telemetry_version": 2,
                                "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                                "request_id": run_ctx.request_id if run_ctx else None,
                                "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                                "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                                "gemini_request_id": gemini_request_id,
                                "timestamp": end_time_iso,
                                "started_at": start_time_iso,
                                "completed_at": end_time_iso,
                                "duration_ms": duration_ms,
                                "caller": caller,
                                "model_requested": GEMINI_PRIMARY_MODEL,
                                "model_attempted": model_name,
                                "attempt_number": idx,
                                "is_fallback_attempt": is_fallback,
                                "http_status": None,
                                "success": False,
                                "error_type": error_type,
                                "error_category": "network_error",
                                "fallback_reason": last_fallback_reason,
                                "gemini_called": True,
                                "fallback_used": True,
                                "daily_cache_key": daily_cache_key or (run_ctx.daily_cache_key if run_ctx else None),
                                "request_duration_ms": duration_ms,
                                "selection_summary": f"Gemini HTTP Attempt #{idx} Network Error ({error_type}, {duration_ms}ms)",
                            })
                        except Exception as log_err:
                            logger.warning(f"Error logging network failure: {log_err}")

                except Exception as e:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    end_time_iso = datetime.now(timezone.utc).isoformat()
                    error_type = e.__class__.__name__
                    last_fallback_reason = "primary_unknown_error" if idx == 1 else "fallback_unknown_error"
                    if run_ctx and idx == 1:
                        run_ctx.fallback_attempted = True
                        run_ctx.fallback_trigger = last_fallback_reason

                    if repo and hasattr(repo, "add_decision_log"):
                        try:
                            repo.add_decision_log({
                                "log_id": f"log_att_fail_{uuid.uuid4().hex[:10]}",
                                "event_type": "gemini_http_attempt_failed",
                                "telemetry_version": 2,
                                "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                                "request_id": run_ctx.request_id if run_ctx else None,
                                "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                                "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                                "gemini_request_id": gemini_request_id,
                                "timestamp": end_time_iso,
                                "started_at": start_time_iso,
                                "completed_at": end_time_iso,
                                "duration_ms": duration_ms,
                                "caller": caller,
                                "model_requested": GEMINI_PRIMARY_MODEL,
                                "model_attempted": model_name,
                                "attempt_number": idx,
                                "is_fallback_attempt": is_fallback,
                                "http_status": None,
                                "success": False,
                                "error_type": error_type,
                                "error_category": "unknown_error",
                                "fallback_reason": last_fallback_reason,
                                "gemini_called": True,
                                "fallback_used": True,
                                "daily_cache_key": daily_cache_key or (run_ctx.daily_cache_key if run_ctx else None),
                                "request_duration_ms": duration_ms,
                                "selection_summary": f"Gemini HTTP Attempt #{idx} Error ({error_type}, {duration_ms}ms)",
                            })
                        except Exception as log_err:
                            logger.warning(f"Error logging attempt error: {log_err}")

        # Emit Logical Gemini Failure Event if all models failed
        total_gem_dur = round((time.perf_counter() - start_gem_perf) * 1000, 2)
        if run_ctx:
            run_ctx.gemini_request_id = gemini_request_id
            run_ctx.gemini_attempt_count = len(models_to_try)
            run_ctx.fallback_attempted = True
            if not run_ctx.fallback_trigger:
                run_ctx.fallback_trigger = last_fallback_reason
            run_ctx.final_failure_reason = last_fallback_reason
            run_ctx.add_timeline_event(
                stage="gemini_generation",
                status="failed",
                duration_ms=total_gem_dur,
                result={"reason": last_fallback_reason, "fallback_trigger": run_ctx.fallback_trigger},
            )

        if repo and hasattr(repo, "add_decision_log"):
            try:
                repo.add_decision_log({
                    "log_id": f"log_gem_fail_{uuid.uuid4().hex[:10]}",
                    "event_type": "gemini_request_failed",
                    "telemetry_version": 2,
                    "briefing_run_id": run_ctx.briefing_run_id if run_ctx else None,
                    "request_id": run_ctx.request_id if run_ctx else None,
                    "session_id": session_id or (run_ctx.session_id if run_ctx else None),
                    "user_id": user_id or (run_ctx.user_id if run_ctx else "unknown"),
                    "gemini_request_id": gemini_request_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "attempts_made": len(models_to_try),
                    "fallback_attempted": True,
                    "fallback_trigger": run_ctx.fallback_trigger if run_ctx else last_fallback_reason,
                    "final_failure_reason": last_fallback_reason,
                    "primary_model": GEMINI_PRIMARY_MODEL,
                    "final_model": None,
                    "final_success": False,
                    "final_error_type": last_fallback_reason,
                    "total_duration_ms": total_gem_dur,
                    "gemini_called": True,
                    "selection_summary": f"Gemini logical request {gemini_request_id} failed after {len(models_to_try)} attempt(s). Trigger: {run_ctx.fallback_trigger if run_ctx else last_fallback_reason}, Final failure: {last_fallback_reason}",
                })
            except Exception as log_err:
                logger.warning(f"Error logging gemini_request_failed: {log_err}")

        est_p_tokens = max(1, total_prompt_chars // 4) if total_prompt_chars else 0
        est_cost = calculate_estimated_cost(GEMINI_PRIMARY_MODEL, est_p_tokens, 0)
        logger.warning(
            f"[AI CALL TELEMETRY] All Gemini models failed. Caller: '{caller}' | Reason: {last_fallback_reason}",
            extra=sanitize_log_data({
                "provider": "fallback",
                "caller": caller,
                "model_requested": GEMINI_PRIMARY_MODEL,
                "fallback_reason": last_fallback_reason,
                "http_status": last_http_status,
                "prompt_char_count": total_prompt_chars,
                "prompt_token_count": est_p_tokens,
                "estimated_cost_usd": est_cost,
                "prompt_breakdown": prompt_breakdown,
            })
        )
        return AgentResult(
            text="",
            provider="fallback",
            model_requested=GEMINI_PRIMARY_MODEL,
            model_used=None,
            gemini_called=True,
            fallback_used=True,
            fallback_reason=last_fallback_reason,
            http_status=last_http_status,
            request_duration_ms=None,
            actions_taken=[],
            caller=caller,
            prompt_char_count=total_prompt_chars,
            prompt_token_count=est_p_tokens,
            response_char_count=0,
            response_token_count=0,
            total_token_count=est_p_tokens,
            estimated_cost_usd=est_cost,
            finish_reason="FALLBACK",
            usage_metadata={},
            prompt_breakdown=prompt_breakdown,
        )

    @staticmethod
    def _generate_fallback_chat_reply(
        system_prompt: str,
        user_message: str,
        actions: list[dict[str, Any]],
        title_query: str | None = None,
    ) -> str:
        """Generate brief, factual fallback response without fake jokes or artificial catchphrases."""
        if actions:
            t = actions[0].get("title", "the requested item")
            act = actions[0].get("action")
            if act == "rate_movie":
                return f"I've logged your rating for '{t}'. The conversational service was unavailable, but your rating was saved."
            elif act == "add_monitoring":
                return f"I added '{t}' to your queue. The conversational service was unavailable, but the queue update succeeded."
            elif act == "remove_item":
                return f"I removed '{t}' from your queue. The conversational service was unavailable, but the queue update succeeded."
            elif act == "delete_rating":
                return f"I deleted your rating for '{t}'. The conversational service was unavailable, but the update succeeded."
            elif act == "update_status":
                return f"I updated the status for '{t}'. The conversational service was unavailable, but the update succeeded."
            elif act == "movie_search":
                q = actions[0].get("query", "movies")
                return f"I searched TMDB for '{q}'. The conversational service was unavailable, but your search results are displayed below."
            return f"Action completed for '{t}'. The conversational service was unavailable."

        if title_query:
            return f"I checked for '{title_query}', but I couldn't reach the conversational service just now. Please check your queue or try again."

        msg_l = user_message.lower()
        if any(p in msg_l for p in ["rated", "ratings", "my rating"]):
            return "You haven't logged ratings for any movies yet. You can rate movies from 1 to 5 stars to track your favorites!"

        return "The conversational service is currently unavailable. Please try again in a moment."
