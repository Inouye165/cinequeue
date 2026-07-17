import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import TMDB_API_KEY, WATCHLIST_BACKEND, GOOGLE_CLOUD_PROJECT, AUTH_ALLOWED_ORIGINS, ENVIRONMENT
from app.logging_config import setup_logging
from app.routers import movies, watchlist, auth, admin
from app.services.tmdb import TmdbClient

setup_logging()
logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application lifespan")

    if ENVIRONMENT == "development":
        from app.config import (
            AUTH_ENABLED,
            AUTH_MODE,
            AUTH_ALLOWED_ORIGINS,
            FIREBASE_PROJECT_ID,
            SESSION_COOKIE_SECURE,
            SESSION_COOKIE_NAME,
        )
        logger.info("=== Development Auth Diagnostics ===")
        logger.info("ENVIRONMENT: %s", ENVIRONMENT)
        logger.info("AUTH_ENABLED: %s", AUTH_ENABLED)
        logger.info("AUTH_MODE: %s", AUTH_MODE)
        logger.info("AUTH_ALLOWED_ORIGINS: %s", AUTH_ALLOWED_ORIGINS)
        logger.info("FIREBASE_PROJECT_ID: %s", FIREBASE_PROJECT_ID)
        logger.info("SESSION_COOKIE_SECURE: %s", SESSION_COOKIE_SECURE)
        logger.info("SESSION_COOKIE_NAME: %s", SESSION_COOKIE_NAME)
        logger.info("WATCHLIST_BACKEND: %s", WATCHLIST_BACKEND)
        logger.info("Cross-Origin-Opener-Policy (COOP): Not explicitly configured in backend middleware")
        logger.info("====================================")

    # -- Watchlist repository --------------------------------------------------
    if WATCHLIST_BACKEND == "firestore":
        from app.firestore_repo import FirestoreWatchlistRepository

        project = GOOGLE_CLOUD_PROJECT or None
        app.state.watchlist_repo = FirestoreWatchlistRepository(project=project)
        logger.info("Using Firestore watchlist backend (project=%s)", project)
    else:
        from app.sqlite_repo import SqliteWatchlistRepository

        app.state.watchlist_repo = SqliteWatchlistRepository()
        logger.info("Using SQLite watchlist backend")

    # -- TMDB client -----------------------------------------------------------
    if TMDB_API_KEY:
        try:
            app.state.tmdb = TmdbClient()
            logger.info("TMDB client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize TMDB client: {e}")
            app.state.tmdb = None
    else:
        logger.warning("TMDB_API_KEY not configured")
        app.state.tmdb = None
    # -- Initialize Admin User -------------------------------------------------
    repo = app.state.watchlist_repo
    from app.config import ADMIN_USERNAME, ADMIN_PASSWORD
    from app.services.admin_auth import hash_password, generate_salt
    try:
        if not repo.get_admin_user(ADMIN_USERNAME):
            salt = generate_salt()
            pwd_hash = hash_password(ADMIN_PASSWORD, salt)
            repo.create_admin_user(ADMIN_USERNAME, pwd_hash, salt)
            logger.info("Initialized default admin user '%s' in database", ADMIN_USERNAME)
    except Exception as e:
        logger.error("Failed to initialize default admin user: %s", e)

    yield
    if app.state.tmdb:
        await app.state.tmdb.close()
        logger.info("TMDB client closed")
    logger.info("Application lifespan ended")


from app.auth_perf import AuthPerfMiddleware

app = FastAPI(title="Cinequeue", lifespan=lifespan)

app.add_middleware(AuthPerfMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=AUTH_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Auth-Trace-Id", "X-Auth-Perf-Token-Verification-Ms", "X-Auth-Perf-Admin-Lookup-Ms"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    
    csp = (
        "default-src 'self'; "
        "script-src 'self' https://apis.google.com https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://image.tmdb.org https://*.googleusercontent.com https://img.youtube.com https://i.ytimg.com; "
        "frame-src 'self' https://cinequeue-inouye-2026.firebaseapp.com https://*.firebaseapp.com https://www.youtube.com https://www.youtube-nocookie.com; "
        "connect-src 'self' https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://*.googleapis.com;"
    )
    response.headers["Content-Security-Policy"] = csp
    
    if ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
    return response


@app.middleware("http")
async def check_tmdb_key(request, call_next):
    if (
        request.url.path.startswith("/api")
        and not request.url.path.startswith("/api/auth")
        and request.url.path != "/api/health"
    ):
        if not app.state.tmdb:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=503,
                content={"detail": "TMDB_API_KEY is not configured"},
            )
    return await call_next(request)


@app.get("/api/health")
async def health():
    return {"status": "ok", "tmdb_configured": bool(TMDB_API_KEY)}


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(movies.router)
app.include_router(watchlist.router)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api"):
            return {"detail": "Not found"}
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
