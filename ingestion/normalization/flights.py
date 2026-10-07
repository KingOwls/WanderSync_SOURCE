from __future__ import annotations

from ingestion.normalization.common import clean, iso_date, parse_cop_price, stable_id


def normalize_flight(raw: dict, *, source: str, source_url: str, snapshot_id: str, scraped_at: str) -> dict | None:
    origin = clean(raw.get("origin", "")).upper()
    destination = clean(raw.get("destination", "")).upper()
    travel_date = iso_date(raw.get("travel_date"))
    price = parse_cop_price(raw.get("price_text"))
    airline = clean(raw.get("airline") or "")
    if not airline or len(origin) != 3 or len(destination) != 3 or not travel_date or price is None:
        return None
    return {
        "id": stable_id("FL", source, origin, destination, travel_date, price, airline),
        "airline": airline,
        "origin": origin,
        "destination": destination,
        "travel_date": travel_date,
        "departure_at": raw.get("departure_at"),
        "arrival_at": raw.get("arrival_at"),
        "price": price,
        "currency": "COP",
        "source": source,
        "source_url": source_url,
        "snapshot_id": snapshot_id,
        "scraped_at": scraped_at,
        "active": True,
    }
