from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


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


@dataclass
class DecisionLog:
    log_id: str
    event_type: str = "startup_briefing_decision"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: str = "unknown"
    session_id: Optional[str] = None
    model_requested: str = "gemini-3.6-flash"
    model_used: Optional[str] = "gemini-3.6-flash"
    gemini_called: bool = True
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
    selection_summary: str = ""
    sanitized_prompt: str = ""
    raw_model_response: str = ""
    final_response: str = ""
    request_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
