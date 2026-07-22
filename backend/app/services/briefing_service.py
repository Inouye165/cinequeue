"""Briefing service handling 17-step startup data collection, news clustering, novelty tracking, and structured LLM briefings."""

import hashlib
import logging
import re
import time
from typing import Any

from app.repository import WatchlistRepository
from app.services.news_service import (
    TmdbEntertainmentNewsProvider,
    cluster_news_stories,
    compute_content_fingerprint,
    rank_briefing_candidates,
)
from app.services.tmdb import TmdbClient
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)


def generate_item_key(item_type: str, title_id: str, detail_suffix: str) -> str:
    """Generate a deterministic item key."""
    clean_type = re.sub(r'[^a-zA-Z0-9_]', '', item_type)
    clean_title = re.sub(r'[^a-zA-Z0-9_]', '', str(title_id))
    clean_suffix = re.sub(r'[^a-zA-Z0-9_:-]', '', str(detail_suffix))
    return f"{clean_type}:{clean_title}:{clean_suffix}"


class BriefingService:
    @staticmethod
    async def evaluate_startup_briefing(
        user_id: str,
        repo: WatchlistRepository,
        tmdb: TmdbClient | None,
        session_id: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Generate or retrieve a startup briefing following the 17-step sequence."""
        now_iso = repo.utc_now_iso()

        # Step 1 & 2: Load settings
        settings = repo.get_agent_settings(user_id)
        if not settings.get("notify_on_login", True):
            return {"enabled": False, "briefing": None, "updates": []}

        # Session caching check
        if session_id and not force_refresh:
            cached = repo.get_agent_session(user_id, session_id)
            if cached:
                logger.info(f"Returning session-cached briefing for session_id={session_id}")
                return cached

        # Step 3: Capture reference timestamps BEFORE updating login or presentation state
        briefing_state = repo.get_user_briefing_state(user_id)
        previous_login_at = briefing_state.get("previous_login_at")
        previous_briefing_presented_at = briefing_state.get("previous_briefing_presented_at")

        # Step 4: Load monitored titles
        items = repo.list_items(user_id)
        monitored = [
            item for item in items
            if not item.get("is_owned") and (item.get("status") in {"following", "queue", "watchlist"} or not item.get("status"))
        ]

        presented_keys = repo.get_presented_briefing_keys(user_id)
        candidate_items: list[dict[str, Any]] = []

        # Step 5: Retrieve cached or current local weather (WeatherData object)
        location = settings.get("location", "").strip()
        weather_service = WeatherService()
        weather_data = await weather_service.get_weather_data(location) if location else None

        # Step 6: Refresh release & streaming availability information
        for item in monitored:
            media_type = item.get("media_type", "movie")
            tmdb_id = item.get("tmdb_id")
            title = item.get("title", "Untitled")
            title_id = f"{media_type}_{tmdb_id}"

            air_date = item.get("release_date")
            days_away = None
            next_season_num = None

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

            if days_away is not None:
                season_str = f" Season {next_season_num}" if next_season_num else ""

                if -14 <= days_away <= 0:
                    ago_days = abs(days_away)
                    date_desc = "TODAY" if ago_days == 0 else f"{ago_days} day{'s' if ago_days != 1 else ''} ago"
                    msg = f"'{title}'{season_str} became available ({date_desc} on {air_date})."
                    key = generate_item_key("newly_available", title_id, air_date or "available")
                    candidate_items.append({
                        "item_key": key,
                        "story_cluster_id": key,
                        "type": "newly_available",
                        "category": "newly_available",
                        "urgency": 1,
                        "title": title,
                        "title_id": title_id,
                        "available_date": air_date,
                        "message": msg,
                        "summary": msg,
                        "content_fingerprint": compute_content_fingerprint(msg),
                        "published_at": air_date or now_iso,
                    })
                elif 1 <= days_away <= 3:
                    day_desc = "tomorrow" if days_away == 1 else f"in {days_away} days"
                    msg = f"'{title}'{season_str} arrives {day_desc} ({air_date})."
                    key = generate_item_key("imminent_release", title_id, air_date or "imminent")
                    candidate_items.append({
                        "item_key": key,
                        "story_cluster_id": key,
                        "type": "imminent_release",
                        "category": "imminent_release",
                        "urgency": 2,
                        "title": title,
                        "title_id": title_id,
                        "release_date": air_date,
                        "days_away": days_away,
                        "message": msg,
                        "summary": msg,
                        "content_fingerprint": compute_content_fingerprint(msg),
                        "published_at": air_date or now_iso,
                    })
                elif 4 <= days_away <= 14:
                    msg = f"'{title}'{season_str} releases in {days_away} days ({air_date})."
                    key = generate_item_key("upcoming_release", title_id, air_date or "upcoming")
                    candidate_items.append({
                        "item_key": key,
                        "story_cluster_id": key,
                        "type": "upcoming_release",
                        "category": "upcoming_release",
                        "urgency": 4,
                        "title": title,
                        "title_id": title_id,
                        "release_date": air_date,
                        "days_away": days_away,
                        "message": msg,
                        "summary": msg,
                        "content_fingerprint": compute_content_fingerprint(msg),
                        "published_at": air_date or now_iso,
                    })

            # Target Rental Price & Free Streaming Check
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
                                prices.append(float(str(curr).replace("$", "")))
                            except ValueError:
                                pass

                    if target_price is not None and prices and min(prices) <= target_price:
                        min_price = min(prices)
                        msg = f"'{title}' is now available to rent for ${min_price:.2f} (target was ${target_price:.2f})."
                        key = generate_item_key("price_drop", title_id, f"{min_price:.2f}")
                        candidate_items.append({
                            "item_key": key,
                            "story_cluster_id": key,
                            "type": "price_drop",
                            "category": "price_drop",
                            "urgency": 2,
                            "title": title,
                            "title_id": title_id,
                            "price": min_price,
                            "message": msg,
                            "summary": msg,
                            "content_fingerprint": compute_content_fingerprint(msg),
                            "published_at": now_iso,
                        })
                    elif providers.get("is_free_streaming") and (item.get("watch_free_streaming") or target_price is not None):
                        msg = f"'{title}' is now streaming for free on included platforms."
                        key = generate_item_key("free_streaming", title_id, "free")
                        candidate_items.append({
                            "item_key": key,
                            "story_cluster_id": key,
                            "type": "free_streaming",
                            "category": "free_streaming",
                            "urgency": 2,
                            "title": title,
                            "title_id": title_id,
                            "message": msg,
                            "summary": msg,
                            "content_fingerprint": compute_content_fingerprint(msg),
                            "published_at": now_iso,
                        })
                except Exception as e:
                    logger.warning(f"Error checking watch providers for {title}: {e}")

        # Step 7 & 8: Fetch, normalize & validate entertainment news
        raw_news_articles = []
        if tmdb and monitored:
            news_provider = TmdbEntertainmentNewsProvider(tmdb)
            for item in monitored[:5]:
                t_title = item.get("title")
                media_type = item.get("media_type", "movie")
                tmdb_id = item.get("tmdb_id")
                title_id = f"{media_type}_{tmdb_id}"
                if t_title:
                    arts = await news_provider.fetch_news_for_title(t_title, title_id)
                    raw_news_articles.extend(arts)

        # Step 9: Cluster duplicate news stories
        clustered_news = cluster_news_stories(raw_news_articles)
        for cluster in clustered_news:
            candidate_items.append({
                "item_key": cluster["story_cluster_id"],
                "story_cluster_id": cluster["story_cluster_id"],
                "type": "entertainment_news",
                "category": cluster["category"],
                "urgency": 3,
                "title": cluster["related_title"],
                "title_id": cluster["title_id"],
                "headline": cluster["headline"],
                "source": cluster["source"],
                "url": cluster["url"],
                "verification": cluster["verification"],
                "message": f"[{cluster['verification'].upper()}] {cluster['source']}: {cluster['headline']}",
                "summary": cluster["summary"],
                "content_fingerprint": cluster["content_fingerprint"],
                "published_at": cluster["published_at"],
            })

        # Query memory recall
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
                    if m_days is not None and -14 <= m_days <= 14:
                        msg = f"💡 MEMORY RECALL: You asked about '{m_title}' on {asked_at_str}. It is releasing/available ({m_rel_date})."
                        key = generate_item_key("memory_recall", f"mem_{m_media}_{m_title}", m_rel_date)
                        candidate_items.append({
                            "item_key": key,
                            "story_cluster_id": key,
                            "type": "memory_recall",
                            "category": "memory_recall",
                            "urgency": 2,
                            "title": m_title,
                            "title_id": f"mem_{m_title}",
                            "message": msg,
                            "summary": msg,
                            "content_fingerprint": compute_content_fingerprint(msg),
                            "published_at": now_iso,
                        })
        except Exception as e:
            logger.warning(f"Error evaluating query memories for briefing: {e}")

        total_candidates = len(candidate_items)

        # Step 10 & 11: Novelty Detection & Material Change Check
        novel_items: list[dict[str, Any]] = []
        already_presented_count = 0
        duplicate_count = 0
        seen_keys: set[str] = set()

        for cand in candidate_items:
            key = cand["item_key"]
            if key in seen_keys:
                duplicate_count += 1
                continue
            seen_keys.add(key)

            prev_pres = presented_keys.get(key)
            if prev_pres:
                prev_fp = prev_pres.get("content_fingerprint")
                curr_fp = cand["content_fingerprint"]
                prev_verif = prev_pres.get("verification") or prev_pres.get("importance")
                curr_verif = cand.get("verification") or cand.get("importance")

                # Story is new/materially changed if fingerprint changed or verification upgraded
                if curr_fp != prev_fp or (cand.get("type") == "entertainment_news" and curr_verif != prev_verif):
                    cand["new_to_user"] = False
                    cand["material_change"] = True
                    novel_items.append(cand)
                else:
                    already_presented_count += 1
            else:
                cand["new_to_user"] = True
                cand["material_change"] = False
                novel_items.append(cand)

        # Step 12 & 13: Rank candidates & select top 3-5 items
        ranked_items = rank_briefing_candidates(novel_items)
        selected_items = ranked_items[:5]
        selected_count = len(selected_items)

        # Step 14 & 15: Construct structured JSON object and generate LLM briefing
        from app.services.agent_service import AiAgentService
        briefing_text = await AiAgentService._format_structured_llm_briefing(
            settings=settings,
            weather_data=weather_data,
            briefing_items=selected_items,
            total_monitored=len(monitored),
        )

        # Step 16: Persist presentation records
        if selected_items:
            repo.record_briefing_presentations(user_id, selected_items)

        # Step 17: Update previous_login_at and previous_briefing_presented_at timestamps in DB
        repo.update_user_briefing_state(
            user_id=user_id,
            login_at=now_iso,
            briefing_presented_at=now_iso if selected_count > 0 else previous_briefing_presented_at,
        )

        briefing_data = {
            "enabled": True,
            "briefing": briefing_text,
            "updates_count": selected_count,
            "updates": selected_items,
            "personality_preset": settings.get("personality_preset", "cinephile"),
            "location": location,
            "weather": weather_data.to_dict() if weather_data else None,
            "previous_login_at": previous_login_at,
            "previous_briefing_presented_at": previous_briefing_presented_at,
            "telemetry": {
                "total_candidates": total_candidates,
                "duplicate_count": duplicate_count,
                "already_presented_count": already_presented_count,
                "selected_count": selected_count,
            }
        }

        if session_id:
            repo.save_agent_session(user_id, session_id, briefing_data)

        # Save briefing into chat history so startup chat is available in Chat AI
        if briefing_text:
            try:
                recent_msgs = repo.list_chat_messages(user_id, limit=5)
                if not recent_msgs or recent_msgs[-1].get("content") != briefing_text:
                    repo.add_chat_message(user_id, "assistant", briefing_text)
            except Exception as e:
                logger.warning(f"Error adding briefing to chat history: {e}")

        return briefing_data
