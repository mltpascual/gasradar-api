"""
Structured logging setup.
Convention: All logs use [Module] prefix for easy filtering.
"""
import logging
import sys
from app.config import settings


def setup_logging():
    """Configure structured logging for the application."""
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger("gasradar")
    logger.info("[API] Logging initialized at level %s", settings.LOG_LEVEL)
    return logger
