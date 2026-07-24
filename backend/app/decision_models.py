import os
import re
import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional
from zoneinfo import ZoneInfo

STARTUP_BRIEFING_CACHE_VERSION = 2
DEFAULT_USER_TIMEZONE = "America/Los_Angeles"


def resolve_user_local_date(user_timezone_str: str | None = None, now_dt: datetime | None = None) -> tuple[str, str]:
    """Resolve the user's local date (YYYY-MM-DD) based on their configured timezone.
    
    Returns tuple of (local_date_str, resolved_timezone_name).
    """
    tz_to_use = (user_timezone_str or "").strip()
    if not tz_to_use:
        tz_to_use = DEFAULT_USER_TIMEZONE

    base_dt = now_dt if now_dt is not None else datetime.now(timezone.utc)
    if base_dt.tzinfo is None:
        base_dt = base_dt.replace(tzinfo=timezone.utc)

    try:
        zi = ZoneInfo(tz_to_use)
        local_date = base_dt.astimezone(zi).date().isoformat()
        return local_date, tz_to_use
    except Exception:
        try:
            zi = ZoneInfo(DEFAULT_USER_TIMEZONE)
            local_date = base_dt.astimezone(zi).date().isoformat()
            return local_date, DEFAULT_USER_TIMEZONE
        except Exception:
            utc_date = base_dt.astimezone(timezone.utc).date().isoformat()
            return utc_date, "UTC"


def build_stable_daily_cache_key(user_id: str, local_date_str: str, version: int = STARTUP_BRIEFING_CACHE_VERSION) -> str:
    """Construct a stable, deterministic daily cache key containing only identity, local date, and cache version."""
    return f"startup_briefing:{user_id}:{local_date_str}:v{version}"


class CandidateType(str, Enum):
    MONITORED_TITLE_URGENT_UPDATE = "monitored_title_urgent_update"
    MONITORED_TITLE_RELEASE = "monitored_title_release"
    STREAMING_ARRIVAL = "streaming_arrival"
    PRICE_DROP = "price_drop"
    WEATHER_ALERT = "weather_alert"
    WEATHER_VIEWING_CONNECTION = "weather_viewing_connection"
    PERSONALIZED_TRIVIA = "personalized_trivia"
    MAJOR_EXTERNAL_ENTERTAINMENT_NEWS = "major_external_entertainment_news"
    PERSONALIZED_RECOMMENDATION = "personalized_recommendation"


@dataclass
class CandidateScore:
    importance: float = 0.5
    interest: float = 0.5
    novelty: float = 1.0
    confidence: float = 1.0
    combined: float = 0.5

    def to_dict(self) -> dict[str, float]:
        return {
            "importance": round(self.importance, 3),
            "interest": round(self.interest, 3),
            "novelty": round(self.novelty, 3),
            "confidence": round(self.confidence, 3),
            "combined": round(self.combined, 3),
        }


@dataclass
class Candidate:
    candidate_id: str
    type: str  # CandidateType value
    title: str
    summary: str
    source: str = "system"
    required: bool = False

    importance_score: float = 0.5
    interest_score: float = 0.5
    novelty_score: float = 1.0
    confidence_score: float = 1.0
    combined_score: float = 0.5
    eligible: bool = True
    exclusion_reason: Optional[str] = None
    interest_reasons: list[str] = field(default_factory=list)
    cooldown_status: Optional[str] = None
    random_weight: float = 1.0
    random_roll: Optional[float] = None
    selected: bool = False

    def calculate_combined_score(
        self,
        weights: Optional[dict[str, float]] = None,
    ) -> float:
        w = weights or {
            "importance": 0.35,
            "interest": 0.35,
            "novelty": 0.15,
            "confidence": 0.15,
        }
        raw = (
            self.importance_score * w["importance"]
            + self.interest_score * w["interest"]
            + self.novelty_score * w["novelty"]
            + self.confidence_score * w["confidence"]
        )
        self.combined_score = round(max(0.0, min(1.0, raw)), 3)
        return self.combined_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "type": self.type,
            "title": self.title,
            "summary": self.summary,
            "source": self.source,
            "required": self.required,
            "importance_score": round(self.importance_score, 3),
            "interest_score": round(self.interest_score, 3),
            "novelty_score": round(self.novelty_score, 3),
            "confidence_score": round(self.confidence_score, 3),
            "combined_score": round(self.combined_score, 3),
            "eligible": self.eligible,
            "exclusion_reason": self.exclusion_reason,
            "interest_reasons": self.interest_reasons,
            "cooldown_status": self.cooldown_status,
            "random_weight": round(self.random_weight, 3),
            "random_roll": round(self.random_roll, 3) if self.random_roll is not None else None,
            "selected": self.selected,
        }


