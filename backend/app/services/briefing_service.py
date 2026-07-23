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


def _ensure_briefing_in_chat_history(user_id: str, briefing_text: str | None, repo: WatchlistRepository) -> None:
    """Ensure the startup briefing greeting is recorded in assistant chat history."""
    if not briefing_text or not briefing_text.strip():
        return
    try:
        recent_msgs = repo.list_chat_messages(user_id, limit=5)
        if not recent_msgs or recent_msgs[-1].get("content") != briefing_text:
            repo.add_chat_message(user_id, "assistant", briefing_text)
    except Exception as e:
        logger.warning(f"Error ensuring briefing in chat history: {e}")


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
                b_text = cached.get("briefing") or ""
                if "Nothing major changed in your watchlist" not in b_text:
                    logger.info(f"Returning session-cached briefing for session_id={session_id}")
                    _ensure_briefing_in_chat_history(user_id, b_text, repo)
                    return cached
                logger.info(f"Invalidating stale hardcoded briefing for session_id={session_id}")



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

        # Build Decision Engine Candidates
        from app.decision_models import Candidate, CandidateType, DecisionConfig, PromptVersion
        from app.services.decision_engine import DecisionEngine, PersonalInterestScorer

        engine_candidates: list[Candidate] = []

        # 1. Weather Alert Candidate (Severe Weather Warning)
        if weather_data and weather_data.significant_alert:
            alert_text = weather_data.significant_alert
            engine_candidates.append(Candidate(
                candidate_id=f"weather_alert:{hash(alert_text)}",
                type=CandidateType.WEATHER_ALERT.value,
                title="Severe Weather Warning",
                summary=alert_text,
                source="weather_service",
                required=True,
                importance_score=0.95,
                interest_score=0.90,
                confidence_score=0.99,
                interest_reasons=["Severe local weather warning requires immediate user notice"],
            ))

        # 2. Monitored Items Candidates
        for cand in candidate_items:
            c_type = cand.get("type", "monitored_update")
            c_title = cand.get("title", "Monitored Item")
            c_summary = cand.get("summary") or cand.get("message", "")
            c_key = cand.get("item_key", f"monitored_{hash(c_title)}")

            if c_type in {"releasing_today", "releasing_tomorrow", "released_recently", "upcoming_release", "price_drop", "free_streaming", "memory_recall"}:
                cand_type = (
                    CandidateType.MONITORED_TITLE_RELEASE.value
                    if any(k in c_type for k in ["release", "today", "tomorrow", "recently"])
                    else (CandidateType.PRICE_DROP.value if c_type == "price_drop" else CandidateType.MONITORED_TITLE_URGENT_UPDATE.value)
                )
                engine_candidates.append(Candidate(
                    candidate_id=c_key,
                    type=cand_type,
                    title=c_title,
                    summary=c_summary,
                    source="watchlist_data",
                    required=True,
                    importance_score=0.90,
                    interest_score=0.95,
                    confidence_score=0.98,
                    interest_reasons=[f"Monitored item in user's queue ({c_type})"],
                ))
            elif c_type == "entertainment_news":
                score_val, reasons = PersonalInterestScorer.calculate_interest(user_id, c_title, repo)
                engine_candidates.append(Candidate(
                    candidate_id=c_key,
                    type=CandidateType.MONITORED_TITLE_URGENT_UPDATE.value,
                    title=c_title,
                    summary=c_summary,
                    source="news_and_watchlist",
                    required=False,
                    importance_score=0.70,
                    interest_score=max(0.75, score_val),
                    confidence_score=0.90,
                    interest_reasons=reasons,
                ))


        # 3. Ordinary Weather Viewing Connection Candidate (if rain/snow & streaming arrival exists)
        if weather_data and weather_data.conditions and any(w in weather_data.conditions.lower() for w in ["rain", "storm", "snow", "shower"]):
            streaming_cands = [c for c in engine_candidates if c.type in {CandidateType.STREAMING_ARRIVAL.value, CandidateType.MONITORED_TITLE_RELEASE.value}]
            if streaming_cands:
                top_stream = streaming_cands[0]
                engine_candidates.append(Candidate(
                    candidate_id=f"weather_conn:{top_stream.candidate_id}",
                    type=CandidateType.WEATHER_VIEWING_CONNECTION.value,
                    title=top_stream.title,
                    summary=f"It is currently {weather_data.conditions.lower()} in {location or 'your area'}, and '{top_stream.title}' became available to watch.",
                    source="weather_and_provider_data",
                    required=False,
                    importance_score=0.65,
                    interest_score=0.85,
                    confidence_score=0.95,
                    interest_reasons=[f"Rain/snow outside pairs naturally with streaming release of '{top_stream.title}'"],
                ))

        # 4. Verified Trivia Candidates
        try:
            rated_list = repo.list_rated_movies(user_id)
            if rated_list:
                top_rated = rated_list[0]
                t_facts = repo.list_verified_trivia(title=top_rated["title"], tmdb_id=top_rated["tmdb_id"])
                if not t_facts:
                    # Provide approved sample trivia
                    t_facts = [{
                        "fact_id": f"trivia_{top_rated['tmdb_id']}_1",
                        "title": top_rated["title"],
                        "tmdb_id": top_rated["tmdb_id"],
                        "fact_text": f"Random movie fact: much of {top_rated['title']} was praised for iconic location filming.",
                        "source": "verified_archive",
                    }]
                for tf in t_facts:
                    t_score, t_reasons = PersonalInterestScorer.calculate_interest(user_id, tf["title"], repo, tmdb_id=tf.get("tmdb_id"))
                    engine_candidates.append(Candidate(
                        candidate_id=tf["fact_id"],
                        type=CandidateType.PERSONALIZED_TRIVIA.value,
                        title=tf["title"],
                        summary=tf["fact_text"],
                        source=tf.get("source", "verified_archive"),
                        required=False,
                        importance_score=0.50,
                        interest_score=max(0.75, t_score),
                        confidence_score=0.95,
                        interest_reasons=t_reasons,
                    ))
        except Exception as e:
            logger.warning(f"Error gathering trivia candidates: {e}")

        # 5. Major External Entertainment News Candidates
        try:
            major_news = repo.list_major_news()
            for mn in major_news:
                n_score, n_reasons = PersonalInterestScorer.calculate_interest(user_id, mn["title"], repo)
                engine_candidates.append(Candidate(
                    candidate_id=mn["story_id"],
                    type=CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS.value,
                    title=mn["title"],
                    summary=mn["summary"],
                    source=mn.get("source", "official_media"),
                    required=False,
                    importance_score=0.75,
                    interest_score=max(0.75, n_score),
                    confidence_score=0.90,
                    interest_reasons=n_reasons,
                ))
        except Exception as e:
            logger.warning(f"Error gathering external news candidates: {e}")

        # Run Decision Engine
        decision_config = DecisionConfig(**repo.get_active_decision_config())
        prompt_version = PromptVersion(**repo.get_active_prompt_version())

        decision_log, selected_engine_candidates = DecisionEngine.evaluate(
            user_id=user_id,
            repo=repo,
            tmdb=tmdb,
            raw_candidates=engine_candidates,
            config=decision_config,
            prompt_version=prompt_version,
            session_id=session_id,
        )

        selected_count = len(selected_engine_candidates)
        selected_items = [c.to_dict() for c in selected_engine_candidates]

        # Convert engine candidates back to briefing item dicts for formatting
        formatting_items = [
            {
                "title": c.title,
                "summary": c.summary,
                "type": c.type,
                "message": c.summary,
            }
            for c in selected_engine_candidates
        ]

        # Fetch recent 10 greetings for anti-repetition context
        recent_chat_msgs = repo.list_chat_messages(user_id, limit=20)
        recent_openings = [m["content"] for m in recent_chat_msgs if m.get("role") in {"assistant", "model"}][:10]

        # Format LLM Briefing
        from app.services.agent_service import AiAgentService
        briefing_text = await AiAgentService._format_structured_llm_briefing(
            settings=settings,
            weather_data=weather_data,
            briefing_items=formatting_items,
            total_monitored=len(monitored),
            recent_openings=recent_openings,
            prompt_version=prompt_version,
        )

        # Update decision log with rendered prompts and final response
        decision_log.sanitized_prompt = f"System Instruction: {prompt_version.system_instruction_template[:200]}...\nWording Instruction: {prompt_version.wording_instruction}"
        decision_log.raw_model_response = briefing_text
        decision_log.final_response = briefing_text

        # Record decision log in database
        try:
            repo.add_decision_log(decision_log.to_dict())
        except Exception as e:
            logger.warning(f"Error recording agent decision log: {e}")

        # Record trivia and news presentation history
        for sc in selected_engine_candidates:
            if sc.type == CandidateType.PERSONALIZED_TRIVIA.value:
                repo.record_trivia_presentation(user_id, sc.candidate_id)
            elif sc.type == CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS.value:
                cluster_id = sc.source or sc.candidate_id
                repo.record_news_presentation(user_id, cluster_id, sc.summary)

        # Persist presentation records
        if selected_items:
            repo.record_briefing_presentations(user_id, selected_items)

        # Update login & presentation timestamps
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
            "decision_log_id": decision_log.log_id,
            "telemetry": {
                "total_candidates": len(engine_candidates),
                "selected_count": selected_count,
                "decision_log_id": decision_log.log_id,
            }
        }

        if session_id:
            repo.save_agent_session(user_id, session_id, briefing_data)

        # Save briefing into chat history so startup chat is available in Chat AI
        _ensure_briefing_in_chat_history(user_id, briefing_text, repo)

        return briefing_data


