"""Briefing service handling change detection, news deduplication, candidate ranking, and persistent novelty tracking."""

import hashlib
import logging
import re
from typing import Any

from app.repository import WatchlistRepository
from app.services.tmdb import TmdbClient
from app.services.weather_service import WeatherService

logger = logging.getLogger(__name__)


def generate_item_key(item_type: str, title_id: str, detail_suffix: str) -> str:
    """Generate a deterministic item key."""
    clean_type = re.sub(r'[^a-zA-Z0-9_]', '', item_type)
    clean_title = re.sub(r'[^a-zA-Z0-9_]', '', str(title_id))
    clean_suffix = re.sub(r'[^a-zA-Z0-9_:-]', '', str(detail_suffix))
    return f"{clean_type}:{clean_title}:{clean_suffix}"


def compute_content_fingerprint(text: str) -> str:
    """Generate SHA256 content fingerprint for deduplication."""
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]


class BriefingService:
    @staticmethod
    async def evaluate_startup_briefing(
        user_id: str,
        repo: WatchlistRepository,
        tmdb: TmdbClient | None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate or retrieve a session-cached startup briefing using persistent novelty tracking."""
        settings = repo.get_agent_settings(user_id)
        if not settings.get("notify_on_login", True):
            return {"enabled": False, "briefing": None, "updates": []}

        if session_id:
            cached = repo.get_agent_session(user_id, session_id)
            if cached:
                logger.info(f"Returning session-cached briefing for session_id={session_id}")
                return cached

        items = repo.list_items(user_id)
        monitored = [
            item for item in items
            if not item.get("is_owned") and (item.get("status") in {"following", "queue", "watchlist"} or not item.get("status"))
        ]

        presented_keys = repo.get_presented_briefing_keys(user_id)
        candidate_items: list[dict[str, Any]] = []

        # 1. Date & Availability Updates for Monitored Titles
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
                        "type": "newly_available",
                        "urgency": 1,
                        "title": title,
                        "title_id": title_id,
                        "available_date": air_date,
                        "message": msg,
                        "content_fingerprint": compute_content_fingerprint(msg),
                    })
                elif 1 <= days_away <= 3:
                    day_desc = "tomorrow" if days_away == 1 else f"in {days_away} days"
                    msg = f"'{title}'{season_str} arrives {day_desc} ({air_date})."
                    key = generate_item_key("imminent_release", title_id, air_date or "imminent")
                    candidate_items.append({
                        "item_key": key,
                        "type": "imminent_release",
                        "urgency": 2,
                        "title": title,
                        "title_id": title_id,
                        "release_date": air_date,
                        "days_away": days_away,
                        "message": msg,
                        "content_fingerprint": compute_content_fingerprint(msg),
                    })
                elif 4 <= days_away <= 14:
                    msg = f"'{title}'{season_str} releases in {days_away} days ({air_date})."
                    key = generate_item_key("upcoming_release", title_id, air_date or "upcoming")
                    candidate_items.append({
                        "item_key": key,
                        "type": "upcoming_release",
                        "urgency": 4,
                        "title": title,
                        "title_id": title_id,
                        "release_date": air_date,
                        "days_away": days_away,
                        "message": msg,
                        "content_fingerprint": compute_content_fingerprint(msg),
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
                        msg = f"'{title}' is now available to rent for ${min_price:.2f} (target was ${target_price:.2f})."
                        key = generate_item_key("price_drop", title_id, f"{min_price:.2f}")
                        candidate_items.append({
                            "item_key": key,
                            "type": "price_drop",
                            "urgency": 2,
                            "title": title,
                            "title_id": title_id,
                            "price": min_price,
                            "message": msg,
                            "content_fingerprint": compute_content_fingerprint(msg),
                        })
                    elif providers.get("is_free_streaming") and (item.get("watch_free_streaming") or target_price is not None):
                        msg = f"'{title}' is now streaming for free on included platforms."
                        key = generate_item_key("free_streaming", title_id, "free")
                        candidate_items.append({
                            "item_key": key,
                            "type": "free_streaming",
                            "urgency": 2,
                            "title": title,
                            "title_id": title_id,
                            "message": msg,
                            "content_fingerprint": compute_content_fingerprint(msg),
                        })
                except Exception as e:
                    logger.warning(f"Error checking watch providers for {title}: {e}")

        # 3. News Feed Collection & Clustering
        if tmdb and monitored:
            try:
                for item in monitored[:5]:
                    t_title = item.get("title")
                    media_type = item.get("media_type", "movie")
                    tmdb_id = item.get("tmdb_id")
                    title_id = f"{media_type}_{tmdb_id}"

                    if t_title:
                        news_articles = await tmdb.get_news(t_title)
                        for art in news_articles[:2]:
                            headline = art.get("title", "")
                            link = art.get("link", "")
                            source = art.get("source", "News")
                            url_hash = hashlib.md5(link.encode("utf-8")).hexdigest()[:10] if link else compute_content_fingerprint(headline)

                            status_label = "confirmed" if any(w in headline.lower() for w in ["officially", "confirmed", "announces", "release date"]) else ("speculative" if "rumor" in headline.lower() else "reported")
                            msg = f"[{status_label.upper()}] {source}: {headline}"
                            key = generate_item_key("news", title_id, url_hash)
                            candidate_items.append({
                                "item_key": key,
                                "type": "news",
                                "urgency": 3,
                                "title": t_title,
                                "title_id": title_id,
                                "source_id": link or source,
                                "headline": headline,
                                "source": source,
                                "status_label": status_label,
                                "message": msg,
                                "content_fingerprint": compute_content_fingerprint(headline),
                            })
            except Exception as e:
                logger.warning(f"Error checking news articles for briefing: {e}")

        # 3b. Persistent Query Memory Recall Evaluation
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
                            "type": "memory_recall",
                            "urgency": 2,
                            "title": m_title,
                            "title_id": f"mem_{m_title}",
                            "message": msg,
                            "content_fingerprint": compute_content_fingerprint(msg),
                        })
        except Exception as e:
            logger.warning(f"Error evaluating query memories for briefing: {e}")

        total_candidates = len(candidate_items)

        # 4. Novelty Filtering
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
                prev_urgency = prev_pres.get("importance", 3)
                curr_urgency = cand.get("urgency", 3)

                if curr_fp != prev_fp or curr_urgency < prev_urgency:
                    cand["new_to_user"] = False
                    cand["material_change"] = True
                    novel_items.append(cand)
                else:
                    already_presented_count += 1
            else:
                cand["new_to_user"] = True
                novel_items.append(cand)

        # 5. Rank and select top 3-5 items
        novel_items.sort(key=lambda x: (x.get("urgency", 5), not x.get("new_to_user", True)))
        selected_items = novel_items[:5]
        selected_count = len(selected_items)

        # 6. Fetch local weather
        location = settings.get("location", "").strip()
        weather_report = await WeatherService.get_weather_report(location) if location else None

        # 7. Generate Natural Language Briefing
        from app.services.agent_service import AiAgentService
        briefing_text = await AiAgentService._format_novelty_briefing(selected_items, weather_report, len(monitored))

        # Record presentations in DB
        if selected_items:
            repo.record_briefing_presentations(user_id, selected_items)

        briefing_data = {
            "enabled": True,
            "briefing": briefing_text,
            "updates_count": selected_count,
            "updates": selected_items,
            "personality_preset": settings.get("personality_preset", "cinephile"),
            "location": location,
            "weather_report": weather_report,
            "telemetry": {
                "total_candidates": total_candidates,
                "duplicate_count": duplicate_count,
                "already_presented_count": already_presented_count,
                "selected_count": selected_count,
            }
        }

        if session_id:
            repo.save_agent_session(user_id, session_id, briefing_data)

        return briefing_data
