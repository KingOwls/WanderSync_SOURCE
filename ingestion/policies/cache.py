from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

SnapshotAge = Literal["FRESH", "STALE", "EXPIRED"]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def classify_snapshot_age(
    captured_at: datetime,
    now: datetime,
    cache_minutes: int,
    stale_hours: int,
) -> SnapshotAge:
    age = _utc(now) - _utc(captured_at)
    seconds = max(0.0, age.total_seconds())
    if seconds <= cache_minutes * 60:
        return "FRESH"
    if seconds <= stale_hours * 3600:
        return "STALE"
    return "EXPIRED"
