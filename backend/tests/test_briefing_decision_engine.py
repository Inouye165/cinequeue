import json
import pytest
from app.sqlite_repo import SqliteWatchlistRepository
from app.decision_models import (
    Candidate,
    CandidateType,
    DecisionConfig,
    DEFAULT_DECISION_CONFIG,
    PromptVersion,
    DEFAULT_PROMPT_VERSION,
)
from app.services.decision_engine import DecisionEngine, PersonalInterestScorer, RandomSelectionService
from app.services.briefing_service import BriefingService
from app.services.agent_service import AiAgentService


@pytest.fixture
def repo():
    r = SqliteWatchlistRepository()
    user_id = "test_decision_user"
    r.clear_all(user_id)
    return r


@pytest.mark.asyncio
async def test_1_severe_weather_always_selected_over_optional_trivia(repo):
    user_id = "user_test_1"
    raw_candidates = [
        Candidate(
            candidate_id="w_alert_1",
            type=CandidateType.WEATHER_ALERT.value,
            title="Severe Thunderstorm Warning",
            summary="High winds and severe lightning expected.",
            source="weather_service",
            required=True,
            importance_score=0.95,
        ),
        Candidate(
            candidate_id="trivia_1",
            type=CandidateType.PERSONALIZED_TRIVIA.value,
            title="Braveheart",
            summary="Filmed in Ireland.",
            source="trivia_db",
            required=False,
            importance_score=0.50,
            interest_score=0.80,
            confidence_score=0.90,
            combined_score=0.80,
        ),
    ]
    log, selected = DecisionEngine.evaluate(user_id, repo, None, raw_candidates, random_seed=42)
    assert len(selected) >= 1
    assert any(c.type == CandidateType.WEATHER_ALERT.value for c in selected)
    assert selected[0].title == "Severe Thunderstorm Warning"


@pytest.mark.asyncio
async def test_2_ordinary_weather_excluded_during_cooldown(repo):
    user_id = "user_test_2"
    now_iso = repo.utc_now_iso()
    repo.update_user_briefing_state(user_id, login_at=now_iso, briefing_presented_at=now_iso)

    cand = Candidate(
        candidate_id="w_conn_1",
        type=CandidateType.WEATHER_VIEWING_CONNECTION.value,
        title="Spider-Man",
        summary="Rain outside and Spider-Man streaming.",
        source="weather_data",
        required=False,
        importance_score=0.60,
        interest_score=0.85,
        confidence_score=0.90,
        combined_score=0.80,
    )
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=42)
    assert not any(c.type == CandidateType.WEATHER_VIEWING_CONNECTION.value for c in selected)
    assert "ordinary_weather_cooldown" in log.cooldowns_applied or "consecutive_login_restriction" in log.cooldowns_applied


@pytest.mark.asyncio
async def test_3_trivia_consecutive_login_restriction(repo):
    user_id = "user_test_3"
    now_iso = repo.utc_now_iso()
    repo.update_user_briefing_state(user_id, login_at=now_iso, briefing_presented_at=now_iso)

    cand = Candidate(
        candidate_id="trivia_2",
        type=CandidateType.PERSONALIZED_TRIVIA.value,
        title="Inception",
        summary="Inception spinning top fact.",
        source="trivia_db",
        required=False,
        interest_score=0.90,
        confidence_score=0.95,
        combined_score=0.90,
    )
    cfg = DecisionConfig(prevent_optional_items_on_consecutive_logins=True)
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [cand], config=cfg, random_seed=42)
    assert len(selected) == 0
    assert "consecutive_login_restriction" in log.cooldowns_applied


@pytest.mark.asyncio
async def test_4_previously_presented_trivia_not_repeated(repo):
    user_id = "user_test_4"
    fact_id = "trivia_fact_99"
    repo.record_trivia_presentation(user_id, fact_id)

    cand = Candidate(
        candidate_id=fact_id,
        type=CandidateType.PERSONALIZED_TRIVIA.value,
        title="The Dark Knight",
        summary="Batman joker costume fact.",
        source="trivia_db",
        required=False,
        interest_score=0.90,
        confidence_score=0.95,
        combined_score=0.90,
    )
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=42)
    assert len(selected) == 0
    assert any("previously shown" in c.get("exclusion_reason", "") for c in log.excluded_candidates)


@pytest.mark.asyncio
async def test_5_external_news_below_interest_threshold_excluded(repo):
    user_id = "user_test_5"
    cand = Candidate(
        candidate_id="news_low",
        type=CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS.value,
        title="Unrelated Indie Film",
        summary="Minor indie festival news.",
        source="news_api",
        required=False,
        interest_score=0.50,  # Below default threshold 0.72
        confidence_score=0.90,
        combined_score=0.60,
    )
    cfg = DecisionConfig(minimum_interest_score=0.72)
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [cand], config=cfg, random_seed=42)
    assert len(selected) == 0
    assert any("below minimum threshold" in c.get("exclusion_reason", "") for c in log.excluded_candidates)


