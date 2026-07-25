import datetime
import json
import logging
import random
import uuid
from typing import Any, Optional

from app.decision_models import (
    Candidate,
    CandidateType,
    DecisionConfig,
    DecisionLog,
    PromptVersion,
)
from app.repository import WatchlistRepository
from app.services.tmdb import TmdbClient

logger = logging.getLogger(__name__)


class RandomSelectionService:
    def __init__(self, seed: Optional[Any] = None):
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self.seed_used = seed

    def random(self) -> float:
        return self._rng.random()

    def choice(self, seq: list[Any]) -> Any:
        return self._rng.choice(seq)

    def choices(self, population: list[Any], weights: list[float], k: int = 1) -> list[Any]:
        return self._rng.choices(population, weights=weights, k=k)


class PersonalInterestScorer:
    @staticmethod
    def calculate_interest(
        user_id: str,
        title: str,
        repo: WatchlistRepository,
        tmdb_id: Optional[int] = None,
        media_type: str = "movie",
        category_tags: Optional[list[str]] = None,
    ) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 0.40  # Base line interest

        rated_movies = repo.list_rated_movies(user_id)
        watchlist_items = repo.list_items(user_id)
        query_memory = repo.list_query_memories(user_id, limit=20) if hasattr(repo, "list_query_memories") else []


        title_lower = title.lower()

        # Signal 1: Highly rated titles or franchise match
        high_rated = [m for m in rated_movies if (m.get("rating") or 0) >= 4]
        for hr in high_rated:
            hr_title = hr.get("title", "").lower()
            if hr_title in title_lower or title_lower in hr_title:
                score += 0.35
                reasons.append(f"User rated '{hr['title']}' {hr['rating']} stars")
                break
            # Franchise / universe match (e.g. Marvel, Spider-Man, Star Wars, Batman)
            franchises = ["spider-man", "marvel", "star wars", "batman", "avengers", "dune", "game of thrones", "lord of the rings"]
            for f in franchises:
                if f in hr_title and f in title_lower:
                    score += 0.30
                    reasons.append(f"Strong franchise connection to highly-rated '{hr['title']}' ({f.title()})")
                    break

        # Signal 2: Monitored watchlist items
        monitored_matches = [i for i in watchlist_items if title_lower in i.get("title", "").lower()]
        if monitored_matches:
            score += 0.25
            reasons.append(f"Title '{title}' is currently monitored in user's queue")

        # Signal 3: Recent query memory / searches
        search_matches = [q for q in query_memory if title_lower in q.get("query_text", "").lower() or title_lower in q.get("title", "").lower()]
        if search_matches:
            score += 0.20
            reasons.append(f"User recently searched or asked about '{title}'")

        # Fallback explanation if general match
        if not reasons:
            if high_rated:
                reasons.append(f"General alignment with user's {len(high_rated)} highly rated movies")
            else:
                reasons.append("Default baseline interest estimate")

        final_score = round(max(0.0, min(1.0, score)), 3)
        return final_score, reasons


