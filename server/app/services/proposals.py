# server/app/services/proposals.py (when an assistant proposal stops being confirmable)
from datetime import datetime, timedelta
from typing import Optional


def proposal_cutoff(now: datetime, ttl_hours: float) -> datetime:
    """Proposals created before this moment are expired. `now` and the stored times are naive UTC."""
    return now - timedelta(hours=ttl_hours)


def proposal_is_expired(created_at: Optional[datetime], now: datetime, ttl_hours: float) -> bool:
    """True when the proposal is older than the allowed age. A row with no creation time is not expired."""
    if created_at is None:
        return False
    return created_at < proposal_cutoff(now, ttl_hours)