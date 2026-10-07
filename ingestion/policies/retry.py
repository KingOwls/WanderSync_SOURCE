from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def retry_after_seconds(headers: dict | object) -> int | None:
    try:
        value = headers.get("Retry-After") or headers.get("retry-after")
    except AttributeError:
        return None
    if not value:
        return None
    value = str(value).strip()
    if value.isdigit():
        return max(0, int(value))
    try:
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0, int((when - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


def should_retry_status(status: int) -> bool:
    if status in {401, 403}:
        return False
    return status == 429 or 500 <= status < 600


def backoff_seconds(attempt: int, *, base: float = 2.0, cap: float = 30.0) -> float:
    return min(cap, base * (2 ** max(0, attempt - 1)))
