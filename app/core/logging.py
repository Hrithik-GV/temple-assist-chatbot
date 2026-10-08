"""Logging configuration and setup for the application."""

import logging
import sys
from typing import Optional
from app.core.config import settings


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: Optional[str] = None) -> None:
    """Configure centralized application logging.

    Args:
        level: Optional log level override (e.g. 'DEBUG', 'INFO'). Defaults to settings.LOG_LEVEL.
    """
    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Create standard stream handler with custom format
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)

    # Set third-party loggers to a reasonable level to prevent noise
    logging.getLogger("uvicorn.access").setLevel(log_level)
    logging.getLogger("uvicorn.error").setLevel(log_level)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance.

    Args:
        name: The name of the module/component (typically __name__).

    Returns:
        logging.Logger: Configured logger.
    """
    return logging.getLogger(name)
