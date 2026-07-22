import json
import logging
import re
from typing import Any

import httpx

from app.config import GEMINI_API_KEY
from app.repository import WatchlistRepository, DuplicateItemError
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



class AiAgentService:
    @staticmethod
    async def evaluate_monitored_updates(
        user_id: str, repo: WatchlistRepository, tmdb: TmdbClient | None
    ) -> dict[str, Any]:
        """Evaluate user's queue/following titles and generate a personalized login briefing."""
        from app.services.briefing_service import BriefingService
        return await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb)
        settings = repo.get_agent_settings(user_id)
        if not settings.get("notify_on_login", True):
            return {"enabled": False, "briefing": None, "updates": []}

        items = repo.list_items(user_id)
        monitored = [
            item for item in items
            if not item.get("is_owned") and (item.get("status") in {"following", "queue", "watchlist"} or not item.get("status"))
        ]

        updates = []
        for item in monitored:
            media_type = item.get("media_type", "movie")
            tmdb_id = item.get("tmdb_id")
            title = item.get("title", "Untitled")

            air_date = item.get("release_date")
            days_away = None
            next_season_num = None

            # 1. Air dates & season updates
            if media_type == "tv" and tmdb and tmdb_id:
                try:
                    details = await tmdb.get_details("tv", tmdb_id)
                    seasons = details.get("seasons", [])
                    next_season = tmdb.get_next_season(seasons) if seasons else None
                    if next_season:
                        air_date = next_season.get("air_date") or air_date
                        days_away = next_season.get("days_away")
                        next_season_num = next_season.get("season_number")
                except Exception as e:
                    logger.warning(f"Error checking TV details for {title}: {e}")

            if days_away is None and air_date:
                from app.models import days_until
                days_away = days_until(air_date)

            # Categorize date updates
            if days_away is not None:
                if 0 <= days_away <= 2:
                    day_desc = "TODAY" if days_away == 0 else ("in 1 day" if days_away == 1 else f"in {days_away} days")
                    season_str = f" Season {next_season_num}" if next_season_num else ""
                    updates.append({
                        "title": title,
                        "type": "imminent_release",
                        "urgency": 1,
                        "days_away": days_away,
                        "message": f"🔥 URGENT (Next 2 Days): '{title}'{season_str} releases {day_desc} ({air_date})!",
                        "item": item,
                    })
                elif -14 <= days_away < 0:
                    ago_days = abs(days_away)
                    ago_str = f"{ago_days} day{'s' if ago_days != 1 else ''} ago"
                    updates.append({
                        "title": title,
                        "type": "recently_available",
                        "urgency": 2,
                        "days_away": days_away,
                        "message": f"🎉 JUST RELEASED: '{title}' became available recently ({ago_str} on {air_date})!",
                        "item": item,
                    })
                elif 3 <= days_away <= 14:
                    season_str = f" Season {next_season_num}" if next_season_num else ""
                    updates.append({
                        "title": title,
                        "type": "upcoming_2_weeks",
                        "urgency": 3,
                        "days_away": days_away,
                        "message": f"📅 UPCOMING (Next 2 Weeks): '{title}'{season_str} releases in {days_away} days ({air_date}).",
                        "item": item,
                    })
                elif 15 <= days_away <= 30:
                    season_str = f" Season {next_season_num}" if next_season_num else ""
                    updates.append({
                        "title": title,
                        "type": "upcoming_month",
                        "urgency": 4,
                        "days_away": days_away,
                        "message": f"📆 UPCOMING: '{title}'{season_str} releases in {days_away} days ({air_date}).",
                        "item": item,
                    })

            # 2. Target Rental Price Check & Free Streaming
            target_price = item.get("target_rental_price")
            if tmdb and tmdb_id:
                try:
                    providers = await tmdb.get_watch_providers(media_type, tmdb_id)
                    rent_list = providers.get("categories", {}).get("rent", [])
                    buy_list = providers.get("categories", {}).get("buy", [])

                    prices = []
                    for r in rent_list + buy_list:
                        curr = r.get("current_price") or r.get("price")
                        if curr:
                            try:
                                p_val = float(str(curr).replace("$", ""))
                                prices.append(p_val)
                            except ValueError:
                                pass

                    if target_price is not None and prices and min(prices) <= target_price:
                        min_price = min(prices)
                        updates.append({
                            "title": title,
                            "type": "price_drop",
                            "urgency": 2,
                            "days_away": None,
                            "message": f" Great news! '{title}' is now available to rent for ${min_price:.2f} (your target was ${target_price:.2f})!",
                            "item": item,
                        })
                    elif providers.get("is_free_streaming") and (item.get("watch_free_streaming") or target_price is not None):
                        updates.append({
                            "title": title,
                            "type": "free_streaming",
                            "urgency": 2,
                            "days_away": None,
                            "message": f" '{title}' is now streaming for free on included platforms!",
                            "item": item,
                        })
                except Exception as e:
                    logger.warning(f"Error checking watch providers for {title}: {e}")

        # 3. Persistent Query Memory Evaluation (Titles asked about in past 4+ weeks)
        try:
            memories = repo.list_query_memories(user_id, limit=30)
            monitored_titles_set = {m.get("title", "").lower() for m in monitored}
            for mem in memories:
                m_title = mem.get("title") or mem.get("query_text")
                if not m_title or m_title.lower() in monitored_titles_set:
                    continue
                m_tmdb_id = mem.get("tmdb_id")
                m_media = mem.get("media_type") or "movie"
                m_rel_date = None
                if tmdb and m_tmdb_id:
                    try:
                        det = await tmdb.get_details(m_media, m_tmdb_id)
                        m_rel_date = det.get("release_date")
                    except Exception:
                        pass
                elif tmdb and m_title:
                    try:
                        search_res = await tmdb.search(m_title)
                        if search_res:
                            m_rel_date = search_res[0].get("release_date")
                    except Exception:
                        pass

                if m_rel_date:
                    from app.models import days_until
                    m_days = days_until(m_rel_date)
                    asked_at_str = mem.get("asked_at", "")[:10]
                    if m_days is not None:
                        if -14 <= m_days <= 2:
                            updates.append({
                                "title": m_title,
                                "type": "memory_recall",
                                "urgency": 2,
                                "days_away": m_days,
                                "message": f"💡 MEMORY RECALL: You asked about '{m_title}' on {asked_at_str}. It is currently available/releasing ({m_rel_date})!",
                                "item": {"title": m_title, "release_date": m_rel_date},
                            })
                        elif 3 <= m_days <= 14:
                            updates.append({
                                "title": m_title,
                                "type": "memory_recall",
                                "urgency": 3,
                                "days_away": m_days,
                                "message": f"💡 MEMORY RECALL: You asked about '{m_title}' on {asked_at_str}. It releases in {m_days} days ({m_rel_date})!",
                                "item": {"title": m_title, "release_date": m_rel_date},
                            })
        except Exception as e:
            logger.warning(f"Error evaluating query memories: {e}")

        # Sort updates by urgency and date proximity
        updates.sort(key=lambda u: (u.get("urgency", 5), abs(u.get("days_away") or 999)))

        # Fetch weather report if user location is configured
        location = settings.get("location", "").strip()
        weather_report = await WeatherService.get_weather_report(location) if location else None

        # Format briefing response
        system_prompt = get_system_prompt(settings, weather_report)
        briefing_text = await AiAgentService._format_briefing_text(system_prompt, updates, monitored, weather_report)

        return {
            "enabled": True,
            "briefing": briefing_text,
            "updates_count": len(updates),
            "updates": updates,
            "personality_preset": settings.get("personality_preset", "cinephile"),
            "location": location,
            "weather_report": weather_report,
        }

    @staticmethod
    async def _format_novelty_briefing(
        updates: list[dict[str, Any]],
        weather_report: str | None = None,
        total_monitored: int = 0,
    ) -> str:
        if not updates:
            return "Good morning! No new release updates or news since your last visit. Everything in your queue is up to date."

        formatted_items = []
        for u in updates:
            formatted_items.append(f"• {u['message']}")
        bullet_list = "\n".join(formatted_items)

        prompt = (
            f"Here are the top novelty updates for the user's monitored titles:\n"
            f"{bullet_list}\n\n"
            f"Write a short, natural, friendly 2-3 sentence startup briefing. "
            f"Start directly with a warm greeting (e.g. 'Good morning' or 'Welcome back'). "
            f"Do NOT list every item like a database log; summarize the key points concisely."
        )

        system_prompt = RECOMMENDED_SYSTEM_PROMPT
        if weather_report:
            system_prompt += f"\n\nLocal Weather Note: {weather_report}"

        if GEMINI_API_KEY:
            try:
                llm_response = await AiAgentService._call_gemini_api(system_prompt, prompt)
                if llm_response:
                    logger.info("Generated briefing via Gemini", extra={
                        "response_source": "gemini",
                        "model_requested": "gemini-flash-latest",
                        "model_used": "gemini-flash-latest",
                        "intent": "startup_briefing",
                        "fallback_used": False,
                        "selected_count": len(updates),
                    })
                    return llm_response
            except Exception as e:
                logger.error(f"Gemini API error during briefing generation: {e}")

        # Neutral, helpful fallback response
        logger.info("Generated briefing via fallback", extra={
            "response_source": "fallback",
            "fallback_used": True,
            "fallback_reason": "api_error_or_missing_key",
            "intent": "startup_briefing",
            "selected_count": len(updates),
        })

        count = len(updates)
        return (
            f"Welcome back! You have {count} update{'s' if count != 1 else ''} in your CineQueue data:\n"
            f"{bullet_list}"
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
        ext_title, target_price = AiAgentService._extract_title_and_price(user_message)

        # 1. Intent Recognition & Auto-Monitoring Execution
        if ext_title and tmdb:
            try:
                res = await tmdb.search(ext_title)
                if res:
                    best = res[0]
                    t_name = best.get("title")
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

        msg_lower = user_message.lower().strip()
        title_query = ext_title
        if not title_query:
            title_patterns = [
                r"(?:any\s+)?(?:update|updates|news|info|word)\s+(?:on|about|for)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
                r"(?:why\s+didn't\s+the\s+agent\s+say\s+something\s+about|why\s+didn't\s+you\s+mention|what\s+about|tell\s+me\s+about|is\s+there\s+any\s+update\s+on|how\s+about|info\s+on|status\s+of)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
                r"(?:is|when\s+is)\s+['\"]?([^'.\"$\n]+?)['\"]?\s+(?:releasing|coming\s+out|available|dropping)",
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

        title_context_note = ""
        recommendation_note = ""

        if title_query:
            # Store query into persistent memory
            repo.add_query_memory(user_id, user_message, title=title_query)

            exact_matches = [i for i in items if title_query.lower() in i.get("title", "").lower()]
            partial_matches = [
                i for i in items
                if any(w in i.get("title", "").lower() for w in title_query.split() if len(w) > 3 and w.lower() not in {"title", "movie", "show", "season"})
            ]
            matching_user_items = exact_matches or partial_matches
            rec_item_id = None
            rec_media_type = None

            if matching_user_items:
                item = matching_user_items[0]
                t_title = item.get("title")
                status_str = "monitored" if item.get("status") in {"following", "queue"} else item.get("status")
                rel_date = item.get("release_date")
                rec_item_id = item.get("tmdb_id")
                rec_media_type = item.get("media_type", "movie")
                from app.models import days_until
                days = days_until(rel_date) if rel_date else None
                days_desc = f" (Releasing in {days} days on {rel_date})" if days and days > 0 else (f" (Released {abs(days)} days ago on {rel_date})" if days and days < 0 else (f" (Releasing TODAY {rel_date})" if days == 0 else f" (Release date: {rel_date})"))
                title_context_note = f"\n[System Note: User specifically asked about '{t_title}'. Item IS in user's queue. Status: {status_str}{days_desc}. Answer specifically about '{t_title}' in your annoyed-yet-thorough computer persona.]"
            elif tmdb:
                try:
                    res = await tmdb.search(title_query)
                    if res:
                        best = res[0]
                        t_title = best.get("title")
                        rel_date = best.get("release_date")
                        media_type = best.get("media_type")
                        rec_item_id = best.get("id")
                        rec_media_type = media_type
                        rel_str = f" ({rel_date})" if rel_date else ""
                        title_context_note = f"\n[System Note: User asked about '{t_title}'. Found on TMDB: '{t_title}' ({media_type}{rel_str}). It is NOT currently in user's queue. Answer conversationally in your annoyed computer persona.]"
                    else:
                        title_context_note = f"\n[System Note: User asked about '{title_query}'. No matching show/movie found in user's queue or TMDB.]"
                except Exception as e:
                    logger.warning(f"Error resolving title search for LLM context: {e}")

            if tmdb and rec_item_id and rec_media_type:
                try:
                    recs = await tmdb.get_recommendations(rec_media_type, rec_item_id)
                    if recs:
                        r_title = recs[0].get("title")
                        r_year = (recs[0].get("release_date") or "")[:4]
                        r_year_str = f" ({r_year})" if r_year else ""
                        recommendation_note = f"\n[System Note: Taste Recommendation: Based on user's interest in this title, you may suggest '{r_title}'{r_year_str} as a similar recommendation.]"
                except Exception as e:
                    logger.warning(f"Error fetching recommendations for context: {e}")

        holiday_ctx = ""
        holiday_remark = get_approaching_holiday_or_season()
        if holiday_remark:
            holiday_ctx = f"\n[System Note: Context remark: {holiday_remark}]"

        location = settings.get("location", "").strip()
        weather_report = await WeatherService.get_weather_report(location) if location else None
        system_prompt = get_system_prompt(settings, weather_report)
        actions_str = ""
        if actions_taken:
            actions_list = [f"Added/Updated '{a['title']}' to monitoring" + (f" with target rental price ${a['target_rental_price']:.2f}" if a.get("target_rental_price") else "") for a in actions_taken]
            actions_str = f"\n[System Note: Automated action executed on user behalf: {', '.join(actions_list)}]"

        full_prompt = f"User message: {user_message}{actions_str}{title_context_note}{recommendation_note}{holiday_ctx}"

        agent_reply = None
        if GEMINI_API_KEY:
            try:
                monitored_summary = "\n".join([f"- {i['title']} ({i['media_type']}, status: {i['status']}" + (f", target price: ${i['target_rental_price']}" if i.get("target_rental_price") else "") + ")" for i in monitored[:10]])
                if not monitored_summary:
                    monitored_summary = "None currently monitored."

                chat_context = (
                    f"{system_prompt}\n\n"
                    f"User's Monitored Watchlist Context:\n{monitored_summary}\n\n"
                    f"Recent Conversation:\n"
                )
                for m in history[-6:]:
                    chat_context += f"{m['role'].capitalize()}: {m['content']}\n"
                agent_reply = await AiAgentService._call_gemini_api(chat_context, full_prompt)
            except Exception as e:
                logger.error(f"Gemini API error during chat: {e}")

        if not agent_reply:
            agent_reply = await AiAgentService._generate_fallback_chat_reply(
                system_prompt, user_message, actions_taken, user_id, repo, tmdb
            )

        # Save assistant message
        msg_record = repo.add_chat_message(user_id, "assistant", agent_reply, actions=actions_taken)
        return {
            "message": msg_record,
            "actions_taken": actions_taken,
        }


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
    async def _call_gemini_api(system_prompt: str, user_prompt: str) -> str | None:
        """Call Gemini API via httpx using current active model endpoints."""
        models_to_try = ["gemini-flash-latest", "gemini-3.5-flash-lite"]
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\nUser: {user_prompt}"}]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
                except Exception as e:
                    logger.warning(f"Error calling Gemini model '{model_name}': {e}")
        return None

    @staticmethod
    async def _generate_fallback_chat_reply(
        system_prompt: str,
        user_message: str,
        actions: list[dict[str, Any]],
        user_id: str,
        repo: WatchlistRepository,
        tmdb: TmdbClient | None,
    ) -> str:
        """Generate persona-infused fallback response, querying user watchlist or TMDB when applicable."""
        preset = system_prompt.lower()
        msg_lower = user_message.lower()
        holiday_remark = get_approaching_holiday_or_season()

        if actions:
            t = actions[0].get("title", "it")
            p = actions[0].get("target_rental_price")
            if p:
                actions_desc = f" I've added '{t}' to your Monitoring tab and set a rental price alert for ${p:.2f}."
            else:
                actions_desc = f" I've added '{t}' directly to your Monitoring list."

            if "noir" in preset:
                return f"Got it, kid.{actions_desc} I'll keep my eye on the streets and let you know when the coast is clear."
            elif "sci" in preset:
                return f"Command acknowledged.{actions_desc} Telemetry stream active and monitoring parameters set."
            elif "sarcastic" in preset:
                return f"*Sigh* Fine, fine!{actions_desc} Don't say I never do anything for you."
            else:
                return f"*Sigh* Fine. {actions_desc} Now I have another item to calculate telemetry on daily. You're welcome."

        items = repo.list_items(user_id)
        monitored = [item for item in items if not item.get("is_owned") and (item.get("status") in {"following", "queue", "watchlist"} or not item.get("status"))]

        # Extract title query
        title_query, _ = AiAgentService._extract_title_and_price(user_message)
        if not title_query:
            patterns = [
                r"(?:any\s+)?(?:update|updates|news|info|word)\s+(?:on|about|for)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
                r"(?:why\s+didn't\s+the\s+agent\s+say\s+something\s+about|why\s+didn't\s+you\s+mention|what\s+about|tell\s+me\s+about|is\s+there\s+any\s+update\s+on|how\s+about)\s+['\"]?([^'.\"$\n]+?)['\"]?$",
                r"(?:is|when\s+is)\s+['\"]?([^'.\"$\n]+?)['\"]?\s+(?:releasing|coming\s+out|available|dropping)",
                r"(?:search|find|check)\s+(?:for\s+)?['\"]?([^'.\"$\n]+?)['\"]?$",
            ]
            for pat in patterns:
                m = re.search(pat, msg_lower, re.IGNORECASE)
                if m:
                    extracted = m.group(1).strip()
                    extracted = re.sub(r'\s+(?:released|available|coming|out|today|soon)$', '', extracted, flags=re.IGNORECASE).strip()
                    if extracted and len(extracted) > 1 and extracted not in {"my shows", "my queue", "monitored shows", "updates", "watchlist"}:
                        title_query = extracted
                        break

        if title_query:
            # Check user watchlist first
            matching_user_items = [
                i for i in items
                if title_query.lower() in i.get("title", "").lower() or any(w in i.get("title", "").lower() for w in title_query.split() if len(w) > 2)
            ]
            rec_str = ""
            if matching_user_items:
                item = matching_user_items[0]
                t_title = item.get("title")
                status_str = "monitored" if item.get("status") in {"following", "queue"} else item.get("status")
                rel_date = item.get("release_date")
                from app.models import days_until
                days = days_until(rel_date) if rel_date else None

                days_info = ""
                if days is not None:
                    if days == 0:
                        days_info = f" Releasing TODAY ({rel_date})!"
                    elif days > 0:
                        days_info = f" Releasing in {days} day{'s' if days != 1 else ''} ({rel_date})."
                    elif days >= -30:
                        days_info = f" Released recently ({abs(days)} days ago on {rel_date})."
                    else:
                        rel_year = rel_date[:4] if rel_date and len(rel_date) >= 4 else ""
                        days_info = f" Released back in {rel_year} ({rel_date})." if rel_year else f" Released on {rel_date}."
                elif rel_date:
                    days_info = f" Release date: {rel_date}."

                if tmdb and item.get("tmdb_id"):
                    try:
                        recs = await tmdb.get_recommendations(item.get("media_type", "movie"), item["tmdb_id"])
                        if recs:
                            rec_str = f" If you enjoy '{t_title}', you might also check out '{recs[0]['title']}'."
                    except Exception:
                        pass

                if "noir" in preset:
                    return f"Checked the records for '{t_title}'. It's in your queue (status: {status_str}).{days_info}{rec_str}"
                elif "sci" in preset:
                    return f"Telemetry query for '{t_title}': Status: {status_str}.{days_info}{rec_str}"
                elif "sarcastic" in preset:
                    return f"Found '{t_title}' in your queue! Status: {status_str}.{days_info}{rec_str}"
                else:
                    return f"Checked your queue for '{t_title}'—it's currently {status_str}.{days_info}{rec_str}"

            # Check TMDB if not in user items
            if tmdb:
                try:
                    res = await tmdb.search(title_query)
                    if res:
                        best = res[0]
                        t_title = best.get("title")
                        rel_date = best.get("release_date")
                        media_type = best.get("media_type")
                        rel_str = f" ({rel_date})" if rel_date else ""

                        try:
                            recs = await tmdb.get_recommendations(media_type, best["id"])
                            if recs:
                                rec_str = f" Also, you might enjoy '{recs[0]['title']}'."
                        except Exception:
                            pass

                        if "noir" in preset:
                            return f"I hit the beat and found '{t_title}' ({media_type}){rel_str} on TMDB. It's not in your queue yet. Want me to track it?{rec_str}"
                        elif "sci" in preset:
                            return f"Archive search result: Located '{t_title}' ({media_type}){rel_str}. Unmonitored. Would you like to initialize telemetry?{rec_str}"
                        elif "sarcastic" in preset:
                            return f"Found '{t_title}' ({media_type}){rel_str} on TMDB! You haven't added it to your queue yet. Want me to add it?{rec_str}"
                        else:
                            return f"I found '{t_title}' ({media_type}{rel_str}) on TMDB. It's not in your queue yet—let me know if you want me to track it.{rec_str}"
                except Exception as e:
                    logger.warning(f"Fallback TMDB search error: {e}")

            if "noir" in preset:
                return f"No leads on '{title_query}' in your files or TMDB records. Want me to try searching another title?"
            elif "sci" in preset:
                return f"Query anomaly: Target '{title_query}' not detected in local queue or TMDB archives."
            elif "sarcastic" in preset:
                return f"I checked for '{title_query}' but couldn't find anything matching that title. Double check the spelling?"
            else:
                return f"I searched for '{title_query}' in your queue and on TMDB, but couldn't find any exact matches. Double check the spelling?"

        # General updates query
        if any(w in msg_lower for w in ["all updates", "my updates", "monitored shows", "what updates", "show list", "my queue", "my list", "update", "updates", "monitored", "following", "monitoring", "upcoming"]):
            briefing_res = await AiAgentService.evaluate_monitored_updates(user_id, repo, tmdb)
            holiday_str = f" {holiday_remark}" if holiday_remark else ""
            if briefing_res.get("updates"):
                bullet_lines = "\n".join([f"• {u['message']}" for u in briefing_res["updates"]])
                count = len(briefing_res["updates"])
                if "noir" in preset:
                    return f"Chief, here are the {count} update{'s' if count > 1 else ''} on your monitored files:\n{bullet_lines}{holiday_str}"
                elif "sci" in preset:
                    return f"Telemetry sync status: {count} active update signal{'s' if count > 1 else ''}:\n{bullet_lines}{holiday_str}"
                elif "sarcastic" in preset:
                    return f"Here's what's happening with your {count} monitored show{'s' if count > 1 else ''}:\n{bullet_lines}{holiday_str}"
                else:
                    return f"Here are the latest updates for your monitored shows:\n{bullet_lines}{holiday_str}"
            elif monitored:
                titles_str = ", ".join([f"'{i['title']}'" for i in monitored[:5]])
                more_count = len(monitored) - 5
                more_str = f" and {more_count} more" if more_count > 0 else ""
                return f"You currently have {len(monitored)} monitored title(s): {titles_str}{more_str}. No urgent release alerts in the next 14 days!{holiday_str}"
            else:
                return f"You don't have any monitored shows in your list yet! Ask me to monitor a title like 'waiting for Succession' to add one.{holiday_str}"

        holiday_str = f" {holiday_remark}" if holiday_remark else ""
        if "noir" in preset:
            return "Copy that. Keeping eyes on your queue. Let me know if you want to track a specific movie or show."
        elif "sci" in preset:
            return "Telemetry nominal. Specify a title name or price target to add monitoring parameters."
        elif "sarcastic" in preset:
            return "I'm listening! Tell me what movie or show you want to track."
        else:
            return f"I'm here! Ask me about your monitored shows, or tell me what title you're waiting for.{holiday_str}"


