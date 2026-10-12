"""Core modules including configuration, database, logging, and error handling."""

from app.core.config import settings
from app.core.database import MongoDBManager, get_db, mongodb
from app.core.logging import get_logger, setup_logging

__all__ = [
    "settings",
    "get_logger",
    "setup_logging",
    "mongodb",
    "MongoDBManager",
    "get_db",
]
