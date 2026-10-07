from __future__ import annotations

from ingestion.normalization.common import city_code, clean, parse_cop_price, stable_id


def normalize_car(raw: dict, *, source: str, source_url: str, snapshot_id: str, scraped_at: str) -> dict | None:
    provider = clean(raw.get("provider") or "")
    model = clean(raw.get("model") or "")
    city = city_code(raw.get("city"))
    category = clean(raw.get("category") or "") or None
    price = parse_cop_price(raw.get("price_text"))
    if not provider or not model or not city or price is None:
        return None
    return {
        "id": stable_id("CAR", source, provider, model, city, category, price),
        "provider": provider,
        "model": model,
        "city": city,
        "daily_price": price,
        "currency": "COP",
        "category": category,
        "source": source,
        "source_url": source_url,
        "snapshot_id": snapshot_id,
        "scraped_at": scraped_at,
        "active": True,
    }
