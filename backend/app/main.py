import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    TMDB_API_KEY,
    WATCHLIST_BACKEND,
    GOOGLE_CLOUD_PROJECT,
    AUTH_ALLOWED_ORIGINS,
    ENVIRONMENT,
    FIREBASE_AUTH_DOMAIN,
    PUBLIC_AUTH_DOMAIN,
)
from app.logging_config import setup_logging
from app.routers import movies, watchlist, auth, admin, agent
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
    
    is_auth_proxy = request.url.path.startswith("/__/auth/")
    
    if not is_auth_proxy:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        
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
    else:
        if "X-Content-Type-Options" not in response.headers:
            response.headers["X-Content-Type-Options"] = "nosniff"
        if "Referrer-Policy" not in response.headers:
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if "Permissions-Policy" not in response.headers:
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            
    if ENVIRONMENT == "production":
        if not is_auth_proxy or "Strict-Transport-Security" not in response.headers:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
    return response


@app.middleware("http")
async def check_tmdb_key(request, call_next):
    if (
        request.url.path.startswith("/api")
        and not request.url.path.startswith("/api/auth")
        and not request.url.path.startswith("/api/agent")
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


@app.api_route("/__/auth/{path:path}", methods=["GET", "POST"])
async def firebase_auth_proxy(path: str, request: Request):
    import re
    # Security: Limit request methods strictly to GET and POST
    if request.method not in ("GET", "POST"):
        return Response(status_code=405, content="Method Not Allowed")

    # Security: Limit request size to 10 MB
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 10 * 1024 * 1024:
                return Response(status_code=413, content="Request Entity Too Large")
        except ValueError:
            return Response(status_code=400, content="Invalid Content-Length")

    # Read request body safely up to 10 MB
    body = b""
    if request.method == "POST":
        body = await request.body()
        if len(body) > 10 * 1024 * 1024:
            return Response(status_code=413, content="Request Entity Too Large")

    # Upstream URL Construction: Proxy only the /__/auth/ namespace to the fixed Firebase Auth Domain
    query_string = request.url.query
    query_suffix = f"?{query_string}" if query_string else ""
    target_url = f"https://{FIREBASE_AUTH_DOMAIN}/__/auth/{path}{query_suffix}"

    # Prepare headers to forward (Do not forward Host, or Authorization)
    # Filter Cookie header selectively to drop Cinequeue cookies but keep others
    headers_to_forward = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower in ("host", "authorization", "content-length"):
            continue
        if key_lower == "cookie":
            filtered_cookies = []
            for pair in value.split(";"):
                pair = pair.strip()
                if not pair:
                    continue
                if "=" in pair:
                    cname, _ = pair.split("=", 1)
                    if cname.strip() not in ("__Host-cinequeue_session", "cinequeue_session", "cinequeue_csrf"):
                        filtered_cookies.append(pair)
                else:
                    filtered_cookies.append(pair)
            if filtered_cookies:
                headers_to_forward["cookie"] = "; ".join(filtered_cookies)
        else:
            headers_to_forward[key] = value

    try:
        async with httpx.AsyncClient() as client:
            upstream_resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers_to_forward,
                content=body,
                follow_redirects=False,
                timeout=(5.0, 15.0)
            )

        response = Response(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            media_type=upstream_resp.headers.get("content-type")
        )

        headers_items = (
            upstream_resp.headers.multi_items()
            if hasattr(upstream_resp.headers, "multi_items")
            else upstream_resp.headers.items()
        )
        for key, value in headers_items:
            key_lower = key.lower()
            if key_lower in ("content-length", "transfer-encoding", "content-encoding", "content-type"):
                continue

            # Upstream Location Rewrite logic
            if key_lower == "location":
                legacy_prefix = f"https://{FIREBASE_AUTH_DOMAIN}/__/auth/"
                if value.startswith(legacy_prefix):
                    new_host = PUBLIC_AUTH_DOMAIN or request.url.netloc
                    value = value.replace(legacy_prefix, f"https://{new_host}/__/auth/")
                response.headers.append(key, value)

            # Upstream Set-Cookie Rewrite logic (strip or replace Domain= attribute)
            elif key_lower == "set-cookie":
                domain_pattern = re.compile(rf';?\s*domain={re.escape(FIREBASE_AUTH_DOMAIN)}', re.IGNORECASE)
                if PUBLIC_AUTH_DOMAIN:
                    cleaned_cookie = domain_pattern.sub(f"; domain={PUBLIC_AUTH_DOMAIN}", value)
                else:
                    cleaned_cookie = domain_pattern.sub("", value)
                response.headers.append(key, cleaned_cookie)
            else:
                response.headers.append(key, value)

        return response
    except httpx.RequestError as e:
        logger.error("Firebase auth proxy connectivity error: %s", e)
        return Response(status_code=502, content="Bad Gateway: Failed to connect to identity provider")
    except Exception as e:
        logger.error("Firebase auth proxy unexpected error: %s", e)
        return Response(status_code=500, content="Internal Server Error")


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(agent.router)
app.include_router(watchlist.router)
app.include_router(movies.router)



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
