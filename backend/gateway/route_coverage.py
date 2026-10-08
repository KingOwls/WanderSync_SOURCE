from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Iterable

from .travel_logic import city_code_for_airport

SUPPORTED_CITIES = ("BOG", "MDE", "CLO", "CTG", "SMR")
TARGET_OFFERS_PER_DIRECTION = max(1, min(10, int(os.getenv("TARGET_OFFERS_PER_DIRECTION", "10"))))
HEALTHY_SOURCE_STATUSES = {"SUCCESS", "CACHED", "STALE_FALLBACK"}


@dataclass(frozen=True)
class DirectionCoverage:
    status: str
    visible_count: int
    raw_count: int
    offers: tuple[dict, ...]
    sources_checked: int
    sources_available: int


def supported_city_pairs() -> tuple[tuple[str, str], ...]:
    return tuple((origin, destination) for origin in SUPPORTED_CITIES for destination in SUPPORTED_CITIES if origin != destination)


def _tourist_pair(row: dict) -> tuple[str | None, str | None]:
    return (
        city_code_for_airport(str(row.get("origin", ""))),
        city_code_for_airport(str(row.get("destination", ""))),
    )


def _dedup_key(row: dict):
    return (
        str(row.get("source", "")),
        str(row.get("origin", "")),
        str(row.get("destination", "")),
        str(row.get("travel_date", "")),
        row.get("price"),
        row.get("trip_type"),
    )


def select_direction_offers(rows: list[dict], *, origin: str, destination: str, limit: int = 10) -> tuple[dict, ...]:
    origin = origin.strip().upper()
    destination = destination.strip().upper()
    capped = max(1, min(10000, int(limit)))
    seen = set()
    matches: list[dict] = []
    for row in rows:
        if row.get("active") is False:
            continue
        if _tourist_pair(row) != (origin, destination):
            continue
        key = _dedup_key(row)
        if key in seen:
            continue
        seen.add(key)
        matches.append(dict(row))
    matches.sort(key=lambda row: (
        str(row.get("travel_date") or ""),
        float(row.get("price") or 0),
        str(row.get("source") or ""),
        str(row.get("id") or ""),
    ))
    return tuple(matches[:capped])


def _direction_rows(rows: list[dict], origin: str, destination: str) -> list[dict]:
    seen = set()
    result = []
    for row in rows:
        if row.get("active") is False or _tourist_pair(row) != (origin, destination):
            continue
        key = _dedup_key(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def build_direction_coverage(
    rows: list[dict],
    *,
    origin: str,
    destination: str,
    source_health: dict[str, str],
    expected_sources: Iterable[str],
    limit: int = 10,
) -> DirectionCoverage:
    origin = origin.strip().upper()
    destination = destination.strip().upper()
    raw = _direction_rows(rows, origin, destination)
    offers = select_direction_offers(rows, origin=origin, destination=destination, limit=limit)
    expected = tuple(expected_sources)
    available = sum(1 for source in expected if source_health.get(source) in HEALTHY_SOURCE_STATUSES)
    checked = sum(1 for source in expected if source_health.get(source) not in (None, "NOT_RUN"))
    if len(raw) >= TARGET_OFFERS_PER_DIRECTION:
        status = "AVAILABLE"
    elif raw:
        status = "PARTIAL"
    elif expected and available == len(expected):
        status = "NO_OFFERS"
    else:
        status = "SOURCE_UNAVAILABLE"
    return DirectionCoverage(status, len(offers), len(raw), offers, checked, available)
