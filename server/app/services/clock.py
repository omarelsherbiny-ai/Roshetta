"""UTC clock helpers for SQLAlchemy's timezone-naive DateTime columns."""

from datetime import datetime, timezone


def utc_now_naive() -> datetime:
    """Return UTC now without tzinfo for existing naive-UTC database columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_from_timestamp_naive(timestamp: int | float) -> datetime:
    """Convert a Unix timestamp to a naive UTC datetime for database storage."""
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
