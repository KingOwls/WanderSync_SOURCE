from datetime import datetime, timezone
from pathlib import Path

from ingestion.models import SnapshotMetadata
from ingestion.parsers.cars import parse_cars
from ingestion.parsers.flights import parse_flights
from ingestion.parsers.hotels import parse_hotels

ROOT = Path(__file__).parent / "fixtures" / "scraping"
META = SnapshotMetadata(
    source="test-source", kind="x", source_url="https://example.org/public", query_hash="abc",
    captured_at=datetime(2026, 10, 5, tzinfo=timezone.utc).isoformat(), http_status=200, status="SUCCESS",
)


def test_wingo_parser_extracts_real_route_date_price():
    rows = parse_flights((ROOT / "wingo.html").read_text(), META)
    assert rows[0]["origin"] == "BOG"
    assert rows[0]["destination"] == "MDE"
    assert rows[0]["travel_date"] == "11/11/2026"
    assert rows[0]["price_text"] == "COP84,390"
    assert rows[0]["airline"] == "Wingo"


def test_hotel_parser_extracts_hotel_room_city_and_price_without_inventing_rating():
    rows = parse_hotels((ROOT / "ghl.html").read_text(), META)
    assert rows[0]["name"] == "GHL Portón Medellín"
    assert rows[0]["room_type"] == "Classic King"
    assert rows[0]["city"] == "Medellín"
    assert rows[0]["price_text"] == "419.202 COP"
    assert rows[0]["rating"] is None


def test_car_parser_extracts_provider_model_city_daily_price():
    rows = parse_cars((ROOT / "cars.html").read_text(), META)
    assert rows[0]["provider"] == "National"
    assert rows[0]["model"] == "Renault Logan"
    assert rows[0]["city"] == "Medellín"
    assert rows[0]["category"] == "Compacto Manual"
    assert rows[0]["price_text"] == "COP $223.983"


def _flight_meta(source):
    return SnapshotMetadata(
        source=source, kind="flights", source_url=f"https://example.org/{source}", query_hash="flight",
        captured_at=datetime(2026, 10, 5, tzinfo=timezone.utc).isoformat(), http_status=200, status="SUCCESS",
    )


def test_clicair_parser_extracts_public_offer_table():
    rows = parse_flights((ROOT / "clicair.html").read_text(), _flight_meta("clicair"))
    assert rows
    assert rows[0]["airline"] == "CLIC"
    assert rows[0]["origin"] == "BOG"
    assert rows[0]["destination"] == "EOH"
    assert rows[0]["travel_date"] == "Oct 12, 2026"
    assert rows[0]["price_text"] == "COP 196,250"
    assert rows[0]["trip_type"] == "Solo ida"


def test_satena_parser_extracts_public_offer_table():
    rows = parse_flights((ROOT / "satena.html").read_text(), _flight_meta("satena"))
    assert rows
    assert rows[0]["airline"] == "SATENA"
    assert rows[0]["origin"] == "BOG"
    assert rows[0]["destination"] == "EOH"
    assert rows[0]["travel_date"] == "Oct 18, 2026"
    assert rows[0]["price_text"] == "COP 190,300"
    assert rows[0]["trip_type"] == "Solo ida"


def test_jetsmart_semantic_table_aliases_deduplicate_and_keep_more_than_five_rows():
    rows = parse_flights((ROOT / "jetsmart.html").read_text(), _flight_meta("jetsmart"))
    assert len(rows) == 7  # six valid solo-ida rows plus one round-trip row before adapter filtering
    first = rows[0]
    assert first["airline"] == "JetSMART"
    assert first["origin"] == "BOG"
    assert first["destination"] == "SMR"
    assert first["travel_date"] == "sáb 24 oct 2026"
    assert first["price_text"] == "desde COP 158.230*"


def test_wingo_semantic_table_uses_hacia_and_tipo_de_tarifa_aliases():
    rows = parse_flights((ROOT / "wingo_semantic.html").read_text(), _flight_meta("wingo"))
    assert len(rows) == 1
    assert rows[0]["airline"] == "Wingo"
    assert rows[0]["origin"] == "MDE"
    assert rows[0]["destination"] == "SMR"
    assert rows[0]["trip_type"] == "Solo ida/Económica"


def test_semantic_table_requires_concrete_date_and_price():
    html = '''<table><tr><th>Desde</th><th>A</th><th>Tipo de tarifa</th><th>Fechas</th><th>Precio</th></tr>
    <tr><td>Bogotá (BOG)</td><td>Santa Marta (SMR)</td><td>Solo ida</td><td></td><td>desde COP 100.000</td></tr>
    <tr><td>Bogotá (BOG)</td><td>Santa Marta (SMR)</td><td>Solo ida</td><td>24/10/2026</td><td>Consultar</td></tr></table>'''
    assert parse_flights(html, _flight_meta("jetsmart")) == []
