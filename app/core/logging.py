"""Logging configuration and setup for the application."""

import logging
import sys
from typing import Optional
from app.core.config import settings


import json
from datetime import datetime, timezone

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JsonLogFormatter(logging.Formatter):
    """Format logs as single-line JSON records for production log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "line": record.lineno,
            "module": record.module,
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


def setup_logging(level: Optional[str] = None, format_type: Optional[str] = None) -> None:
    """Configure centralized application logging.

    Args:
        level: Optional log level override (e.g. 'DEBUG', 'INFO'). Defaults to settings.LOG_LEVEL.
        format_type: Optional format type override ('text' or 'json').
    """
    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO)
    fmt_choice = (format_type or settings.LOG_FORMAT).lower()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Create standard stream handler with chosen formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    if fmt_choice == "json" or (settings.is_production and fmt_choice != "text"):
        formatter = JsonLogFormatter()
    else:
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
