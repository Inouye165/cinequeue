import json
import logging
import re
from typing import Any

import httpx

from app.config import GEMINI_API_KEY
from app.repository import WatchlistRepository, DuplicateItemError
from app.services.tmdb import TmdbClient

logger = logging.getLogger(__name__)

PERSONALITY_PRESETS = {
    "cinephile": (
        "You are a passionate, witty, and knowledgeable movie & TV cinephile. "
        "You speak with excitement, subtle cinematic references, and expert insights about entertainment."
    ),
    "noir": (
        "You are a cynical, hardboiled 1940s Film Noir detective monitoring media files. "
        "You view the movie and TV landscape through rain-slicked streets, moody shadows, and dry wit."
    ),
    "scifi": (
        "You are an advanced futuristic AI unit specializing in entertainment telemetry and media archives. "
        "Your tone is crisp, precise, analytical, and futuristic."
    ),
    "sarcastic": (
        "You are a hilarious, sarcastic friend who lives and breathes movies and TV. "
        "You give great advice but can't help dropping cheeky banter and playful jabs."
    ),
}


def get_system_prompt(settings: dict[str, Any]) -> str:
    preset = settings.get("personality_preset", "cinephile")
    custom = settings.get("custom_prompt", "").strip()
    if preset == "custom" and custom:
        return f"You are an AI Agent for Cinequeue with the following custom personality:\n{custom}"
    preset_prompt = PERSONALITY_PRESETS.get(preset, PERSONALITY_PRESETS["cinephile"])
    return (
        f"{preset_prompt}\n"
        "You are the AI assistant for Cinequeue, a personal movie and show monitoring app. "
        "You help users keep track of upcoming releases, season premieres, rental price drops, and media updates. "
        "Always stay in character while being helpful, concise, and accurate."
    )


