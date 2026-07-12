import logging
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "backend" / "logs"
LOG_DIR.mkdir(exist_ok=True)


def setup_logging():
    """Configure logging for the application."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_DIR / "app.log"),
        ],
    )

    # Set specific log levels for external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
