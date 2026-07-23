import json
import logging
import pytest
import httpx
from app.sqlite_repo import SqliteWatchlistRepository
from app.services.agent_service import (
    AiAgentService,
    build_gemini_request,
    get_system_prompt,
    sanitize_log_data,
)
from app.config import GEMINI_PRIMARY_MODEL, GEMINI_FALLBACK_MODEL


@pytest.fixture
def repo(tmp_path, monkeypatch):
    db_file = tmp_path / "test_refactor_watchlist.db"
    monkeypatch.setattr("app.sqlite_repo.DB_PATH", db_file)
    monkeypatch.setattr("app.sqlite_repo.DATA_DIR", tmp_path)
    repository = SqliteWatchlistRepository()
    yield repository
    repository.clear_all("test_user_refactor")


def test_build_gemini_request_structure():
    """Test 1, 2, 3: systemInstruction is separate, roles are user/model, current msg is final user turn."""
    sys_inst = "You are a movie buff friend."
    history = [
        {"role": "user", "content": "Hi there!"},
        {"role": "assistant", "content": "Hello! How can I help?"},
    ]
    user_msg = "Any update on What Dreams May Come?"
    context_notes = ["Context: Found 'What Dreams May Come' on TMDB (1998-10-02)."]

    payload = build_gemini_request(
        system_instruction=sys_inst,
        recent_history=history,
        user_message=user_msg,
        context_notes=context_notes,
    )

    # 1. Native systemInstruction is separate
    assert "systemInstruction" in payload
    assert payload["systemInstruction"]["parts"][0]["text"] == sys_inst

    # 2. Conversation messages have correct roles (user / model)
    contents = payload["contents"]
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[0]["parts"][0]["text"] == "Hi there!"
    assert contents[1]["role"] == "model"  # Assistant mapped to 'model' for Gemini API
    assert contents[1]["parts"][0]["text"] == "Hello! How can I help?"

    # 3. Current message is the final user turn with exact user_message preserved
    final_turn = contents[2]
    assert final_turn["role"] == "user"
    assert user_msg in final_turn["parts"][0]["text"]
    assert "User: User message:" not in final_turn["parts"][0]["text"]


@pytest.mark.asyncio
async def test_missing_api_key_fallback(monkeypatch, repo):
    """Test 6: Missing API key produces fallback_reason="api_key_missing"."""
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "")
    res = await AiAgentService.process_chat("test_user_refactor", "Hello", repo, None)
    assert res["telemetry"]["fallback_used"] is True
    assert res["telemetry"]["fallback_reason"] == "api_key_missing"
    assert res["telemetry"]["gemini_called"] is False


