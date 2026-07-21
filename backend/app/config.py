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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DB_PATH = DATA_DIR / "watchlist.db"
# NOTE: SQLite data is temporary on Cloud Run (containers are ephemeral)
# For persistent storage, set WATCHLIST_BACKEND=firestore

# Watchlist storage backend: "sqlite" (default for local dev) or "firestore"
WATCHLIST_BACKEND = os.getenv("WATCHLIST_BACKEND", "sqlite")

# Google Cloud project ID — used by the Firestore client when set
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")

PORT = int(os.getenv("PORT", "8080"))

# --- Authentication Configuration ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").strip().lower() == "true"
AUTH_MODE = os.getenv("AUTH_MODE", "allowlist").strip().lower()

_raw_emails = os.getenv("AUTH_ALLOWED_EMAILS", "")
AUTH_ALLOWED_EMAILS = [e.strip().lower() for e in _raw_emails.split(",") if e.strip()]

_raw_origins = os.getenv("AUTH_ALLOWED_ORIGINS", "")
AUTH_ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()] or [
    "http://localhost:5180",
    "http://127.0.0.1:5180",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "https://cinequeue-568212960791.us-west1.run.app",
]

FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", GOOGLE_CLOUD_PROJECT or "cinequeue-inouye-2026").strip()

FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "").strip()
FIREBASE_AUTH_DOMAIN = os.getenv("FIREBASE_AUTH_DOMAIN", "cinequeue-inouye-2026.firebaseapp.com").strip()
PUBLIC_AUTH_DOMAIN = os.getenv("PUBLIC_AUTH_DOMAIN", "").strip()
FIREBASE_APP_ID = os.getenv("FIREBASE_APP_ID", "1:568212960791:web:000e9657bed24ce73e8e52").strip()
FIREBASE_MESSAGING_SENDER_ID = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "568212960791").strip()

SESSION_COOKIE_DAYS = int(os.getenv("SESSION_COOKIE_DAYS", "5"))

# Cookie security settings
# Use Secure cookies in production by default
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true" if ENVIRONMENT == "production" else "false").strip().lower() == "true"

# Name of the session cookie
if SESSION_COOKIE_SECURE:
    SESSION_COOKIE_NAME = "__Host-cinequeue_session"
else:
    SESSION_COOKIE_NAME = "cinequeue_session"

# Admin configurations
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()

# Default admin password for local development
if ENVIRONMENT == "development" and not ADMIN_PASSWORD:
    ADMIN_PASSWORD = "admin_secure_pass_2026"

ADMIN_SESSION_COOKIE_NAME = "cinequeue_admin_session"

# Fail-closed validation for production
if AUTH_ENABLED:
    if not FIREBASE_PROJECT_ID:
        raise ValueError("FIREBASE_PROJECT_ID must be set when AUTH_ENABLED is True")
    if not FIREBASE_API_KEY:
        raise ValueError("FIREBASE_API_KEY must be set when AUTH_ENABLED is True")
    if AUTH_MODE == "allowlist" and not AUTH_ALLOWED_EMAILS:
        raise ValueError("AUTH_ALLOWED_EMAILS must be set when AUTH_MODE is 'allowlist' and AUTH_ENABLED is True")
    if ENVIRONMENT == "production" and not AUTH_ALLOWED_ORIGINS:
        raise ValueError("AUTH_ALLOWED_ORIGINS must be set in production when AUTH_ENABLED is True")
    if ENVIRONMENT == "production" and not ADMIN_PASSWORD:
        raise ValueError("ADMIN_PASSWORD must be set in production when AUTH_ENABLED is True")

