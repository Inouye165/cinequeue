import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import TMDB_API_KEY
from app.database import init_db
from app.logging_config import setup_logging
from app.routers import movies, watchlist
from app.services.tmdb import TmdbClient

setup_logging()
logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application lifespan")
    init_db()
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
    yield
    if app.state.tmdb:
        await app.state.tmdb.close()
        logger.info("TMDB client closed")
    logger.info("Application lifespan ended")


app = FastAPI(title="Cinequeue", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_tmdb_key(request, call_next):
    if request.url.path.startswith("/api") and request.url.path != "/api/health":
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
