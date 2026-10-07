from __future__ import annotations

from ingestion.normalization.common import city_code, clean, parse_cop_price, stable_id


def normalize_hotel(raw: dict, *, source: str, source_url: str, snapshot_id: str, scraped_at: str) -> dict | None:
    name = clean(raw.get("name") or "")
    room_type = clean(raw.get("room_type") or "") or None
    city = city_code(raw.get("city"))
    price = parse_cop_price(raw.get("price_text"))
    if not name or not city or price is None:
        return None
    return {
        "id": stable_id("HT", source, name, room_type, city, price),
        "name": name,
        "room_type": room_type,
        "city": city,
        "nightly_price": price,
        "currency": "COP",
        "rating": raw.get("rating"),
        "source": source,
        "source_url": source_url,
        "snapshot_id": snapshot_id,
        "scraped_at": scraped_at,
        "active": True,
    }
