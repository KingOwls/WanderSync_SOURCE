from ingestion.normalization.cars import normalize_car
from ingestion.normalization.flights import normalize_flight
from ingestion.normalization.hotels import normalize_hotel


def test_flight_normalization_keeps_observed_values_and_stable_id():
    raw = {"airline":"Wingo","origin":"bog","destination":"mde","travel_date":"11/11/2026","price_text":"COP84,390"}
    a = normalize_flight(raw, source="wingo", source_url="https://www.wingo.com/es/vuelos-nacionales", snapshot_id="snap-1", scraped_at="2026-10-05T21:00:00+00:00")
    b = normalize_flight(raw, source="wingo", source_url="https://www.wingo.com/es/vuelos-nacionales", snapshot_id="snap-2", scraped_at="2026-10-05T22:00:00+00:00")
    assert a["id"] == b["id"]
    assert a["price"] == 84390
    assert a["currency"] == "COP"
    assert a["travel_date"] == "2026-11-11"
    assert a["departure_at"] is None
    assert a["arrival_at"] is None


def test_hotel_normalization_maps_medellin_to_mde_and_preserves_null_rating():
    row = normalize_hotel({"name":" GHL Portón Medellín ","room_type":"Classic King","city":"Medellín","price_text":"419.202 COP","rating":None}, source="ghl", source_url="https://example.com", snapshot_id="s", scraped_at="2026-10-05T21:00:00+00:00")
    assert row["city"] == "MDE"
    assert row["nightly_price"] == 419202
    assert row["rating"] is None


def test_car_normalization_maps_city_and_rejects_missing_required_fields():
    assert normalize_car({"provider":"National","model":"Renault Logan","city":"Medellín","category":"Compacto Manual","price_text":"COP $223.983"}, source="alkilautos", source_url="https://example.com", snapshot_id="s", scraped_at="2026-10-05T21:00:00+00:00")["daily_price"] == 223983
    assert normalize_car({"provider":"National","model":"","city":"Medellín","price_text":"COP $223.983"}, source="alkilautos", source_url="https://example.com", snapshot_id="s", scraped_at="2026-10-05T21:00:00+00:00") is None


def test_flight_normalization_accepts_public_spanish_month_abbreviations():
    raw = {"airline":"SATENA","origin":"BOG","destination":"EOH","travel_date":"Dic 20, 2026","price_text":"COP 322,850"}
    row = normalize_flight(raw, source="satena", source_url="https://rutas-destinos.satena.com/example", snapshot_id="snap-s", scraped_at="2026-10-05T23:00:00+00:00")
    assert row is not None
    assert row["travel_date"] == "2026-12-20"
    assert row["price"] == 322850


def test_iso_date_accepts_spanish_weekday_day_month_year():
    from ingestion.normalization.common import iso_date
    assert iso_date("sáb 24 oct 2026") == "2026-10-24"
    assert iso_date("mié 18 nov 2026") == "2026-11-18"
    assert iso_date("24/10/2026") == "2026-10-24"
    assert iso_date("2026-10-24") == "2026-10-24"
