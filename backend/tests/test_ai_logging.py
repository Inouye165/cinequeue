import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.services.agent_service import (
    AiAgentService,
    AgentResult,
    calculate_estimated_cost,
    compute_prompt_metrics,
)


def test_calculate_estimated_cost():
    # Flash model: $0.075 / 1M input, $0.30 / 1M output
    cost_flash = calculate_estimated_cost("gemini-3.6-flash", 1000, 500)
    expected_flash = round((1000 * 0.075 / 1_000_000) + (500 * 0.30 / 1_000_000), 8)
    assert cost_flash == expected_flash

    # Pro model: $1.25 / 1M input, $5.00 / 1M output
    cost_pro = calculate_estimated_cost("gemini-1.5-pro", 1000, 500)
    expected_pro = round((1000 * 1.25 / 1_000_000) + (500 * 5.00 / 1_000_000), 8)
    assert cost_pro == expected_pro


def test_compute_prompt_metrics():
    sys_prompt = "System instruction text"
    history = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}]
    user_msg = "What movies are good?"
    context_notes = ["User loves Sci-Fi", "Weather is rainy"]

    total_chars, breakdown = compute_prompt_metrics(sys_prompt, history, user_msg, context_notes)

    assert breakdown["system_instruction_chars"] == len(sys_prompt)
    assert breakdown["history_chars"] == len("Hello") + len("Hi there")
    assert breakdown["history_message_count"] == 2
    assert breakdown["user_message_chars"] == len(user_msg)
    assert breakdown["context_notes_chars"] == len("User loves Sci-Fi") + len("Weather is rainy")
    assert breakdown["context_notes_count"] == 2
    assert total_chars == breakdown["total_prompt_chars"]
    assert total_chars > 0


@pytest.mark.asyncio
async def test_call_gemini_api_telemetry_success(monkeypatch):
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "test_key")

    mock_response_json = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": "Inception is a fantastic Sci-Fi thriller."}]},
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 250,
            "candidatesTokenCount": 50,
            "totalTokenCount": 300,
        },
    }

    async def mock_post(*args, **kwargs):
        return httpx.Response(200, json=mock_response_json)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await AiAgentService._call_gemini_api(
        system_instruction="You are a movie expert.",
        recent_history=[],
        user_message="Tell me about Inception.",
        context_notes=["User likes Nolan"],
        caller="test_caller",
    )

    assert isinstance(result, AgentResult)
    assert result.provider == "gemini"
    assert result.caller == "test_caller"
    assert result.prompt_token_count == 250
    assert result.response_token_count == 50
    assert result.total_token_count == 300
    assert result.finish_reason == "STOP"
    assert result.estimated_cost_usd > 0
    assert result.usage_metadata == mock_response_json["usageMetadata"]
    assert "system_instruction_chars" in result.prompt_breakdown

    d = result.to_dict()
    assert d["prompt_token_count"] == 250
    assert d["response_token_count"] == 50
    assert d["total_token_count"] == 300
    assert d["estimated_cost_usd"] > 0
    assert d["caller"] == "test_caller"


@pytest.mark.asyncio
async def test_call_gemini_api_telemetry_missing_key(monkeypatch):
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", None)

    result = await AiAgentService._call_gemini_api(
        system_instruction="Sys prompt",
        recent_history=[],
        user_message="User prompt",
        caller="no_key_test",
    )

    assert result.provider == "fallback"
    assert result.caller == "no_key_test"
    assert result.prompt_char_count > 0
    assert result.prompt_token_count > 0
    assert result.response_char_count == 0
    assert result.response_token_count == 0
    assert result.finish_reason == "API_KEY_MISSING"