@pytest.mark.asyncio
async def test_call_gemini_api_non_200_and_timeout(monkeypatch):
    """Test 7 & 8: Non-200 response and timeout recorded properly."""
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "fake_key")

    # Rate limited 429
    def mock_post_429(url, **kwargs):
        return httpx.Response(429, json={"error": "Rate limit exceeded"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_429)
    result_429 = await AiAgentService._call_gemini_api("sys", [], "hello")
    assert result_429.fallback_used is True
    assert result_429.fallback_reason == "rate_limited"
    assert result_429.http_status == 429

    # Timeout
    def mock_post_timeout(url, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_timeout)
    result_timeout = await AiAgentService._call_gemini_api("sys", [], "hello")
    assert result_timeout.fallback_used is True
    assert result_timeout.fallback_reason == "timeout"


@pytest.mark.asyncio
async def test_primary_model_fallback_model_attempt(monkeypatch):
    """Test 9 & 10: Primary model attempted before fallback model, model used recorded."""
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "fake_key")
    monkeypatch.setattr("app.services.agent_service.GEMINI_PRIMARY_MODEL", "gemini-3.6-flash")
    monkeypatch.setattr("app.services.agent_service.GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")

    attempted_models = []

    async def mock_post_success(self, url, json=None, **kwargs):
        for m in ["gemini-3.6-flash", "gemini-3.5-flash"]:
            if m in url:
                attempted_models.append(m)
        if "gemini-3.5-flash" in url:
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{"text": "Success from 3.5 flash"}]}}]
            })
        return httpx.Response(500, json={"error": "Primary model failed"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_success)
    result = await AiAgentService._call_gemini_api("sys", [], "hello")

    assert attempted_models == ["gemini-3.6-flash", "gemini-3.5-flash"]
    assert result.fallback_used is False
    assert result.model_requested == "gemini-3.6-flash"
    assert result.model_used == "gemini-3.5-flash"
    assert result.text == "Success from 3.5 flash"


def test_greeting_prompt_no_canned_language():
    """Test 11 & 12: Greeting prompt contains no forced 'smooth and quiet' language, simple greeting for empty items."""
    prompt = AiAgentService._build_greeting_instruction([], "morning", "Concord, CA", None, ["Hello! Welcome back."])
    assert "smooth and quiet" not in prompt.lower()
    assert "movie marathon" not in prompt.lower()
    assert "Create a brief, natural opening using only the supplied facts" in prompt
    assert "Hello! Welcome back." in prompt  # Past greeting passed for anti-repetition


@pytest.mark.asyncio
async def test_what_dreams_may_come_context_focused(repo, monkeypatch):
    """Test 4, 14: Title-specific query does not include unrelated watchlist/ratings, stays focused."""
    user_id = "test_user_refactor"
    # Add unrelated watchlist item and rating
    repo.add_item(user_id, "movie", 999, "Unrelated Movie", None, "2026-12-01", "queue")
    repo.rate_movie(user_id, "movie", 888, "Unrelated Rating", None, "2025-01-01", 5)

    captured_context = []

    async def mock_call_gemini(system_instruction, recent_history=[], user_message="", context_notes=None):
        if context_notes:
            captured_context.extend(context_notes)
        from app.services.agent_service import AgentResult
        return AgentResult(
            text="Here is info on What Dreams May Come.",
            provider="gemini",
            model_requested="gemini-3.6-flash",
            model_used="gemini-3.6-flash",
            gemini_called=True,
            fallback_used=False,
            fallback_reason=None,
            http_status=200,
            request_duration_ms=100.0,
            actions_taken=[],
        )


    # Mock tmdb search
    class FakeTmdb:
        async def search(self, title):
            return [{"id": 12154, "title": "What Dreams May Come", "media_type": "movie", "release_date": "1998-10-02"}]

        async def get_recommendations(self, media_type, tmdb_id):
            return []

    import app.services.agent_service as agent_module
    monkeypatch.setattr(agent_module.AiAgentService, "_call_gemini_api", mock_call_gemini)

    res = await AiAgentService.process_chat(user_id, "Any update on What Dreams May Come?", repo, FakeTmdb())

    # Verify context notes focus on What Dreams May Come and do not dump unrelated items
    ctx_str = " ".join(captured_context)
    assert "What Dreams May Come" in ctx_str
    assert "Unrelated Movie" not in ctx_str
    assert "Unrelated Rating" not in ctx_str


@pytest.mark.asyncio
async def test_deterministic_action_success_when_gemini_unavailable(monkeypatch, repo):
    """Test 15: Deterministic actions succeed even when Gemini is unavailable."""
    monkeypatch.setattr("app.services.agent_service.GEMINI_API_KEY", "")

    # Mock tmdb
    class FakeTmdb:
        async def search(self, title):
            return [{"id": 550, "title": "Fight Club", "media_type": "movie", "release_date": "1999-10-15"}]

    res = await AiAgentService.process_chat("test_user_refactor", "Add Fight Club to my queue", repo, FakeTmdb())
    assert len(res["actions_taken"]) == 1
    assert res["actions_taken"][0]["action"] == "add_monitoring"
    assert res["actions_taken"][0]["title"] == "Fight Club"
    # Action succeeded in repository
    items = repo.list_items("test_user_refactor")
    assert any(i["title"] == "Fight Club" for i in items)
    # Brief factual fallback string returned without fake personality
    assert "Fight Club" in res["message"]["content"]
    assert res["telemetry"]["fallback_used"] is True


def test_sanitize_log_data():
    """Test 16: No API keys, tokens, emails, or cookies appear in sanitized log data."""
    raw_data = {
        "user_id": "user_123",
        "email": "secret@example.com",
        "api_key": "AQ.SecretKey123",
        "token": "bearer_abc123",
        "cookie": "session=xyz",
        "message": "Hello world",
    }
    sanitized = sanitize_log_data(raw_data)
    json_str = json.dumps(sanitized)
    assert "secret@example.com" not in json_str
    assert "AQ.SecretKey123" not in json_str
    assert "bearer_abc123" not in json_str
    assert "session=xyz" not in json_str
    assert sanitized["user_id"] == "user_123"