@dataclass
class DecisionConfig:
    version: int = 1
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_by: str = "system_default"
    change_note: str = "Initial default configuration"
    optional_item_enabled: bool = True
    optional_item_base_probability: float = 0.20
    weather_connection_probability: float = 0.12
    trivia_probability: float = 0.08
    external_news_probability: float = 0.12
    recommendation_probability: float = 0.10
    minimum_interest_score: float = 0.72
    minimum_confidence_score: float = 0.85
    minimum_combined_score: float = 0.75
    maximum_optional_items: int = 1
    ordinary_weather_cooldown_hours: int = 48
    trivia_cooldown_hours: int = 72
    external_news_cooldown_hours: int = 48
    recommendation_cooldown_hours: int = 72
    same_title_recommendation_cooldown_days: int = 30
    same_trivia_never_repeat: bool = True
    same_news_story_repeat_only_if_changed: bool = True
    prevent_optional_items_on_consecutive_logins: bool = True
    recent_greeting_comparison_count: int = 10
    trivia_enabled: bool = True
    external_news_enabled: bool = True
    weather_enabled: bool = True
    recommendations_enabled: bool = True
    allow_rumors: bool = False
    logging_detail_level: str = "full"

    def validate(self) -> list[str]:
        errors = []
        probs = [
            ("optional_item_base_probability", self.optional_item_base_probability),
            ("weather_connection_probability", self.weather_connection_probability),
            ("trivia_probability", self.trivia_probability),
            ("external_news_probability", self.external_news_probability),
            ("recommendation_probability", self.recommendation_probability),
            ("minimum_interest_score", self.minimum_interest_score),
            ("minimum_confidence_score", self.minimum_confidence_score),
            ("minimum_combined_score", self.minimum_combined_score),
        ]
        for name, val in probs:
            if val < 0.0 or val > 1.0:
                errors.append(f"{name} must be between 0.0 and 1.0 (got {val})")

        cooldowns = [
            ("ordinary_weather_cooldown_hours", self.ordinary_weather_cooldown_hours),
            ("trivia_cooldown_hours", self.trivia_cooldown_hours),
            ("external_news_cooldown_hours", self.external_news_cooldown_hours),
            ("recommendation_cooldown_hours", self.recommendation_cooldown_hours),
            ("same_title_recommendation_cooldown_days", self.same_title_recommendation_cooldown_days),
            ("recent_greeting_comparison_count", self.recent_greeting_comparison_count),
        ]
        for name, val in cooldowns:
            if val < 0:
                errors.append(f"{name} cannot be negative (got {val})")

        if self.maximum_optional_items < 0:
            errors.append(f"maximum_optional_items cannot be negative (got {self.maximum_optional_items})")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_DECISION_CONFIG = DecisionConfig()

DEFAULT_WORDING_INSTRUCTION = (
    "Write a brief, natural startup greeting using only the selected verified facts.\n\n"
    "Lead with required urgent information when present.\n\n"
    "Optional weather, trivia, entertainment news, or recommendations should feel casual and should be omitted when they do not naturally fit.\n\n"
    "It is acceptable to provide only a short greeting when nothing meaningful has changed.\n\n"
    "Do not invent information merely to make the greeting more interesting.\n\n"
    "Do not repeat wording or sentence structures from the recent greetings supplied in the context.\n\n"
    "Do not list application capabilities or end every greeting by asking the user to manage their queue or request a recommendation."
)


@dataclass
class PromptVersion:
    version: int = 1
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_by: str = "system_default"
    change_note: str = "Initial default prompt template"
    system_instruction_template: str = (
        "You are the user's personal CineQueue movie and television assistant. Speak like a knowledgeable, relaxed friend who enjoys discussing entertainment.\n\n"
        "Answer the user's specific question directly before adding related information. Use natural conversational wording. Be warm and occasionally playful, but never force jokes, sarcasm, attitude, or weather references. Do not perform a chatbot personality.\n\n"
        "Do not use canned artificial phrases such as 'my algorithms suggest,' 'another query,' 'not that you asked,' or theatrical sighs. Do not mention being an AI unless directly asked.\n\n"
        "Use supplied account, watchlist, release, provider, news, and conversation data carefully. Only state information supported by the available data or verified tools. Never fabricate release dates, streaming availability, news, or user history.\n\n"
        "When the user asks about one title, remain focused on that title unless another title is directly relevant. When information is unavailable, say so plainly.\n\n"
        "For startup briefings, summarize only useful items that are new, changed, recently available, approaching soon, or urgent. Do not repeat an item merely because it appeared in a previous briefing. Keep startup briefings compact and prioritize the most important information."
    )
    wording_instruction: str = DEFAULT_WORDING_INSTRUCTION

    def validate(self) -> list[str]:
        errors = []
        if not self.system_instruction_template.strip():
            errors.append("System instruction template cannot be empty.")
        if not self.wording_instruction.strip():
            errors.append("Wording instruction cannot be empty.")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_PROMPT_VERSION = PromptVersion()