@pytest.mark.asyncio
async def test_call_gemini_api_telemetry_fallback_on_error(monkeypatch):
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "test_key")

    async def mock_post(*args, **kwargs):
        return httpx.Response(500, json={"error": "Internal Error"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await AiAgentService._call_gemini_api(
        system_instruction="Sys prompt",
        recent_history=[],
        user_message="User prompt",
        caller="error_test",
    )

    assert result.provider == "fallback"
    assert result.caller == "error_test"
    assert result.fallback_used is True
    assert result.prompt_char_count > 0
    assert result.prompt_token_count > 0
    assert result.estimated_cost_usd >= 0


def test_get_agent_logs_endpoint(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.sqlite_repo import SqliteWatchlistRepository
    from app.auth import get_current_user, CurrentUser

    db_file = tmp_path / "test_telemetry_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()
    app.state.watchlist_repo = repo

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        uid="test_user", email="test@example.com", display_name="Test User"
    )

    try:
        with TestClient(app) as client:
            res = client.get("/api/agent/logs?limit=10")
            assert res.status_code == 200
            data = res.json()
            assert "logs" in data
            assert "summary" in data
            assert "total_calls" in data["summary"]
            assert "avg_duration_ms" in data["summary"]
            assert "success_rate_percent" in data["summary"]
    finally:
        app.dependency_overrides.clear()


# --- Tests A through G: Truthful AI Logging & Boundary Tests ---

def test_a_local_decision_performs_no_gemini_logging(tmp_path, monkeypatch):
    """Test A: Call DecisionEngine.evaluate() directly and verify local candidate decision event."""
    from app.sqlite_repo import SqliteWatchlistRepository
    from app.services.decision_engine import DecisionEngine
    from app.decision_models import Candidate, CandidateType, DEFAULT_DECISION_CONFIG, DEFAULT_PROMPT_VERSION

    db_file = tmp_path / "test_a_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()

    candidates = [
        Candidate(
            candidate_id="cand_1",
            type=CandidateType.WEATHER_ALERT.value,
            title="Weather Alert",
            summary="Heavy rain outside.",
            source="weather",
            required=True,
        )
    ]

    log, selected = DecisionEngine.evaluate(
        user_id="user_test_a",
        repo=repo,
        tmdb=None,
        raw_candidates=candidates,
        config=DEFAULT_DECISION_CONFIG,
        prompt_version=DEFAULT_PROMPT_VERSION,
    )

    assert log.event_type == "startup_briefing_candidate_decision"
    assert log.gemini_called is False
    assert log.model_used is None

    # Verify no Gemini HTTP attempt events exist in repository logs
    repo.add_decision_log(log.to_dict())
    logs_data = repo.list_decision_logs(user_id="user_test_a")
    saved_logs = logs_data["logs"]
    assert len(saved_logs) == 1
    assert saved_logs[0]["event_type"] == "startup_briefing_candidate_decision"
    assert saved_logs[0]["gemini_called"] is False
    assert not any(l["event_type"].startswith("gemini_http_attempt") for l in saved_logs)


@pytest.mark.asyncio
async def test_b_daily_cache_hit_emits_event_without_gemini_call(tmp_path, monkeypatch):
    """Test B: Mock a valid daily greeting cache hit and verify cache hit returned without Gemini call."""
    from app.sqlite_repo import SqliteWatchlistRepository
    from app.services.agent_service import AiAgentService
    from app.services.briefing_service import BriefingService
    from app.decision_models import resolve_user_local_date, build_stable_daily_cache_key, STARTUP_BRIEFING_CACHE_VERSION

    db_file = tmp_path / "test_b_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()
    user_id = "user_test_b"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    local_date, _ = resolve_user_local_date("America/Los_Angeles")
    cache_key = build_stable_daily_cache_key(user_id, local_date, STARTUP_BRIEFING_CACHE_VERSION)

    repo.save_daily_greeting(user_id, cache_key, {
        "status": "completed",
        "result_source": "fresh_gemini",
        "briefing": "Cached morning briefing text.",
        "briefing_text": "Cached morning briefing text.",
    })

    gemini_called_flag = False
    async def mock_call_gemini(*args, **kwargs):
        nonlocal gemini_called_flag
        gemini_called_flag = True
        raise RuntimeError("Gemini should not be called on cache hit!")

    monkeypatch.setattr(AiAgentService, "_call_gemini_api", mock_call_gemini)

    res = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_b")

    assert res["briefing"] == "Cached morning briefing text."
    assert gemini_called_flag is False

    logs_data = repo.list_decision_logs(user_id=user_id)
    logs = logs_data["logs"]
    assert any(l.get("daily_cache_result") == "hit" for l in logs)


@pytest.mark.asyncio
async def test_c_daily_cache_miss_and_primary_success(tmp_path, monkeypatch):
    """Test C: Mock cache miss and successful primary Gemini HTTP response."""
    import httpx
    from app.sqlite_repo import SqliteWatchlistRepository
    from app.services.briefing_service import BriefingService
    from app.services.agent_service import AiAgentService

    db_file = tmp_path / "test_c_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()
    user_id = "user_test_c"
    repo.save_agent_settings(user_id, {"notify_on_login": True, "timezone": "America/Los_Angeles"})

    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "valid_test_key")

    mock_response_json = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": "Fresh LLM generated briefing."}]},
            }
        ],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 30, "totalTokenCount": 130},
    }

    async def mock_post(*args, **kwargs):
        return httpx.Response(200, json=mock_response_json)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    res = await BriefingService.evaluate_startup_briefing(user_id, repo, tmdb=None, session_id="sess_c")

    assert res["briefing"] == "Fresh LLM generated briefing."

    logs_data = repo.list_decision_logs(user_id=user_id)
    logs = logs_data["logs"]

    # Verify run completed event logs miss
    assert any(l.get("daily_cache_result") == "miss" for l in logs)

    # Verify HTTP attempt events
    completed_attempts = [l for l in logs if l.get("event_type") == "gemini_http_attempt_completed"]
    assert len(completed_attempts) == 1
    attempt = completed_attempts[0]
    assert attempt["attempt_number"] == 1
    assert attempt["is_fallback_attempt"] is False
    assert attempt["model_attempted"] == "gemini-3.6-flash"
    assert attempt["http_status"] == 200
    assert attempt["success"] is True


