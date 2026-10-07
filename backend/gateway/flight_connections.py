from __future__ import annotations

from dataclasses import dataclass

from .travel_logic import city_code_for_airport


@dataclass(frozen=True)
class SuggestedConnectionCandidate:
    via: str
    total_price: float
    currency: str
    legs: tuple[dict, dict]


def build_suggested_connections(
    outgoing_rows: list[dict],
    incoming_rows: list[dict],
    *,
    origin: str,
    destination: str,
    travel_date: str,
    limit: int = 10,
) -> tuple[SuggestedConnectionCandidate, ...]:
    origin = origin.strip().upper()
    destination = destination.strip().upper()
    limit = max(1, min(10, int(limit)))
    seen = set()
    candidates: list[SuggestedConnectionCandidate] = []
    for first in outgoing_rows:
        if first.get("active") is False or str(first.get("travel_date")) != travel_date or first.get("currency", "COP") != "COP":
            continue
        first_origin = city_code_for_airport(str(first.get("origin", "")))
        first_via = city_code_for_airport(str(first.get("destination", "")))
        if first_origin != origin or not first_via or first_via in {origin, destination}:
            continue
        for second in incoming_rows:
            if second.get("active") is False or str(second.get("travel_date")) != travel_date or second.get("currency", "COP") != "COP":
                continue
            if str(first.get("id")) == str(second.get("id")):
                continue
            second_via = city_code_for_airport(str(second.get("origin", "")))
            second_destination = city_code_for_airport(str(second.get("destination", "")))
            if second_via != first_via or second_destination != destination:
                continue
            key = (str(first.get("id")), str(second.get("id")))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(SuggestedConnectionCandidate(
                via=first_via,
                total_price=round(float(first.get("price") or 0) + float(second.get("price") or 0), 2),
                currency="COP",
                legs=(first, second),
            ))
    candidates.sort(key=lambda item: (
        item.total_price,
        item.via,
        str(item.legs[0].get("source") or ""),
        str(item.legs[1].get("source") or ""),
        str(item.legs[0].get("id") or ""),
        str(item.legs[1].get("id") or ""),
    ))
    return tuple(candidates[:limit])