SECRET_PATTERNS = [
    (r'\?key=[^&\s"\']+', '?key=[REDACTED_API_KEY]'),
    (r'AIzaSy[a-zA-Z0-9_\-]{33}', '[REDACTED_GEMINI_KEY]'),
    (r'Bearer\s+[a-zA-Z0-9_\-\.]+', 'Bearer [REDACTED_TOKEN]'),
    (r'__Host-[a-zA-Z0-9_\-]+=[^;\s]+', '__Host-[REDACTED_COOKIE]'),
]


def scrub_secrets(val: Any) -> Any:
    """Recursively scrub sensitive keys, tokens, and URL parameters from data structures."""
    if isinstance(val, str):
        res = val
        for pat, repl in SECRET_PATTERNS:
            res = re.sub(pat, repl, res)
        return res
    elif isinstance(val, dict):
        cleaned = {}
        for k, v in val.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ["authorization", "api_key", "gemini_api_key", "tmdb_api_key", "cookie", "bearer"]):
                cleaned[k] = "[REDACTED_SECRET]"
            else:
                cleaned[k] = scrub_secrets(v)
        return cleaned
    elif isinstance(val, list):
        return [scrub_secrets(item) for item in val]
    return val


@dataclass
class StartupRunContext:
    briefing_run_id: str
    request_id: str
    session_id: Optional[str]
    user_id: str
    telemetry_version: int = 2
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    start_time_perf: float = field(default_factory=time.perf_counter)
    completed_at: Optional[str] = None
    total_duration_ms: Optional[float] = None
    force_refresh: bool = False
    user_timezone: str = "UTC"
    resolved_local_date: str = field(default_factory=lambda: date.today().isoformat())
    server_date: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    result_source: str = "error"
    final_status: str = "running"
    response_text_length: int = 0
    daily_cache_key: Optional[str] = None
    daily_cache_result: Optional[str] = None
    daily_cache_backend: str = "sqlite"
    candidate_signature: Optional[str] = None
    generation_claim_result: Optional[str] = None
    generation_wait_duration_ms: Optional[float] = None
    generation_wait_outcome: Optional[str] = None
    refresh_reason: Optional[str] = None
    gemini_request_id: Optional[str] = None
    gemini_attempt_count: int = 0
    fallback_attempted: bool = False
    fallback_trigger: Optional[str] = None
    final_failure_reason: Optional[str] = None
    final_model: Optional[str] = None
    already_presented_count: int = 0
    selected_count: int = 0
    ai_diagnostic_detail: str = field(default_factory=lambda: os.getenv("AI_DIAGNOSTIC_DETAIL", "normal").lower())

    external_attempt_counts: dict[str, int] = field(default_factory=lambda: {
        "weather": 0,
        "tmdb_details": 0,
        "tmdb_search": 0,
        "tmdb_watch_providers": 0,
        "news": 0,
        "gemini": 0,
    })
    external_cache_hit_counts: dict[str, int] = field(default_factory=lambda: {
        "weather": 0,
        "tmdb_details": 0,
        "tmdb_search": 0,
        "tmdb_watch_providers": 0,
        "news": 0,
    })
    timeline: list[dict[str, Any]] = field(default_factory=list)
    _sequence_counter: int = field(default=0, init=False)

    def add_timeline_event(
        self,
        stage: str,
        status: str,
        duration_ms: float = 0.0,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
        result: Any = None,
    ) -> dict[str, Any]:
        self._sequence_counter += 1
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "sequence": self._sequence_counter,
            "stage": stage,
            "status": status,
            "started_at": started_at or now_iso,
            "completed_at": completed_at or now_iso,
            "duration_ms": round(duration_ms, 2),
            "result": scrub_secrets(result),
        }
        self.timeline.append(entry)
        return entry

    def record_external_attempt(self, service: str):
        if service in self.external_attempt_counts:
            self.external_attempt_counts[service] += 1

    def record_external_cache_hit(self, service: str):
        if service in self.external_cache_hit_counts:
            self.external_cache_hit_counts[service] += 1

    def finalize_run(self, result_source: str, final_status: str, response_text: Optional[str] = None) -> dict[str, Any]:
        end_perf = time.perf_counter()
        now_iso = datetime.now(timezone.utc).isoformat()
        self.completed_at = now_iso
        self.total_duration_ms = round((end_perf - self.start_time_perf) * 1000, 2)
        self.result_source = result_source
        self.final_status = final_status
        self.response_text_length = len(response_text) if response_text else 0

        self.add_timeline_event(
            stage="response_returned",
            status=final_status,
            duration_ms=0.0,
            started_at=now_iso,
            completed_at=now_iso,
            result={"result_source": result_source, "response_text_length": self.response_text_length},
        )

        return self.to_summary_dict()

    def to_summary_dict(self) -> dict[str, Any]:
        return scrub_secrets({
            "log_id": f"run_sum_{uuid.uuid4().hex[:10]}",
            "event_type": "startup_briefing_run_completed" if self.final_status != "error" else "startup_briefing_run_failed",
            "telemetry_version": self.telemetry_version,
            "briefing_run_id": self.briefing_run_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "timestamp": self.completed_at or self.started_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at or datetime.now(timezone.utc).isoformat(),
            "total_duration_ms": self.total_duration_ms or round((time.perf_counter() - self.start_time_perf) * 1000, 2),
            "request_duration_ms": self.total_duration_ms or round((time.perf_counter() - self.start_time_perf) * 1000, 2),
            "force_refresh": self.force_refresh,
            "user_timezone": self.user_timezone,
            "resolved_local_date": self.resolved_local_date,
            "server_date": self.server_date,
            "result_source": self.result_source,
            "final_status": self.final_status,
            "response_text_length": self.response_text_length,
            "daily_cache_key": self.daily_cache_key,
            "daily_cache_result": self.daily_cache_result,
            "daily_cache_backend": self.daily_cache_backend,
            "candidate_signature": self.candidate_signature,
            "generation_claim_result": self.generation_claim_result,
            "generation_wait_duration_ms": self.generation_wait_duration_ms,
            "generation_wait_outcome": self.generation_wait_outcome,
            "refresh_reason": self.refresh_reason,
            "already_presented_count": self.already_presented_count,
            "selected_count": self.selected_count,
            "gemini_request_id": self.gemini_request_id,
            "gemini_attempt_count": self.gemini_attempt_count,
            "fallback_attempted": self.fallback_attempted,
            "fallback_trigger": self.fallback_trigger,
            "final_failure_reason": self.final_failure_reason,
            "final_model": self.final_model,
            "external_attempt_counts": self.external_attempt_counts,
            "external_cache_hit_counts": self.external_cache_hit_counts,
            "timeline": self.timeline,
            "gemini_called": self.external_attempt_counts.get("gemini", 0) > 0,
            "fallback_used": self.fallback_attempted,
            "selection_summary": f"Startup briefing run {self.briefing_run_id} finished via '{self.result_source}' ({self.final_status}, {self.total_duration_ms}ms)",
        })