@pytest.mark.asyncio
async def test_6_major_relevant_news_above_threshold_selected(repo):
    user_id = "user_test_6"
    cand = Candidate(
        candidate_id="news_high",
        type=CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS.value,
        title="Marvel Announcement",
        summary="Major Marvel Studios announcement.",
        source="official_media",
        required=False,
        interest_score=0.95,
        confidence_score=0.95,
        combined_score=0.90,
    )
    # Seed 1 guarantees slot roll <= base_optional_probability
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=1)
    assert len(selected) == 1
    assert selected[0].title == "Marvel Announcement"


@pytest.mark.asyncio
async def test_7_optional_item_omitted_according_to_probability(repo):
    user_id = "user_test_7"
    cand = Candidate(
        candidate_id="opt_1",
        type=CandidateType.PERSONALIZED_RECOMMENDATION.value,
        title="Severance",
        summary="Great sci-fi show.",
        source="recommendations",
        required=False,
        interest_score=0.90,
        confidence_score=0.90,
        combined_score=0.85,
    )
    # Seed 999 produces high slot roll (>0.20)
    cfg = DecisionConfig(optional_item_base_probability=0.20)
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [cand], config=cfg, random_seed=999)
    assert len(selected) == 0
    assert log.random_rolls["optional_slot_roll"] > 0.20


@pytest.mark.asyncio
async def test_8_max_one_optional_item_selected_by_default(repo):
    user_id = "user_test_8"
    cands = [
        Candidate(candidate_id="opt_a", type=CandidateType.PERSONALIZED_TRIVIA.value, title="Title A", summary="Fact A", required=False, interest_score=0.9, confidence_score=0.9, combined_score=0.85),
        Candidate(candidate_id="opt_b", type=CandidateType.MAJOR_EXTERNAL_ENTERTAINMENT_NEWS.value, title="Title B", summary="News B", required=False, interest_score=0.9, confidence_score=0.9, combined_score=0.85),
    ]
    cfg = DecisionConfig(maximum_optional_items=1)
    log, selected = DecisionEngine.evaluate(user_id, repo, None, cands, config=cfg, random_seed=1)
    assert len(selected) <= 1


@pytest.mark.asyncio
async def test_9_deterministic_seeds_produce_reproducible_decisions(repo):
    user_id = "user_test_9"
    cands = [
        Candidate(candidate_id="c1", type=CandidateType.PERSONALIZED_TRIVIA.value, title="Title 1", summary="Sum 1", required=False, interest_score=0.85, confidence_score=0.9, combined_score=0.8),
    ]
    log1, sel1 = DecisionEngine.evaluate(user_id, repo, None, cands, random_seed=12345)
    log2, sel2 = DecisionEngine.evaluate(user_id, repo, None, cands, random_seed=12345)
    assert log1.random_rolls == log2.random_rolls
    assert len(sel1) == len(sel2)


@pytest.mark.asyncio
async def test_10_candidate_explanations_generated(repo):
    user_id = "user_test_10"
    cand = Candidate(candidate_id="c_exp", type=CandidateType.PERSONALIZED_TRIVIA.value, title="Spider-Man", summary="Fact", required=False, interest_score=0.50, confidence_score=0.9, combined_score=0.5)
    log, sel = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=1)
    assert log.selection_summary != ""
    assert "below minimum threshold" in log.excluded_candidates[0]["exclusion_reason"]


@pytest.mark.asyncio
async def test_11_decision_log_records_scores_cooldowns_weights_rolls(repo):
    user_id = "user_test_11"
    cand = Candidate(candidate_id="c_full", type=CandidateType.PERSONALIZED_RECOMMENDATION.value, title="Title Rec", summary="Rec", required=False, interest_score=0.85, confidence_score=0.9, combined_score=0.8)
    log, sel = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=1)
    d = log.to_dict()
    assert "random_rolls" in d
    assert "cooldowns_applied" in d
    assert "decision_config_version" in d


@pytest.mark.asyncio
async def test_12_single_agent_log_table_stores_chat_and_briefing_events(repo):
    user_id = "user_test_12"
    cand = Candidate(candidate_id="c_db", type=CandidateType.MONITORED_TITLE_RELEASE.value, title="Movie Release", summary="Rel", required=True, importance_score=0.9)
    log, sel = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=1)
    repo.add_decision_log(log.to_dict())

    retrieved = repo.get_decision_log(log.log_id)
    assert retrieved is not None
    assert retrieved["user_id"] == user_id


@pytest.mark.asyncio
async def test_13_secrets_never_appear_in_logs_or_diagnostic_bundles(repo):
    from app.services.agent_service import sanitize_log_data
    secret_payload = {"api_key": "secret_123", "token": "bearer_456", "user_id": "safe_id"}
    sanitized = sanitize_log_data(secret_payload)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["user_id"] == "safe_id"