class AiAgentService:
    @staticmethod
    async def evaluate_monitored_updates(
        user_id: str, repo: WatchlistRepository, tmdb: TmdbClient | None
    ) -> dict[str, Any]:
        """Evaluate user's queue/following titles and generate a personalized login briefing."""
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

        # Sort updates by urgency and date proximity
        updates.sort(key=lambda u: (u.get("urgency", 5), abs(u.get("days_away") or 999)))

        # Format briefing response
        system_prompt = get_system_prompt(settings)
        briefing_text = await AiAgentService._format_briefing_text(system_prompt, updates, monitored)

        return {
            "enabled": True,
            "briefing": briefing_text,
            "updates_count": len(updates),
            "updates": updates,
            "personality_preset": settings.get("personality_preset", "cinephile"),
        }

    @staticmethod
    async def _format_briefing_text(
        system_prompt: str, updates: list[dict[str, Any]], monitored: list[dict[str, Any]]
    ) -> str:
        summary_points = "\n".join([f"• {u['message']}" for u in updates]) if updates else "No urgent release or price alerts today, everything is running smoothly!"
        prompt = (
            f"Here are ALL current updates for the user's monitored movies and TV shows:\n"
            f"{summary_points}\n\n"
            f"Total monitored titles: {len(monitored)}.\n"
            f"IMPORTANT: You MUST include and summarize ALL of the updates listed above (especially highlighting any title releasing in the next 2 days or released since last login). Write a personal login greeting and update summary in your personality."
        )

        if GEMINI_API_KEY:
            try:
                llm_response = await AiAgentService._call_gemini_api(system_prompt, prompt)
                if llm_response:
                    return llm_response
            except Exception as e:
                logger.error(f"Gemini API error during briefing generation: {e}")

        # Smart Fallback briefing generator - ALL updates included!
        preset = system_prompt.lower()
        if not updates:
            if "noir" in preset:
                return f"Rain is falling outside, but your watch queue is calm. We're keeping tabs on all {len(monitored)} monitored files."
            elif "sci" in preset:
                return f"System scan complete for {len(monitored)} monitored units. Zero release anomalies detected today."
            elif "sarcastic" in preset:
                return f"Nothing new today! Your {len(monitored)} monitored shows are taking their sweet time. I'll let you know when someone actually releases something."
            else:
                return f"Welcome back, film fan! Your queue is up to date with {len(monitored)} titles monitored. I'm keeping a close eye out for new release dates and price drops!"

        bullet_lines = "\n".join([f"• {u['message']}" for u in updates])
        count = len(updates)

        if "noir" in preset:
            return f"Chief, the night shift turned up {count} update{'s' if count > 1 else ''} on your watched list:\n{bullet_lines}\nKeep your eyes peeled."
        elif "sci" in preset:
            return f"Telemetry sync complete. {count} event signal{'s' if count > 1 else ''} detected:\n{bullet_lines}\nAll systems nominal."
        elif "sarcastic" in preset:
            return f"Well, look who finally logged in! Here are {count} update{'s' if count > 1 else ''} you need to check out:\n{bullet_lines}"
        else:
            # Cinephile default
            return f"Welcome back! Cinequeue agent here with {count} update{'s' if count > 1 else ''} on your list:\n{bullet_lines}\nLet me know if you want to add more to your monitoring!"

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

        # 1. Intent Extraction: Auto-add mentioned titles to monitoring
        if settings.get("auto_add_mentioned", True) and tmdb:
            mentioned_title, target_price = AiAgentService._extract_title_and_price(user_message)
            if mentioned_title:
                try:
                    search_res = await tmdb.search(mentioned_title)
                    if search_res:
                        best_match = search_res[0]
                        media_type = best_match["media_type"]
                        tmdb_id = best_match["id"]
                        title = best_match["title"]
                        poster_path = best_match.get("poster_url", "").replace("https://image.tmdb.org/t/p/w342", "") if best_match.get("poster_url") else None
                        release_date = best_match.get("release_date")

                        try:
                            item = repo.add_item(
                                user_id=user_id,
                                media_type=media_type,
                                tmdb_id=tmdb_id,
                                title=title,
                                poster_path=poster_path,
                                release_date=release_date,
                                status="following",
                                target_rental_price=target_price,
                            )
                            actions_taken.append({
                                "action": "add_monitoring",
                                "title": title,
                                "media_type": media_type,
                                "tmdb_id": tmdb_id,
                                "target_rental_price": target_price,
                            })
                        except DuplicateItemError:
                            # Update existing item to following and set price if provided
                            repo.update_item(
                                user_id=user_id,
                                media_type=media_type,
                                tmdb_id=tmdb_id,
                                status="following",
                                target_rental_price=target_price,
                            )
                            actions_taken.append({
                                "action": "update_monitoring",
                                "title": title,
                                "media_type": media_type,
                                "tmdb_id": tmdb_id,
                                "target_rental_price": target_price,
                            })
                except Exception as e:
                    logger.error(f"Error during auto-add title search: {e}")

        # 2. Format LLM or Fallback prompt
        system_prompt = get_system_prompt(settings)
        actions_str = ""
        if actions_taken:
            actions_list = [f"Added/Updated '{a['title']}' to monitoring" + (f" with target rental price ${a['target_rental_price']:.2f}" if a.get("target_rental_price") else "") for a in actions_taken]
            actions_str = f"\n[System Note: Automated action executed on user behalf: {', '.join(actions_list)}]"

        full_prompt = f"User message: {user_message}{actions_str}"

        # 3. Call LLM or smart fallback
        agent_reply = None
        if GEMINI_API_KEY:
            try:
                items = repo.list_items(user_id)
                monitored = [item for item in items if not item.get("is_owned") and item.get("status") in {"following", "queue"}]
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
        # Match price e.g. "$3", "$2.99", "3 dollars", "under $4"
        price_match = re.search(r'(?:\$|under\s+\$?|to\s+rent\s+for\s+\$?)\s*(\d+(?:\.\d{1,2})?)', text, re.IGNORECASE)
        target_price = float(price_match.group(1)) if price_match else None

        # Match waiting/notification patterns
        patterns = [
            r"(?:waiting|wait|looking)\s+for\s+(?:the\s+movie\s+|the\s+show\s+)?['\"]?([^'.\"$\n]+?)['\"]?\s*(?:to\s+(?:come|air|drop|rent|release)|under|\$|$)",
            r"(?:notify|alert|tell)\s+me\s+when\s+(?:the\s+movie\s+|the\s+show\s+)?['\"]?([^'.\"$\n]+?)['\"]?\s*(?:drops|is|available|to\s+rent|under|\$|$)",
            r"(?:add|track|monitor)\s+['\"]?([^'.\"$\n]+?)['\"]?\s*(?:to\s+my\s+list|to\s+monitoring|under|\$|$)",
            r"(?:can't|cant)\s+wait\s+for\s+['\"]?([^'.\"$\n]+?)['\"]?\s*(?:to\s+drop|to\s+rent|under|\$|$)",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                extracted = m.group(1).strip()
                # Clean trailing keywords
                extracted = re.sub(r'\s+(?:to|for|under|on|in|drops)$', '', extracted, flags=re.IGNORECASE).strip()
                if extracted and len(extracted) > 1:
                    return extracted, target_price

        return None, target_price

    @staticmethod
    async def _call_gemini_api(system_prompt: str, user_prompt: str) -> str | None:
        """Call Gemini API via httpx."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\nUser: {user_prompt}"}]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
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
                return f"Alright, alright!{actions_desc} You have good taste, I'll give you that much."
            else:
                return f"Sounds good!{actions_desc} I'll keep checking for updates, air dates, and price drops for you!"

        items = repo.list_items(user_id)
        monitored = [item for item in items if not item.get("is_owned") and (item.get("status") in {"following", "queue", "watchlist"} or not item.get("status"))]

        # Query about monitored shows or updates
        if any(w in msg_lower for w in ["update", "monitored", "show", "queue", "watchlist", "list", "following", "monitoring", "upcoming", "recent", "new"]):
            briefing_res = await AiAgentService.evaluate_monitored_updates(user_id, repo, tmdb)
            if briefing_res.get("updates"):
                bullet_lines = "\n".join([f"• {u['message']}" for u in briefing_res["updates"]])
                return f"Here are all current updates for your monitored shows:\n{bullet_lines}"
            elif monitored:
                titles_str = ", ".join([f"'{i['title']}'" for i in monitored[:5]])
                more_count = len(monitored) - 5
                more_str = f" and {more_count} more" if more_count > 0 else ""
                return f"You currently have {len(monitored)} monitored title(s): {titles_str}{more_str}. No urgent release alerts in the next 14 days!"
            else:
                return "You don't have any monitored shows in your list yet! Ask me to monitor a title like 'I'm waiting for Severance' or add items from search."

        # 1. Extract potential title from query first (e.g. "any update on what dreams may come" -> "what dreams may come")
        title_query = None
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
            # Check user's watchlist first
            matching_user_items = [
                i for i in items
                if title_query in i.get("title", "").lower() or any(w in i.get("title", "").lower() for w in title_query.split() if len(w) > 2)
            ]
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
                    else:
                        days_info = f" Released {abs(days)} day{'s' if abs(days) != 1 else ''} ago on {rel_date}."
                elif rel_date:
                    days_info = f" Release date: {rel_date}."

                if "noir" in preset:
                    return f"Checked the records for '{t_title}'. It's currently in your list (status: {status_str}).{days_info}"
                elif "sci" in preset:
                    return f"Telemetry query for unit '{t_title}': Status: {status_str}.{days_info}"
                elif "sarcastic" in preset:
                    return f"Found '{t_title}' in your queue! Status is {status_str}.{days_info}"
                else:
                    return f"I checked your queue for '{t_title}'! It's currently {status_str}.{days_info}"

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

                        if "noir" in preset:
                            return f"I hit the beat and found '{t_title}' ({media_type}){rel_str} on TMDB. It's not in your queue yet. Want me to track it?"
                        elif "sci" in preset:
                            return f"Archive search result: Located '{t_title}' ({media_type}){rel_str}. Unmonitored. Would you like to initialize telemetry?"
                        elif "sarcastic" in preset:
                            return f"Found '{t_title}' ({media_type}){rel_str} on TMDB! You haven't added it to your queue yet though. Should I add it?"
                        else:
                            return f"I searched for '{t_title}' and found it on TMDB ({media_type}{rel_str}). It's not in your queue yet — would you like me to monitor it for you?"
                except Exception as e:
                    logger.warning(f"Fallback TMDB search error: {e}")

            # If title was queried but not found in user items and no TMDB results:
            if "noir" in preset:
                return f"No leads on '{title_query}' in your files or TMDB records. Want me to try searching another title?"
            elif "sci" in preset:
                return f"Query anomaly: Target '{title_query}' not detected in local queue or TMDB archives."
            elif "sarcastic" in preset:
                return f"I checked for '{title_query}' but couldn't find anything matching that title. Double check the spelling?"
            else:
                return f"I searched for '{title_query}' in your queue and on TMDB, but couldn't find any exact matches. Would you like me to check a different title?"

        # 2. General updates query or broad list query (ONLY if no title_query was requested)
        if any(w in msg_lower for w in ["all updates", "my updates", "monitored shows", "what updates", "show list", "my queue", "my list", "update", "updates", "monitored", "following", "monitoring", "upcoming"]):
            briefing_res = await AiAgentService.evaluate_monitored_updates(user_id, repo, tmdb)
            if briefing_res.get("updates"):
                bullet_lines = "\n".join([f"• {u['message']}" for u in briefing_res["updates"]])
                count = len(briefing_res["updates"])
                if "noir" in preset:
                    return f"Chief, here are the {count} update{'s' if count > 1 else ''} on your monitored files:\n{bullet_lines}"
                elif "sci" in preset:
                    return f"Telemetry sync status: {count} active update signal{'s' if count > 1 else ''}:\n{bullet_lines}"
                elif "sarcastic" in preset:
                    return f"Here's what's actually happening with your {count} monitored show{'s' if count > 1 else ''}:\n{bullet_lines}"
                else:
                    return f"Here are all current updates for your monitored shows:\n{bullet_lines}"
            elif monitored:
                titles_str = ", ".join([f"'{i['title']}'" for i in monitored[:5]])
                more_count = len(monitored) - 5
                more_str = f" and {more_count} more" if more_count > 0 else ""
                return f"You currently have {len(monitored)} monitored title(s): {titles_str}{more_str}. No urgent release alerts in the next 14 days!"
            else:
                return "You don't have any monitored shows in your list yet! Ask me to monitor a title like 'I'm waiting for Severance' or add items from search."

        if "noir" in preset:
            return "Copy that. Keeping eyes on your queue. Let me know if you want to track a specific movie or show."
        elif "sci" in preset:
            return "Telemetry nominal. Specify a title name or price target to add monitoring parameters."
        elif "sarcastic" in preset:
            return "I'm listening! Tell me what movie or show you want to track."
        else:
            return "I'm here to help! Ask me about your monitored shows or tell me what title you're waiting for."