@pytest.mark.asyncio
async def test_d_primary_failure_and_fallback_success(tmp_path, monkeypatch):
    """Test D: Mock primary request failure (HTTP 503) and fallback model success (HTTP 200)."""
    from app.sqlite_repo import SqliteWatchlistRepository
    from app.services.agent_service import AiAgentService

    db_file = tmp_path / "test_d_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()
    user_id = "user_test_d"

    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "valid_test_key")

    call_count = 0
    async def mock_post(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "gemini-3.6-flash" in str(url):
            return httpx.Response(503, json={"error": "Service Unavailable"})
        else:
            return httpx.Response(200, json={
                "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Fallback model briefing."}]}}],
                "usageMetadata": {"promptTokenCount": 90, "candidatesTokenCount": 20, "totalTokenCount": 110},
            })

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await AiAgentService._call_gemini_api(
        system_instruction="Sys prompt",
        user_message="User prompt",
        caller="briefing_generator",
        user_id=user_id,
        repo=repo,
    )

    assert result.text == "Fallback model briefing."
    assert result.provider == "gemini"
    assert result.fallback_used is True

    logs_data = repo.list_decision_logs(user_id=user_id)
    logs = logs_data["logs"]

    # Verify 2 started events and 2 outcome events (1 failed, 1 completed)
    failed_attempts = [l for l in logs if l["event_type"] == "gemini_http_attempt_failed"]
    completed_attempts = [l for l in logs if l["event_type"] == "gemini_http_attempt_completed"]

    assert len(failed_attempts) == 1
    assert failed_attempts[0]["attempt_number"] == 1
    assert failed_attempts[0]["is_fallback_attempt"] is False
    assert failed_attempts[0]["http_status"] == 503
    assert failed_attempts[0]["success"] is False

    assert len(completed_attempts) == 1
    assert completed_attempts[0]["attempt_number"] == 2
    assert completed_attempts[0]["is_fallback_attempt"] is True
    assert completed_attempts[0]["http_status"] == 200
    assert completed_attempts[0]["success"] is True