class DecisionEngine:
    @staticmethod
    def evaluate(
        user_id: str,
        repo: WatchlistRepository,
        tmdb: Optional[TmdbClient],
        raw_candidates: list[Candidate],
        config: Optional[DecisionConfig] = None,
        prompt_version: Optional[PromptVersion] = None,
        random_seed: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> tuple[DecisionLog, list[Candidate]]:
        """Evaluate candidates, apply rules/cooldowns, and select final items using reproducible random selection."""
        cfg = config or DecisionConfig(**repo.get_active_decision_config())
        prompt_ver = prompt_version or PromptVersion(**repo.get_active_prompt_version())
        rng = RandomSelectionService(seed=random_seed)

        start_time = datetime.datetime.now(datetime.timezone.utc)
        log_id = f"dec_{uuid.uuid4().hex[:12]}"

        # 1. Fetch user presentation state & login history for cooldowns
        briefing_state = repo.get_user_briefing_state(user_id)
        prev_login_at = briefing_state.get("previous_login_at")
        prev_briefing_at = briefing_state.get("previous_briefing_presented_at")

        cooldowns_applied: list[str] = []
        random_rolls: dict[str, Any] = {}

        # 2. Evaluate eligibility & scores for all candidates
        required_candidates: list[Candidate] = []
        optional_candidates: list[Candidate] = []
        excluded_candidates: list[Candidate] = []

        now_dt = datetime.datetime.now(datetime.timezone.utc)

        # Check consecutive login restriction
        is_consecutive_login = False
        if prev_briefing_at:
            try:
                prev_dt = datetime.datetime.fromisoformat(prev_briefing_at)
                if prev_dt.tzinfo is None:
                    prev_dt = prev_dt.replace(tzinfo=datetime.timezone.utc)
                hours_since = (now_dt - prev_dt).total_seconds() / 3600.0
                if hours_since < 12.0:
                    is_consecutive_login = True
            except Exception:
                pass

        for c in raw_candidates:
            c.calculate_combined_score()

            # Rule: Severe Weather is mandatory
            if c.type == CandidateType.WEATHER_ALERT:
                c.required = True

            # Mandatory items: check requirements
            if c.required:
                c.eligible = True
                c.exclusion_reason = None
                required_candidates.append(c)
                continue

            # Optional items eligibility evaluation
            exclusion_reasons = []

            # Check toggles
            if not cfg.optional_item_enabled:
                exclusion_reasons.append("Optional content disabled in decision config")
            elif c.type == CandidateType.WEATHER_VIEWING_CONNECTION and not cfg.weather_enabled:
                exclusion_reasons.append("Weather connection content disabled")
            elif c.type == CandidateType.PERSONALIZED_TRIVIA and not cfg.trivia_enabled:
                exclusion_reasons.append("Trivia content disabled")
            elif c.type == CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS and not cfg.external_news_enabled:
                exclusion_reasons.append("External news content disabled")
            elif c.type == CandidateType.PERSONALIZED_RECOMMENDATION and not cfg.recommendations_enabled:
                exclusion_reasons.append("Recommendations content disabled")

            # Check minimum scores
            if c.interest_score < cfg.minimum_interest_score:
                exclusion_reasons.append(f"Interest score {c.interest_score} below minimum threshold {cfg.minimum_interest_score}")
            if c.confidence_score < cfg.minimum_confidence_score:
                exclusion_reasons.append(f"Confidence score {c.confidence_score} below minimum threshold {cfg.minimum_confidence_score}")
            if c.combined_score < cfg.minimum_combined_score:
                exclusion_reasons.append(f"Combined score {c.combined_score} below minimum threshold {cfg.minimum_combined_score}")

            # Consecutive login restriction
            if is_consecutive_login and cfg.prevent_optional_items_on_consecutive_logins:
                exclusion_reasons.append("Optional items restricted on consecutive logins (<12h)")
                cooldowns_applied.append("consecutive_login_restriction")

            # Trivia deduplication & cooldown
            if c.type == CandidateType.PERSONALIZED_TRIVIA:
                if repo.is_trivia_presented(user_id, c.candidate_id) and cfg.same_trivia_never_repeat:
                    exclusion_reasons.append("Trivia fact was previously shown to user")
                    cooldowns_applied.append(f"trivia_duplicate:{c.candidate_id}")

            # News deduplication & cooldown
            if c.type == CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS:
                cluster_id = c.source or c.candidate_id
                news_pres = repo.get_news_presentation(user_id, cluster_id)
                if news_pres:
                    if cfg.same_news_story_repeat_only_if_changed and news_pres.get("content_fingerprint") == c.summary:
                        exclusion_reasons.append("News story already shown without material change")
                        cooldowns_applied.append(f"news_duplicate:{cluster_id}")

            # Ordinary weather cooldown check
            if c.type == CandidateType.WEATHER_VIEWING_CONNECTION:
                if prev_briefing_at:
                    try:
                        p_dt = datetime.datetime.fromisoformat(prev_briefing_at)
                        if p_dt.tzinfo is None:
                            p_dt = p_dt.replace(tzinfo=datetime.timezone.utc)
                        h_diff = (now_dt - p_dt).total_seconds() / 3600.0
                        if h_diff < cfg.ordinary_weather_cooldown_hours:
                            exclusion_reasons.append(f"Ordinary weather in cooldown ({round(h_diff, 1)}h < {cfg.ordinary_weather_cooldown_hours}h)")
                            cooldowns_applied.append("ordinary_weather_cooldown")
                    except Exception:
                        pass

            if exclusion_reasons:
                c.eligible = False
                c.exclusion_reason = "; ".join(exclusion_reasons)
                excluded_candidates.append(c)
            else:
                c.eligible = True
                c.exclusion_reason = None
                optional_candidates.append(c)

        # 3. Select final candidates
        selected_candidates: list[Candidate] = list(required_candidates)

        # Assign probability weight per type
        type_weights = {
            CandidateType.WEATHER_VIEWING_CONNECTION.value: cfg.weather_connection_probability,
            CandidateType.PERSONALIZED_TRIVIA.value: cfg.trivia_probability,
            CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS.value: cfg.external_news_probability,
            CandidateType.PERSONALIZED_RECOMMENDATION.value: cfg.recommendation_probability,
            CandidateType.STREAMING_ARRIVAL.value: 0.15,
            CandidateType.PRICE_DROP.value: 0.15,
        }

        # Optional Slot Roll
        if optional_candidates and cfg.optional_item_enabled:
            slot_roll = rng.random()
            random_rolls["optional_slot_roll"] = round(slot_roll, 4)
            random_rolls["optional_slot_threshold"] = cfg.optional_item_base_probability

            if slot_roll <= cfg.optional_item_base_probability:
                # Weighted candidate selection
                weights = [type_weights.get(c.type, 0.10) * c.combined_score for c in optional_candidates]

                if sum(weights) > 0:
                    chosen = rng.choices(optional_candidates, weights=weights, k=min(1, cfg.maximum_optional_items))
                    for ch in chosen:
                        ch.selected = True
                        selected_candidates.append(ch)
                        random_rolls[f"selected_candidate_{ch.candidate_id}_roll"] = "selected_via_weighted_roll"

        # Mark required candidates as selected
        for req in required_candidates:
            req.selected = True

        # Generate Human-Readable Summaries
        explanations = []
        if selected_candidates:
            for sc in selected_candidates:
                if sc.required:
                    explanations.append(f"Selected MANDATORY update '{sc.title}' ({sc.type}): {sc.summary}")
                else:
                    explanations.append(
                        f"Selected optional candidate '{sc.title}' ({sc.type}) because combined score was {sc.combined_score} "
                        f"(interest={sc.interest_score}), optional slot roll ({random_rolls.get('optional_slot_roll')}) <= {cfg.optional_item_base_probability}, "
                        f"and cooldowns passed."
                    )
        else:
            slot_roll_str = f" (slot roll {random_rolls.get('optional_slot_roll')} > {cfg.optional_item_base_probability})" if "optional_slot_roll" in random_rolls else ""
            explanations.append(f"Selected NO optional items{slot_roll_str}. Returning brief standard greeting.")

        selection_summary = "\n".join(explanations)

        # Candidate signature calculation
        import hashlib, json
        all_titles = sorted([c.title for c in raw_candidates if c.title])
        cand_sig = hashlib.md5(json.dumps(all_titles).encode("utf-8")).hexdigest()[:8]

        # 4. Construct DecisionLog record
        duration_ms = round((datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds() * 1000.0, 2)

        from app.decision_models import get_current_run_context
        run_ctx = get_current_run_context()
        if run_ctx:
            run_ctx.candidate_signature = cand_sig
            run_ctx.add_timeline_event(
                stage="candidate_decision",
                status="completed",
                duration_ms=duration_ms,
                result={
                    "selected_count": len(selected_candidates),
                    "candidate_signature": cand_sig,
                },
            )

        log = DecisionLog(
            log_id=log_id,
            event_type="startup_briefing_candidate_decision",
            telemetry_version=2,
            timestamp=start_time.isoformat(),
            user_id=user_id,
            session_id=session_id,
            briefing_run_id=run_ctx.briefing_run_id if run_ctx else None,
            request_id=run_ctx.request_id if run_ctx else None,
            model_requested="gemini-3.6-flash",
            model_used=None,
            gemini_called=False,
            fallback_used=False,
            fallback_reason=None,
            decision_config_version=cfg.version,
            prompt_version=prompt_ver.version,
            required_candidates=[c.to_dict() for c in required_candidates],
            optional_candidates=[c.to_dict() for c in optional_candidates],
            selected_candidates=[c.to_dict() for c in selected_candidates],
            excluded_candidates=[c.to_dict() for c in excluded_candidates],
            random_rolls=random_rolls,
            cooldowns_applied=cooldowns_applied,
            candidate_count_required=len(required_candidates),
            candidate_count_optional=len(optional_candidates),
            candidate_count_selected=len(selected_candidates),
            candidate_count_excluded=len(excluded_candidates),
            candidate_signature=cand_sig,
            decision_duration_ms=duration_ms,
            selection_summary=selection_summary,
            raw_model_response="",
            final_response="",
            request_duration_ms=duration_ms,
        )

        return log, selected_candidates
