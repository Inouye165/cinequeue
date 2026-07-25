import asyncio
import hashlib
import logging
import re
import time
from typing import Any

from app.decision_models import (
    STARTUP_BRIEFING_CACHE_VERSION,
    StartupRunContext,
    build_stable_daily_cache_key,
    resolve_user_local_date,
    set_current_run_context,
)
from app.repository import WatchlistRepository
from app.services.agent_service import validate_fallback_greeting
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


def _filter_unpresented_candidates(user_id: str, candidate_list: list[dict[str, Any]], repo: WatchlistRepository) -> list[dict[str, Any]]:
    if not candidate_list:
        return []
    try:
        presented_dict = repo.get_presented_briefing_keys(user_id)
        unpresented = []
        for cand in candidate_list:
            key = cand.get("item_key") or cand.get("candidate_id") or cand.get("story_cluster_id") or f"item_{cand.get('title', 'gen')}"
            if key not in presented_dict:
                unpresented.append(cand)
        return unpresented
    except Exception as e:
        logger.warning(f"Error filtering unpresented candidates: {e}")
        return candidate_list


class BriefingService:
    @staticmethod
    async def evaluate_startup_briefing(
        user_id: str,
        repo: WatchlistRepository,
        tmdb: TmdbClient | None,
        session_id: str | None = None,
        force_refresh: bool = False,
        briefing_run_id: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate or retrieve a startup briefing following the strict daily briefing contract."""
        import uuid
        brun_id = briefing_run_id or f"run_{uuid.uuid4().hex[:12]}"
        req_id = request_id or f"req_{uuid.uuid4().hex[:12]}"

        run_ctx = StartupRunContext(
            briefing_run_id=brun_id,
            request_id=req_id,
            session_id=session_id,
            user_id=user_id,
            force_refresh=force_refresh,
            refresh_reason="manual" if force_refresh else "daily_startup",
        )
        token = set_current_run_context(run_ctx)
        run_ctx.add_timeline_event("run_started", "completed")

        now_iso = repo.utc_now_iso()

        # Step 1: Load settings
        settings = repo.get_agent_settings(user_id)
        run_ctx.add_timeline_event("settings_load", "completed")
        if not settings.get("notify_on_login", True):
            summary = run_ctx.finalize_run(result_source="disabled", final_status="skipped")
            try:
                repo.add_decision_log(summary)
            except Exception:
                pass
            set_current_run_context(None)
            return {"enabled": False, "briefing": None, "updates": []}

        # Step 2: Resolve user timezone & stable daily cache key
        user_tz = settings.get("timezone") or settings.get("user_timezone")
        local_date_str, resolved_tz, tz_src, tz_err = resolve_user_local_date(user_tz)
        run_ctx.user_timezone = resolved_tz
        run_ctx.timezone_resolution_source = tz_src
        run_ctx.timezone_resolution_error = tz_err
        run_ctx.resolved_local_date = local_date_str
        stable_cache_key = build_stable_daily_cache_key(user_id, local_date_str, version=STARTUP_BRIEFING_CACHE_VERSION)
        run_ctx.daily_cache_key = stable_cache_key

        existing_completed_record = None

        # Step 3: Persistent Daily Cache Lookup FIRST (before weather, TMDB, news, or candidate scoring)
        if not force_refresh:
            start_lookup = time.perf_counter()
            cached_daily = repo.get_daily_greeting(user_id, stable_cache_key)
            lookup_dur_ms = round((time.perf_counter() - start_lookup) * 1000, 2)

            if cached_daily:
                status = cached_daily.get("status", "completed")
                b_text = cached_daily.get("briefing") or cached_daily.get("briefing_text") or ""

                if status == "completed" and validate_fallback_greeting(b_text):
                    logger.info(f"[Briefing] Persistent daily cache HIT for user={user_id}, key={stable_cache_key}")
                    run_ctx.daily_cache_result = "hit"
                    run_ctx.add_timeline_event(
                        stage="persistent_daily_cache_lookup",
                        status="hit",
                        duration_ms=lookup_dur_ms,
                        result={"daily_cache_key": stable_cache_key},
                    )
                    _ensure_briefing_in_chat_history(user_id, b_text, repo)

                    res_src = cached_daily.get("result_source", "persistent_daily_cache")
                    run_ctx.served_from = "persistent_daily_cache"
                    run_ctx.content_origin = cached_daily.get("content_origin") or res_src
                    presented_keys_count = len(repo.get_presented_briefing_keys(user_id))
                    run_ctx.already_presented_count = max(cached_daily.get("already_presented_count", 0), presented_keys_count)
                    run_ctx.selected_count = len(cached_daily.get("selected_candidates", []))
                    summary = run_ctx.finalize_run(
                        result_source=res_src,
                        final_status="success",
                        response_text=b_text
                    )
                    try:
                        repo.add_decision_log(summary)
                    except Exception as e:
                        logger.warning(f"Error recording run summary: {e}")
                    set_current_run_context(None)

                    unpresented = _filter_unpresented_candidates(user_id, cached_daily.get("selected_candidates", []), repo)
                    return {
                        "enabled": True,
                        "briefing": b_text,
                        "updates_count": len(unpresented),
                        "updates": unpresented,
                        "telemetry": summary,
                        "briefing_run_id": brun_id,
                        "request_id": req_id,
                        "cached": True,
                    }

                elif status == "generating":
                    run_ctx.daily_cache_result = "generating"
                    run_ctx.generation_claim_result = "not_acquired"
                    poll_start = time.perf_counter()
                    completed_record = None

                    for _ in range(12):  # Poll up to 2.4s (12 x 200ms)
                        await asyncio.sleep(0.2)
                        check_rec = repo.get_daily_greeting(user_id, stable_cache_key)
                        if check_rec and check_rec.get("status") == "completed":
                            completed_record = check_rec
                            break

                    poll_dur_ms = round((time.perf_counter() - poll_start) * 1000, 2)
                    run_ctx.generation_wait_duration_ms = poll_dur_ms

                    if completed_record:
                        b_text = completed_record.get("briefing") or completed_record.get("briefing_text") or ""
                        run_ctx.generation_wait_outcome = "completed"
                        run_ctx.add_timeline_event(
                            stage="persistent_daily_cache_lookup",
                            status="hit_after_wait",
                            duration_ms=poll_dur_ms,
                            result={"daily_cache_key": stable_cache_key, "wait_duration_ms": poll_dur_ms},
                        )
                        _ensure_briefing_in_chat_history(user_id, b_text, repo)
                        res_src = completed_record.get("result_source", "persistent_daily_cache")
                        run_ctx.served_from = "persistent_daily_cache"
                        run_ctx.content_origin = completed_record.get("content_origin") or res_src
                        summary = run_ctx.finalize_run(
                            result_source=res_src,
                            final_status="success",
                            response_text=b_text
                        )
                        try:
                            repo.add_decision_log(summary)
                        except Exception:
                            pass
                        set_current_run_context(None)
                        return {
                            "enabled": True,
                            "briefing": b_text,
                            "updates_count": len(completed_record.get("selected_candidates", [])),
                            "updates": completed_record.get("selected_candidates", []),
                            "telemetry": summary,
                            "briefing_run_id": brun_id,
                            "request_id": req_id,
                            "cached": True,
                        }
                    else:
                        run_ctx.generation_wait_outcome = "timeout"
                        # Return previously completed stale greeting or deterministic local greeting
                        stale_text = (cached_daily.get("briefing") or cached_daily.get("briefing_text")) if cached_daily else None
                        final_text = stale_text or "Welcome back! Everything is up to date on your monitored queue today."
                        res_src = cached_daily.get("result_source", "stale_cache_fallback") if stale_text else "local_rule_fallback"
                        run_ctx.served_from = "persistent_daily_cache" if stale_text else "local_fallback"
                        run_ctx.content_origin = res_src
                        _ensure_briefing_in_chat_history(user_id, final_text, repo)
                        summary = run_ctx.finalize_run(result_source=res_src, final_status="success", response_text=final_text)
                        try:
                            repo.add_decision_log(summary)
                        except Exception:
                            pass
                        set_current_run_context(None)
                        return {
                            "enabled": True,
                            "briefing": final_text,
                            "updates_count": len(cached_daily.get("selected_candidates", [])) if cached_daily else 0,
                            "updates": cached_daily.get("selected_candidates", []) if cached_daily else [],
                            "telemetry": summary,
                            "briefing_run_id": brun_id,
                            "request_id": req_id,
                            "cached": True,
                        }
            else:
                run_ctx.daily_cache_result = "miss"
                run_ctx.add_timeline_event(
                    stage="persistent_daily_cache_lookup",
                    status="miss",
                    duration_ms=lookup_dur_ms,
                    result={"daily_cache_key": stable_cache_key},
                )
        else:
            # Save existing completed record in case manual refresh generation fails
            existing_completed_record = repo.get_daily_greeting(user_id, stable_cache_key)

        # Step 4: Atomic Generation Claim
        acquired, existing_claim = repo.claim_daily_greeting_generation(user_id, stable_cache_key, lease_seconds=30, force_refresh=force_refresh)
        if acquired:
            run_ctx.generation_claim_result = "acquired"
            run_ctx.add_timeline_event("generation_claim", "acquired", result={"daily_cache_key": stable_cache_key})
        else:
            run_ctx.generation_claim_result = "not_acquired"
            run_ctx.add_timeline_event("generation_claim", "not_acquired", result={"daily_cache_key": stable_cache_key})
            b_text = (existing_claim.get("briefing") or existing_claim.get("briefing_text")) if existing_claim else None
            res_src = existing_claim.get("result_source", "stale_cache_fallback") if (existing_claim and b_text) else "local_rule_fallback"
            run_ctx.served_from = "persistent_daily_cache" if (existing_claim and b_text) else "local_fallback"
            run_ctx.content_origin = res_src
            if not b_text:
                b_text = "Welcome back! Everything is up to date on your monitored queue today."
            _ensure_briefing_in_chat_history(user_id, b_text, repo)
            summary = run_ctx.finalize_run(
                result_source=res_src,
                final_status="success",
                response_text=b_text
            )
            try:
                repo.add_decision_log(summary)
            except Exception:
                pass
            set_current_run_context(None)
            return {
                "enabled": True,
                "briefing": b_text,
                "updates_count": len(existing_claim.get("selected_candidates", [])) if existing_claim else 0,
                "updates": existing_claim.get("selected_candidates", []) if existing_claim else [],
                "telemetry": summary,
                "briefing_run_id": brun_id,
                "request_id": req_id,
                "cached": True,
            }

        # Step 5: Data Collection & Generation (Protected by exception handler)
        try:
            briefing_state = repo.get_user_briefing_state(user_id)
            previous_login_at = briefing_state.get("previous_login_at")
            previous_briefing_presented_at = briefing_state.get("previous_briefing_presented_at")

            items = repo.list_items(user_id)
            monitored = [
                item for item in items
                if not item.get("is_owned") and (item.get("status") in {"following", "queue", "watchlist"} or not item.get("status"))
            ]

            presented_keys = repo.get_presented_briefing_keys(user_id)
            candidate_items: list[dict[str, Any]] = []
            already_presented_count = 0

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
                        if key in presented_keys:
                            already_presented_count += 1
                        else:
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
                        if key in presented_keys:
                            already_presented_count += 1
                        else:
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
                        if key in presented_keys:
                            already_presented_count += 1
                        else:
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
                            if key in presented_keys:
                                already_presented_count += 1
                            else:
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
                            if key in presented_keys:
                                already_presented_count += 1
                            else:
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

                if c_type in {"newly_available", "imminent_release", "releasing_today", "releasing_tomorrow", "released_recently", "upcoming_release", "price_drop", "free_streaming", "memory_recall"}:
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
            selected_items = []
            for c in selected_engine_candidates:
                d = c.to_dict()
                d["item_key"] = c.candidate_id
                selected_items.append(d)

            # Convert engine candidates back to briefing item dicts for formatting
            formatting_items = [
                {
                    "item_key": c.candidate_id,
                    "candidate_id": c.candidate_id,
                    "title": c.title,
                    "summary": c.summary,
                    "type": c.type,
                    "message": c.summary,
                    "category": c.type,
                }
                for c in selected_engine_candidates
            ]

            recent_chat_msgs = repo.list_chat_messages(user_id, limit=20)
            recent_openings = []
            for m in recent_chat_msgs:
                if m.get("role") in {"assistant", "model"}:
                    content = (m.get("content") or "").strip()
                    if content:
                        first_sentence = content.split("\n")[0][:120]
                        recent_openings.append(first_sentence)
                    if len(recent_openings) >= 5:
                        break

            # Format LLM Briefing
            from app.services.agent_service import AiAgentService
            briefing_text = await AiAgentService._format_structured_llm_briefing(
                settings=settings,
                weather_data=weather_data,
                briefing_items=formatting_items,
                total_monitored=len(monitored),
                recent_openings=recent_openings,
                prompt_version=prompt_version,
                user_id=user_id,
                repo=repo,
                force_refresh=force_refresh,
            )

            # Update decision log with rendered prompt preview
            decision_log.sanitized_prompt = f"System Instruction: {prompt_version.system_instruction_template[:200]}...\nWording Instruction: {prompt_version.wording_instruction}"

            # Record candidate decision log in database
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

            # Update telemetry context
            run_ctx.already_presented_count = already_presented_count + len(decision_log.cooldowns_applied) + len(decision_log.excluded_candidates)
            run_ctx.selected_count = selected_count

            briefing_data = {
                "enabled": True,
                "briefing": briefing_text,
                "updates_count": selected_count,
                "updates": formatting_items,
                "personality_preset": settings.get("personality_preset", "cinephile"),
                "location": location,
                "weather": weather_data.to_dict() if weather_data else None,
                "previous_login_at": previous_login_at,
                "previous_briefing_presented_at": previous_briefing_presented_at,
                "decision_log_id": decision_log.log_id,
                "telemetry": {
                    "total_candidates": len(engine_candidates),
                    "selected_count": selected_count,
                    "already_presented_count": run_ctx.already_presented_count,
                    "decision_log_id": decision_log.log_id,
                    "briefing_run_id": brun_id,
                    "request_id": req_id,
                }
            }

            if session_id:
                repo.save_agent_session(user_id, session_id, briefing_data)
                run_ctx.add_timeline_event("session_cache_write", "completed")

            # Save briefing into chat history so startup chat is available in Chat AI
            _ensure_briefing_in_chat_history(user_id, briefing_text, repo)

            # Finalize run context and persist startup_briefing_run_completed summary
            res_source = run_ctx.result_source if run_ctx.result_source != "error" else "local_rule_fallback"

            # Save complete daily record to persistent daily cache
            daily_record = {
                "cache_key": stable_cache_key,
                "cache_version": STARTUP_BRIEFING_CACHE_VERSION,
                "user_id": user_id,
                "user_timezone": run_ctx.user_timezone,
                "local_date": run_ctx.resolved_local_date,
                "status": "completed",
                "generation_owner": req_id,
                "generation_lease_expires_at": None,
                "briefing": briefing_text,
                "briefing_text": briefing_text,
                "result_source": res_source,
                "selected_candidates": formatting_items,
                "weather_snapshot": weather_data.to_dict() if weather_data else None,
                "release_updates": [it for it in formatting_items if any(k in str(it.get("type", "")) for k in ["release", "available"])],
                "watch_provider_updates": [it for it in formatting_items if any(k in str(it.get("type", "")) for k in ["price_drop", "streaming"])],
                "news_updates": [it for it in formatting_items if "news" in str(it.get("type", ""))],
                "already_presented_count": run_ctx.already_presented_count,
                "generated_at": repo.utc_now_iso(),
                "completed_at": repo.utc_now_iso(),
                "model_used": run_ctx.final_model,
                "gemini_success": res_source == "fresh_gemini",
                "fallback_trigger": run_ctx.fallback_trigger,
                "final_failure_reason": run_ctx.final_failure_reason,
                "refresh_reason": "manual" if force_refresh else "daily_startup",
            }
            try:
                repo.save_daily_greeting(user_id, stable_cache_key, daily_record)
                run_ctx.add_timeline_event("persistent_daily_cache_write", "completed", result={"daily_cache_key": stable_cache_key})
            except Exception as e:
                logger.warning(f"Error saving final daily greeting record: {e}")

            run_ctx.served_from = "fresh_generation"
            summary = run_ctx.finalize_run(result_source=res_source, final_status="success", response_text=briefing_text)
            briefing_data["telemetry"] = summary
            try:
                repo.add_decision_log(summary)
            except Exception as e:
                logger.warning(f"Error recording startup run summary: {e}")

            set_current_run_context(None)
            return briefing_data

        except Exception as err:
            logger.warning(f"Error during briefing generation for user {user_id}: {err}")

            if existing_completed_record and existing_completed_record.get("status") == "completed":
                b_text = existing_completed_record.get("briefing") or existing_completed_record.get("briefing_text") or ""
                _ensure_briefing_in_chat_history(user_id, b_text, repo)
                summary = run_ctx.finalize_run(
                    result_source=existing_completed_record.get("result_source", "persistent_daily_cache"),
                    final_status="success",
                    response_text=b_text
                )
                try:
                    repo.add_decision_log(summary)
                except Exception:
                    pass
                set_current_run_context(None)
                return {
                    "enabled": True,
                    "briefing": b_text,
                    "updates_count": len(existing_completed_record.get("selected_candidates", [])),
                    "updates": existing_completed_record.get("selected_candidates", []),
                    "telemetry": summary,
                    "briefing_run_id": brun_id,
                    "request_id": req_id,
                    "cached": True,
                }

            from app.services.agent_service import AiAgentService
            fallback_text = AiAgentService._generate_dynamic_human_briefing(
                settings=settings,
                location=settings.get("location", "").strip(),
                weather_json=None,
                briefing_items=[],
                time_of_day="morning",
            )
            daily_record = {
                "cache_key": stable_cache_key,
                "cache_version": STARTUP_BRIEFING_CACHE_VERSION,
                "user_id": user_id,
                "user_timezone": run_ctx.user_timezone,
                "local_date": run_ctx.resolved_local_date,
                "status": "completed",
                "generation_owner": req_id,
                "generation_lease_expires_at": None,
                "briefing": fallback_text,
                "briefing_text": fallback_text,
                "result_source": "local_rule_fallback",
                "selected_candidates": [],
                "generated_at": repo.utc_now_iso(),
                "completed_at": repo.utc_now_iso(),
                "refresh_reason": "manual" if force_refresh else "daily_startup",
            }
            try:
                repo.save_daily_greeting(user_id, stable_cache_key, daily_record)
            except Exception:
                pass
            summary = run_ctx.finalize_run(result_source="local_rule_fallback", final_status="success", response_text=fallback_text)
            try:
                repo.add_decision_log(summary)
            except Exception:
                pass
            set_current_run_context(None)
            return {
                "enabled": True,
                "briefing": fallback_text,
                "updates_count": 0,
                "updates": [],
                "telemetry": summary,
                "briefing_run_id": brun_id,
                "request_id": req_id,
            }