@pytest.mark.asyncio
async def test_e_network_exception_logging(tmp_path, monkeypatch):
    """Test E: Mock a network ConnectTimeout exception from httpx."""
    from app.sqlite_repo import SqliteWatchlistRepository
    from app.services.agent_service import AiAgentService

    db_file = tmp_path / "test_e_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()
    user_id = "user_test_e"

    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "valid_test_key")

    async def mock_post(*args, **kwargs):
        raise httpx.ConnectTimeout("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await AiAgentService._call_gemini_api(
        system_instruction="Sys prompt",
        user_message="User prompt",
        caller="briefing_generator",
        user_id=user_id,
        repo=repo,
    )

    assert result.provider == "fallback"

    logs_data = repo.list_decision_logs(user_id=user_id)
    logs = logs_data["logs"]

    started_events = [l for l in logs if l["event_type"] == "gemini_http_attempt_started"]
    failed_events = [l for l in logs if l["event_type"] == "gemini_http_attempt_failed"]

    assert len(started_events) >= 1
    assert len(failed_events) >= 1
    assert failed_events[0]["error_type"] == "ConnectTimeout"
    assert failed_events[0]["success"] is False


def test_f_logging_does_not_expose_secrets(tmp_path, monkeypatch):
    """Test F: Verify log records do not leak secret GEMINI_API_KEY or URL query params."""
    import json
    from app.sqlite_repo import SqliteWatchlistRepository

    db_file = tmp_path / "test_f_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()
    secret_key = "AIzaSySUPER_SECRET_GEMINI_KEY_12345"

    log_entry = {
        "log_id": "test_sec_1",
        "event_type": "gemini_http_attempt_started",
        "timestamp": "2026-07-24T12:00:00Z",
        "user_id": "user_sec",
        "model_attempted": "gemini-3.6-flash",
        "gemini_called": True,
        "selection_summary": "Attempt started for model gemini-3.6-flash",
    }
    repo.add_decision_log(log_entry)

    logs_data = repo.list_decision_logs(user_id="user_sec")
    raw_json = json.dumps(logs_data)

    assert secret_key not in raw_json
    assert "?key=" not in raw_json
    assert "Authorization" not in raw_json
    assert "session_cookie" not in raw_json


def test_g_existing_decision_log_serialization_and_repo_persistence(tmp_path, monkeypatch):
    """Test G: Verify DecisionLog model and repository persistence work after schema updates."""
    from app.sqlite_repo import SqliteWatchlistRepository
    from app.decision_models import DecisionLog

    db_file = tmp_path / "test_g_logs.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repo = SqliteWatchlistRepository()

    log = DecisionLog(
        log_id="log_g_100",
        event_type="startup_briefing_candidate_decision",
        user_id="user_g",
        session_id="sess_g_1",
        model_requested="gemini-3.6-flash",
        model_used=None,
        gemini_called=False,
        fallback_used=False,
        required_candidates=[{"candidate_id": "req1", "title": "Dune"}],
        selection_summary="Selected 1 mandatory update.",
    )

    d = log.to_dict()
    assert d["log_id"] == "log_g_100"
    assert d["event_type"] == "startup_briefing_candidate_decision"
    assert d["gemini_called"] is False

    repo.add_decision_log(d)
    fetched = repo.get_decision_log("log_g_100")
    assert fetched is not None
    assert fetched["log_id"] == "log_g_100"
    assert fetched["event_type"] == "startup_briefing_candidate_decision"
    assert fetched["gemini_called"] is False
    assert len(fetched["required_candidates"]) == 1
    assert fetched["required_candidates"][0]["title"] == "Dune"

