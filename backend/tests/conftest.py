"""Shared fixtures and environment setup for backend tests."""

# The test environment must be configured before importing the application.
# pylint: disable=wrong-import-position,import-outside-toplevel

import os
import sys
import tempfile
from pathlib import Path

# Keep the default test app unauthenticated regardless of local shell or .env settings.
os.environ["WATCHLIST_BACKEND"] = "sqlite"
os.environ["AUTH_ENABLED"] = "false"

# Use a temporary directory for test databases so tests don't pollute real data
_test_data_dir = tempfile.mkdtemp(prefix="cinequeue_test_")
os.environ["DATA_DIR"] = _test_data_dir

# Add the backend directory to Python path so imports work
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

import pytest
from app.sqlite_repo import SqliteWatchlistRepository


@pytest.fixture(autouse=True)
def setup_database():
    """Initialize SQLite repo and attach to app state before each test."""
    from app.main import app

    repo = SqliteWatchlistRepository()
    app.state.watchlist_repo = repo
    repo.clear_all("local_test_user")
    yield


@pytest.fixture
def client():
    """Fixture to provide a standard unauthenticated TestClient."""
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_auth():
    """Fixture to provide a test client with mock Firebase Auth enabled."""
    from unittest.mock import patch, AsyncMock
    from fastapi.testclient import TestClient

    with patch.dict("os.environ", {
        "AUTH_ENABLED": "true",
        "AUTH_MODE": "allowlist",
        "AUTH_ALLOWED_EMAILS": "inouye165@gmail.com,sync@example.com",
        "AUTH_ALLOWED_ORIGINS": "https://cinequeue-7tvty3vmvq-uw.a.run.app",
        "ENVIRONMENT": "production",
        "SESSION_COOKIE_SECURE": "true",
        "FIREBASE_API_KEY": "mock_firebase_api_key",
        "ADMIN_PASSWORD": "mock_admin_password_2026"
    }):
        import importlib
        import app.config
        importlib.reload(app.config)
        import app.auth
        importlib.reload(app.auth)
        import app.routers.auth
        importlib.reload(app.routers.auth)
        import app.routers.watchlist
        importlib.reload(app.routers.watchlist)
        import app.routers.movies
        importlib.reload(app.routers.movies)
        import app.main
        importlib.reload(app.main)

        with TestClient(app.main.app, base_url="https://testserver") as c:
            app.main.app.state.tmdb = AsyncMock()
            yield c
