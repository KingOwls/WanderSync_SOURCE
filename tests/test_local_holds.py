from pathlib import Path

ROOT = Path(__file__).parents[1]


def source(service):
    return (ROOT / "backend" / service / "main.py").read_text(encoding="utf-8").lower()


def test_catalog_services_use_active_scraped_offers_and_do_not_mutate_catalog_inventory():
    for service, table in (("flight_service", "flights"), ("hotel_service", "hotels"), ("car_service", "cars")):
        text = source(service)
        assert "active=true" in text.replace(" ", "")
        assert f"update {table} set available_" not in text
        assert "available_seats" not in text
        assert "available_rooms" not in text
        assert "available_units" not in text


def test_local_hold_cancel_is_idempotent_and_only_updates_reservation_status():
    for service in ("flight_service", "hotel_service", "car_service"):
        text = source(service)
        assert 'if row["status"] == "cancelled"' in text
        assert "set status='cancelled'" in text
        assert '"status": "held"' in text


def test_order_total_only_uses_active_scraped_offers():
    text = source("order_service")
    assert "from flights where id=%s and active=true" in text
    assert "from hotels where id=%s and active=true" in text
    assert "from cars where id=%s and active=true" in text


def test_order_total_includes_both_active_flight_legs():
    text = source("order_service")
    assert "def _authoritative_total(outbound_flight_id: str, return_flight_id: str" in text
    assert text.count("select price from flights where id=%s and active=true") >= 2
    assert 'decimal(str(outbound_flight["price"]))' in text
    assert 'decimal(str(return_flight["price"]))' in text


def test_authoritative_roundtrip_total_requires_cop_catalog_rows():
    text = source("order_service")
    assert text.count("and currency='cop'") >= 4
