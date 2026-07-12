import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
# Try to load .env file for local development, but don't fail if it doesn't exist
load_dotenv(ROOT_DIR / ".env")

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
if TMDB_API_KEY in {"", "your_tmdb_api_key_here"}:
    TMDB_API_KEY = ""
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "watchlist.db"
# NOTE: SQLite data is temporary on Cloud Run (containers are ephemeral)
# For persistent storage, migrate to Cloud SQL or Firestore

PORT = int(os.getenv("PORT", "8080"))
