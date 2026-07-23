from dataclasses import asdict, dataclass
import json
import logging
import re
import time
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
) -> dict[str, Any]:
    """Construct a clean, typed Gemini API payload using native systemInstruction and structured contents."""
    payload: dict[str, Any] = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": []
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
    def _build_greeting_instruction(
        briefing_items: list[dict[str, Any]],
        time_of_day: str,
        location: str,
        weather_json: dict[str, Any] | None,
        recent_openings: list[str] | None = None,
    ) -> str:
        items_payload = json.dumps(briefing_items, indent=2)
        weather_str = ""
        if weather_json and weather_json.get("significant_alert"):
            weather_str = f"\nSignificant Weather Alert: {weather_json['significant_alert']}"

        recent_str = ""
        if recent_openings and len(recent_openings) > 0:
            recent_str = f"\nRecent Openings (Do NOT repeat these phrasing patterns):\n" + "\n".join([f"- {o}" for o in recent_openings[-3:]])

        instruction = (
            f"Create a brief, natural opening using only the supplied facts. Mention the most useful new or time-sensitive item first. "
            f"It is acceptable to give only a simple greeting when nothing meaningful has changed. Do not invent activity merely to fill space. "
            f"Do not repeat wording from recent greetings.\n\n"
            f"Time of day: {time_of_day}\n"
            f"Location: {location or 'Not specified'}{weather_str}{recent_str}\n\n"
            f"Briefing items:\n```json\n{items_payload}\n```"
        )
        return instruction

    @staticmethod
    def _generate_dynamic_human_briefing(
        settings: dict[str, Any],
        location: str,
        weather_json: dict[str, Any] | None,
        briefing_items: list[dict[str, Any]],
        time_of_day: str,
    ) -> str:
        if briefing_items:
            titles = [it.get("title", "Untitled") for it in briefing_items if it.get("title")]
            t_str = ", ".join(titles) if titles else "your watchlist"
            return f"Welcome back! Here are the latest updates for {t_str}."
        else:
            return f"Welcome back! No new updates on your monitored queue today."

    @staticmethod
    async def _format_structured_llm_briefing(
        settings: dict[str, Any],
        weather_data: Any,
        briefing_items: list[dict[str, Any]],
        total_monitored: int = 0,
        recent_openings: list[str] | None = None,
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

        instruction = AiAgentService._build_greeting_instruction(
            briefing_items=briefing_items,
            time_of_day=time_of_day,
            location=location,
            weather_json=weather_json,
            recent_openings=recent_openings,
        )

        system_prompt = get_system_prompt(settings, weather_report=None)

        result = await AiAgentService._call_gemini_api(
            system_instruction=system_prompt,
            recent_history=[],
            user_message=instruction,
            context_notes=None,
        )

        if result.text and not result.fallback_used:
            return result.text

        return AiAgentService._generate_dynamic_human_briefing(
            settings=settings,
            location=location,
            weather_json=weather_json,
            briefing_items=briefing_items,
            time_of_day=time_of_day,
        )

    @staticmethod
    async def process_chat(
        user_id: str, user_message: str, repo: WatchlistRepository, tmdb: TmdbClient | None
    ) -> dict[str, Any]:
        """Process chat message, recognize intents (auto-monitoring, rental price targets), update history, and generate response."""
        settings = repo.get_agent_settings(user_id)
        history = repo.list_chat_messages(user_id, limit=20)

        # Save user message
        repo.add_chat_message(user_id, "user", user_message)

        actions_taken = []
        context_notes: list[str] = []
        msg_lower = user_message.lower().strip()

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

        # 1. Intent Recognition: Movie Rating / Watched List Action
        rate_title, rating_val = AiAgentService._extract_rating_action(user_message)
        if rate_title:
            t_name = rate_title
            m_type = "movie"
            t_id = None
            p_path = None
            r_date = None

            # Search local user watchlist & rated movies first
            all_local = repo.list_items(user_id) + repo.list_rated_movies(user_id)
            match_local = next((i for i in all_local if rate_title.lower() in (i.get("title") or "").lower()), None)
            if match_local:
                t_name = match_local.get("title", rate_title)
                m_type = match_local.get("media_type", "movie")
                t_id = match_local.get("tmdb_id")
                p_path = match_local.get("poster_path")
                r_date = match_local.get("release_date")

            if not t_id and tmdb:
                try:
                    res = await tmdb.search(rate_title)
                    if res:
                        best = res[0]
                        t_name = best.get("title") or best.get("name") or rate_title
                        m_type = best.get("media_type", "movie")
                        t_id = best.get("id")
                        r_date = best.get("release_date")
                        p_path = best.get("poster_path")
                except Exception as e:
                    logger.warning(f"Error searching TMDB for rating title '{rate_title}': {e}")

            if t_id:
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
                    actions_taken.append({
                        "action": "rate_movie",
                        "title": t_name,
                        "rating": rating_val or 5,
                        "media_type": m_type,
                        "tmdb_id": t_id,
                    })
                    repo.add_query_memory(user_id, user_message, tmdb_id=t_id, media_type=m_type, title=t_name)
                except Exception as e:
                    logger.warning(f"Error saving rating for '{t_name}': {e}")

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
            else:
                items = repo.list_items(user_id)
                match_i = next((i for i in items if del_title.lower() in (i.get("title") or "").lower()), None)
                if match_i:
                    repo.remove_item(user_id, match_i.get("media_type", "movie"), match_i["tmdb_id"])
                    actions_taken.append({
                        "action": "remove_item",
                        "title": match_i["title"],
                    })

        # 3. Intent Recognition & Auto-Monitoring Execution
        ext_title, target_price = AiAgentService._extract_title_and_price(user_message)
        already_acted = any(
            (a.get("title") or "").lower() in (ext_title or "").lower() or (ext_title or "").lower() in (a.get("title") or "").lower()
            for a in actions_taken
        ) or (rate_title and ext_title and rate_title.lower() in ext_title.lower())
        if ext_title and tmdb and not already_acted:
            try:
                res = await tmdb.search(ext_title)
                if res:
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
            except Exception as e:
                logger.warning(f"Error auto-monitoring title '{ext_title}': {e}")

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
            context_notes.append(f"Automated action executed: {'; '.join(act_strings)}. Inform the user conversationally that this action was completed.")

        title_query = ext_title
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
                    if extracted and len(extracted) > 1 and extracted not in {"my shows", "my queue", "monitored shows", "updates", "watchlist", "list"}:
                        title_query = extracted
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

        location = settings.get("location", "").strip()
        weather_report = await WeatherService.get_weather_report(location) if location else None
        system_prompt = get_system_prompt(settings, weather_report)

        result = await AiAgentService._call_gemini_api(
            system_instruction=system_prompt,
            recent_history=history[-6:],
            user_message=user_message,
            context_notes=context_notes,
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

        return {
            "message": msg_record,
            "actions_taken": actions_taken,
            "telemetry": result.to_dict(),
        }

    @staticmethod
    def _extract_rating_action(text: str) -> tuple[str | None, int | None]:
        """Extract movie/tv title and rating (1-5 stars) from user prompt."""
        clean_text = text.strip()
        msg_lower = clean_text.lower()

        if any(k in msg_lower for k in ["remove", "delete", "unrate", "clear"]):
            return None, None

        has_rate_intent = any(k in msg_lower for k in [
            "watched", "rating", "rated", "rate", "stars", "star", "seen", "log"
        ])
        if not has_rate_intent:
            return None, None

        rating = None
        num_match = re.search(r'(?:(\d)\s*(?:-\s*)?stars?|(\d)\s*/\s*5|rated?\s+(\d)|rating\s+(?:of\s+)?(\d)|give\s+it\s+(\d)|log\s+(?:my\s+)?(\d))', msg_lower)
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
            if any(p in msg_lower for p in ["watched list", "rated movies", "log rating", "rate movie", "rated list", "list of rated"]):
                rating = 5

        if rating is not None:
            rating = max(1, min(5, rating))

        title_str = clean_text
        prefix_patterns = [
            r"^(?:add|put|log|insert|record)\s+(?:a|an|the|my)?\s*(?:\d\s*(?:-\s*)?stars?\s+)?(?:rating\s+for\s+)?",
            r"^(?:i\s+(?:have\s+)?(?:watched|seen))\s+",
            r"^(?:rate)\s+",
            r"^(?:give)\s+",
        ]
        for p in prefix_patterns:
            title_str = re.sub(p, "", title_str, flags=re.IGNORECASE).strip()

        title_str = re.split(r'\s+(?:and\s+rate|and\s+give|with\s+a|giving|rated|rating|to\s+my\s+watched|to\s+my\s+rated|as\s+\d)\b', title_str, flags=re.IGNORECASE)[0].strip()
        title_str = re.sub(r'^(?:for|about|a|an|the)\s+', '', title_str, flags=re.IGNORECASE).strip()
        title_str = re.sub(r'\s+(?:with|giving|and|rating|ratings|stars?|star|to|on|in|a|\d|\d/5)$', '', title_str, flags=re.IGNORECASE).strip()

        ignored_titles = {"movie", "show", "title", "watched list", "rated movies", "my rated movies", "it", "them", "this", "that", "something", "3-star", "4-star", "5-star"}
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
    def _extract_delete_action(text: str) -> tuple[str | None, str | None]:
        """Extract movie title and target deletion type ('rating' or 'watchlist') from user prompt."""
        clean_text = text.strip()
        msg_lower = clean_text.lower()

        if not any(k in msg_lower for k in ["remove", "delete", "unrate", "clear"]):
            return None, None

        target_type = "rating" if any(k in msg_lower for k in ["rating", "rated", "unrate", "watched", "seen"]) else "watchlist"

        title_str = clean_text
        prefix_patterns = [
            r"^(?:remove|delete|clear)\s+(?:rating\s+for\s+)?",
            r"^(?:delete\s+rating\s+for|unrate|remove\s+rating\s+for)\s+",
        ]
        for p in prefix_patterns:
            title_str = re.sub(p, "", title_str, flags=re.IGNORECASE).strip()

        title_str = re.split(r'\s+(?:from\s+my|from\s+the|from)\b', title_str, flags=re.IGNORECASE)[0].strip()
        title_str = re.sub(r'\s+(?:rating|ratings|list|queue)$', '', title_str, flags=re.IGNORECASE).strip()
        title_str = re.sub(r'^(?:a|an|the|for)\s+', '', title_str, flags=re.IGNORECASE).strip()

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
            r"(?:add|track|monitor|follow)\s+['\"]?([^'.\"$\n]+?)['\"]?\s+(?:to\s+my\s+(?:monitor\s+|watch\s*)?(?:list|queue|monitoring)|to\s+monitoring)",
            r"(?:waiting|wait|looking)\s+for\s+(?:the\s+movie\s+|the\s+show\s+)?['\"]?([^'.\"$\n]+?)['\"]?\s*(?:to\s+(?:come|air|drop|rent|release)|under|\$|$)",
            r"(?:notify|alert|tell)\s+me\s+when\s+(?:the\s+movie\s+|the\s+show\s+)?['\"]?([^'.\"$\n]+?)['\"]?\s*(?:drops|is|available|to\s+rent|under|\$|$)",
            r"(?:add|track|monitor)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
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
    async def _call_gemini_api(
        system_instruction: str,
        recent_history: list[dict[str, str]] | str = [],
        user_message: str = "",
        context_notes: list[str] | None = None,
    ) -> AgentResult:
        """Call Gemini API via httpx using configurable model selection and native request structure."""
        if isinstance(recent_history, str):
            user_message = recent_history
            recent_history = []

        if not GEMINI_API_KEY:
            logger.info("GEMINI_API_KEY missing; using fallback generator", extra=sanitize_log_data({
                "provider": "fallback",
                "fallback_reason": "api_key_missing",
            }))
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
            )

        models_to_try = [GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL]
        payload = build_gemini_request(system_instruction, recent_history, user_message, context_notes)

        last_fallback_reason = "unknown_error"
        last_http_status = None

        async with httpx.AsyncClient(timeout=15.0) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                start_time = time.perf_counter()
                try:
                    resp = await client.post(url, json=payload)
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    last_http_status = resp.status_code

                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                text_out = parts[0].get("text", "").strip()
                                if text_out:
                                    logger.info(
                                        f"Gemini API call succeeded with model '{model_name}'",
                                        extra=sanitize_log_data({
                                            "provider": "gemini",
                                            "model_requested": GEMINI_PRIMARY_MODEL,
                                            "model_used": model_name,
                                            "http_status": 200,
                                            "duration_ms": duration_ms,
                                        })
                                    )
                                    return AgentResult(
                                        text=text_out,
                                        provider="gemini",
                                        model_requested=GEMINI_PRIMARY_MODEL,
                                        model_used=model_name,
                                        gemini_called=True,
                                        fallback_used=False,
                                        fallback_reason=None,
                                        http_status=200,
                                        request_duration_ms=duration_ms,
                                        actions_taken=[],
                                    )
                                else:
                                    last_fallback_reason = "empty_response"
                            else:
                                last_fallback_reason = "empty_response"
                        else:
                            last_fallback_reason = "blocked_response"
                    elif resp.status_code == 429:
                        last_fallback_reason = "rate_limited"
                        logger.warning(f"Gemini model '{model_name}' rate limited (429)")
                    elif resp.status_code in {401, 403}:
                        last_fallback_reason = "authentication_failed"
                        logger.warning(f"Gemini model '{model_name}' auth failed ({resp.status_code})")
                    elif resp.status_code == 404:
                        last_fallback_reason = "model_not_found"
                        logger.warning(f"Gemini model '{model_name}' not found (404)")
                    elif resp.status_code in {400, 422}:
                        last_fallback_reason = "invalid_response"
                        logger.warning(f"Gemini model '{model_name}' invalid request ({resp.status_code})")
                    else:
                        last_fallback_reason = "network_error"
                        logger.warning(f"Gemini model '{model_name}' HTTP error ({resp.status_code})")
                except httpx.TimeoutException:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    last_fallback_reason = "timeout"
                    logger.warning(f"Gemini model '{model_name}' timed out after 15s")
                except httpx.NetworkError:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    last_fallback_reason = "network_error"
                    logger.warning(f"Gemini model '{model_name}' network error")
                except Exception as e:
                    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    last_fallback_reason = "unknown_error"
                    logger.warning(f"Gemini model '{model_name}' unexpected error: {e}")

        logger.warning(
            f"All Gemini models failed. Triggering fallback response. Reason: {last_fallback_reason}",
            extra=sanitize_log_data({
                "provider": "fallback",
                "model_requested": GEMINI_PRIMARY_MODEL,
                "fallback_reason": last_fallback_reason,
                "http_status": last_http_status,
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
            return f"Action completed for '{t}'. The conversational service was unavailable."

        if title_query:
            return f"I checked for '{title_query}', but I couldn't reach the conversational service just now. Please check your queue or try again."

        return "The conversational service is currently unavailable. Please try again in a moment."
