import os
import sys
import tempfile
from pathlib import Path

# Ensure WATCHLIST_BACKEND defaults to sqlite for tests
os.environ.setdefault("WATCHLIST_BACKEND", "sqlite")

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
    repo.clear_all()
    yield
