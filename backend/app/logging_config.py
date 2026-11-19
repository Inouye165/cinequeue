import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "backend" / "logs"


def setup_logging():
    """Configure logging for the application."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    env_name = os.getenv("ENVIRONMENT", "development").strip().lower()
    is_cloud_run = bool(os.getenv("K_SERVICE"))
    if env_name != "production" and not is_cloud_run:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                LOG_DIR / "app.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=2,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
    )

    # Set specific log levels for external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