_CURRENT_RUN_CONTEXT: ContextVar[Optional[StartupRunContext]] = ContextVar("_CURRENT_RUN_CONTEXT", default=None)


def get_current_run_context() -> Optional[StartupRunContext]:
    return _CURRENT_RUN_CONTEXT.get()


def set_current_run_context(ctx: Optional[StartupRunContext]):
    return _CURRENT_RUN_CONTEXT.set(ctx)


@dataclass
class DecisionLog:
    log_id: str
    event_type: str = "startup_briefing_candidate_decision"
    telemetry_version: int = 2
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: str = "unknown"
    session_id: Optional[str] = None
    briefing_run_id: Optional[str] = None
    request_id: Optional[str] = None
    model_requested: Optional[str] = "gemini-3.6-flash"
    model_used: Optional[str] = None
    gemini_called: bool = False
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    decision_config_version: int = 1
    prompt_version: int = 1
    required_candidates: list[dict[str, Any]] = field(default_factory=list)
    optional_candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_candidates: list[dict[str, Any]] = field(default_factory=list)
    excluded_candidates: list[dict[str, Any]] = field(default_factory=list)
    random_rolls: dict[str, Any] = field(default_factory=dict)
    cooldowns_applied: list[str] = field(default_factory=list)
    candidate_count_required: int = 0
    candidate_count_optional: int = 0
    candidate_count_selected: int = 0
    candidate_count_excluded: int = 0
    candidate_signature: Optional[str] = None
    decision_duration_ms: float = 0.0
    selection_summary: str = ""
    sanitized_prompt: str = ""
    raw_model_response: str = ""
    final_response: str = ""
    request_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return scrub_secrets(asdict(self))