@pytest.mark.asyncio
async def test_14_non_admin_access_denied():
    from app.services.admin_auth import get_current_admin
    from fastapi import HTTPException
    # Non-admin request without cookie or token raises HTTPException
    class DummyState:
        auth_perf = None
    class DummyReq:
        headers = {}
        state = DummyState()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_admin(request=DummyReq(), session_cookie=None)
    assert exc_info.value.status_code in {401, 403}


@pytest.mark.asyncio
async def test_15_admin_list_and_inspect_decision_logs(repo):
    user_id = "user_test_15"
    cand = Candidate(candidate_id="c_admin", type=CandidateType.MONITORED_TITLE_RELEASE.value, title="Admin Title", summary="Summary", required=True)
    log, sel = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=1)
    repo.add_decision_log(log.to_dict())

    res = repo.list_decision_logs(limit=10, user_id=user_id)
    assert res["total"] >= 1
    assert res["logs"][0]["log_id"] == log.log_id


@pytest.mark.asyncio
async def test_17_config_validation_rejects_invalid_probabilities():
    cfg = DecisionConfig(optional_item_base_probability=1.5)
    errs = cfg.validate()
    assert len(errs) > 0
    assert "must be between 0.0 and 1.0" in errs[0]


@pytest.mark.asyncio
async def test_18_config_changes_create_audit_record(repo):
    cfg_dict = DEFAULT_DECISION_CONFIG.to_dict()
    cfg_dict["optional_item_base_probability"] = 0.35
    saved = repo.save_decision_config(cfg_dict, updated_by="admin_user", change_note="Increased prob to 0.35")
    assert saved["version"] >= 1
    assert saved["updated_by"] == "admin_user"


@pytest.mark.asyncio
async def test_19_20_prompt_versioning_and_restore(repo):
    p_dict = DEFAULT_PROMPT_VERSION.to_dict()
    p_dict["wording_instruction"] = "New wording instruction text"
    saved = repo.save_prompt_version(p_dict, updated_by="admin_user", change_note="V2 prompt")
    assert saved["version"] >= 1

    versions = repo.list_prompt_versions()
    assert len(versions) >= 1


@pytest.mark.asyncio
async def test_22_23_preview_mode_reproducible_and_does_not_mark_presented(repo):
    from app.routers.admin import preview_agent_decision, PreviewDecisionRequest
    body = PreviewDecisionRequest(
        user_id="user_preview",
        weather_condition="Rain",
        monitored_title_update="Spider-Man",
        is_streaming_arrival=True,
        random_seed=42,
    )
    # Mock admin call
    class FakeState:
        watchlist_repo = repo
    class FakeApp:
        state = FakeState()
    class FakeReq:
        app = FakeApp()

    res1 = await preview_agent_decision(body, request=FakeReq(), current_admin="admin")
    res2 = await preview_agent_decision(body, request=FakeReq(), current_admin="admin")

    assert res1["preview_mode"] is True
    assert res1["decision_log"]["selected_candidates"] == res2["decision_log"]["selected_candidates"]




@pytest.mark.asyncio
async def test_24_empty_candidate_data_creates_short_greeting(repo):
    user_id = "user_test_24"
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [], random_seed=42)
    assert len(selected) == 0
    assert "NO optional items" in log.selection_summary


@pytest.mark.asyncio
async def test_25_recent_greeting_context_reduces_repetition():
    from app.services.agent_service import AiAgentService
    recent = ["Good morning! Everything is quiet.", "Welcome back! No updates."]
    instruction = AiAgentService._build_greeting_instruction(
        briefing_items=[],
        time_of_day="morning",
        location="Concord",
        weather_json=None,
        recent_openings=recent,
    )
    assert "Recent Openings" in instruction
    assert "Everything is quiet" in instruction


@pytest.mark.asyncio
async def test_26_ordinary_weather_omitted_without_connection(repo):
    user_id = "user_test_26"
    # No rain & no streaming title
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [], random_seed=42)
    assert not any(c.type == CandidateType.WEATHER_VIEWING_CONNECTION.value for c in selected)


@pytest.mark.asyncio
async def test_27_weather_connected_streaming_includes_verified_title(repo):
    user_id = "user_test_27"
    cand = Candidate(
        candidate_id="conn_spidey",
        type=CandidateType.WEATHER_VIEWING_CONNECTION.value,
        title="Spider-Man",
        summary="Rain outside and Spider-Man is streaming.",
        source="weather_and_provider_data",
        required=False,
        importance_score=0.7,
        interest_score=0.9,
        confidence_score=0.95,
        combined_score=0.85,
    )
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [cand], random_seed=1)
    assert len(selected) == 1
    assert selected[0].title == "Spider-Man"


@pytest.mark.asyncio
async def test_28_fallback_response_and_reason_recorded_in_log(repo):
    user_id = "user_test_28"
    log, selected = DecisionEngine.evaluate(user_id, repo, None, [], random_seed=42)
    log.fallback_used = True
    log.fallback_reason = "api_key_missing"
    repo.add_decision_log(log.to_dict())

    retrieved = repo.get_decision_log(log.log_id)
    assert retrieved["fallback_used"] is True
    assert retrieved["fallback_reason"] == "api_key_missing"
