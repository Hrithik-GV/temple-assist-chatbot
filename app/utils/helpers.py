"""General utility functions."""

from datetime import datetime, timezone


def get_utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def format_datetime(dt: datetime) -> str:
    """Format a datetime object to ISO-8601 string format."""
    return dt.isoformat()
