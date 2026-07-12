import sys
from pathlib import Path

# Add the backend directory to Python path so imports work
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

import pytest
from app.database import init_db


@pytest.fixture(autouse=True)
def setup_database():
    """Initialize database before each test."""
    init_db()
    yield
    # Cleanup could be added here if needed
