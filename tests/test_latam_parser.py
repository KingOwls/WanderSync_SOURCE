from datetime import datetime, timezone

from ingestion.models import SnapshotMetadata
from ingestion.parsers.latam_flights import parse_latam_flights


def _meta(url="https://www.latamairlines.com/co/es/destinos/vuelos-desde-bogota-a-santa-marta"):
    return SnapshotMetadata(
        source="latam", kind="flights", source_url=url, query_hash="q",
        captured_at=datetime(2026, 10, 6, tzinfo=timezone.utc).isoformat(),
        http_status=200, status="SUCCESS",
    )


def test_latam_parser_extracts_exact_date_one_way_offer():
    html = """
    <html><body>
      <h1>Vuelos a Santa Marta desde Bogotá</h1>
      <section class='offer'>
        <span>Vuelo directo</span><span>Desde Bogotá</span><span>Santa Marta</span>
        <span>Solo ida</span><time>09/11/26</time><span>Economy</span>
        <span>Precio desde</span><strong>COP 181.970</strong><span>Tasas incluidas</span>
      </section>
    </body></html>
    """
    rows = parse_latam_flights(html, _meta())
    assert len(rows) == 1
    row = rows[0]
    assert row["airline"] == "LATAM"
    assert row["origin"] == "BOG"
    assert row["destination"] == "SMR"
    assert row["travel_date"] == "2026-11-09"
    assert row["price_text"] == "COP 181.970"
    assert row["trip_type"] == "Solo ida"
    assert row["departure_at"] is None
    assert row["arrival_at"] is None


def test_latam_parser_rejects_month_summary_without_exact_date():
    html = """
    <html><body><h1>Vuelos a Santa Marta desde Bogotá</h1>
    <div>Viaja en noviembre de 2026 desde 181970 COP</div></body></html>
    """
    assert parse_latam_flights(html, _meta()) == []


def test_latam_parser_preserves_multiple_exact_dated_offers():
    html = """
    <html><body><h1>Vuelos a Santa Marta desde Bogotá</h1>
      <article>Solo ida 09/11/26 Economy Precio desde COP 181.970 Tasas incluidas</article>
      <article>Solo ida 18/11/26 Economy Precio desde COP 175.430 Tasas incluidas</article>
    </body></html>
    """
    rows = parse_latam_flights(html, _meta())
    assert [r["travel_date"] for r in rows] == ["2026-11-09", "2026-11-18"]
    assert [r["price_text"] for r in rows] == ["COP 181.970", "COP 175.430"]
