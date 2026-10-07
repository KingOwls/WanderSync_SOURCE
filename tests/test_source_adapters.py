from ingestion.sources.cars_public import NationalMedellinCarsAdapter
from ingestion.sources.flights_wingo import WingoFlightsAdapter
from ingestion.sources.hotels_public import GHLPortonMedellinAdapter


def test_real_source_adapters_wait_for_offer_content_not_only_body():
    expected = {
        "wingo": "table",
        "ghl_porton_medellin": "text=COP",
        "alkilautos_national_medellin": "text=Precio por día",
    }
    for adapter in (WingoFlightsAdapter(), GHLPortonMedellinAdapter(), NationalMedellinCarsAdapter()):
        request = adapter.build_requests()[0]
        assert request.ready_selector == expected[adapter.name]
        assert request.ready_selector != "body"


def test_default_source_registry_enables_four_flight_sources_without_latam(monkeypatch):
    import ingestion.sources.registry as registry
    monkeypatch.delenv("SCRAPE_ENABLED_SOURCES", raising=False)
    names = [adapter.name for adapter in registry.get_enabled_adapters()]
    assert names == ["clicair", "satena", "jetsmart", "wingo", "ghl_porton_medellin", "alkilautos_national_medellin"]
    assert "latam" in registry._ADAPTERS  # importable only for historical evidence
    assert "latam" not in names


def test_new_flight_sources_wait_for_public_offer_table():
    import ingestion.sources.registry as registry
    for name in ("clicair", "satena", "jetsmart", "wingo"):
        assert registry.get_adapter(name).build_requests()[0].ready_selector == "table"
        assert registry.get_adapter(name).build_requests()[0].transport == "http"


def test_clicair_and_satena_persist_only_one_way_rows_for_current_flight_schema():
    from datetime import datetime, timezone
    from pathlib import Path
    from ingestion.models import SnapshotMetadata
    import ingestion.sources.registry as registry

    root = Path(__file__).parent / "fixtures" / "scraping"
    for name, fixture in (("clicair", "clicair.html"), ("satena", "satena.html")):
        adapter = registry.get_adapter(name)
        meta = SnapshotMetadata(
            source=name, kind="flights", source_url=adapter.url, query_hash="q",
            captured_at=datetime(2026, 10, 5, tzinfo=timezone.utc).isoformat(), http_status=200, status="SUCCESS",
        )
        rows = adapter.parse((root / fixture).read_text(), meta)
        assert len(rows) == 1
        assert rows[0]["trip_type"].lower() == "solo ida"


def test_dynamic_hotel_and_car_sources_keep_browser_acquisition():
    import ingestion.sources.registry as registry
    assert registry.get_adapter("ghl_porton_medellin").build_requests()[0].transport == "browser"
    assert registry.get_adapter("alkilautos_national_medellin").build_requests()[0].transport == "browser"


def test_active_flight_sources_build_registry_route_requests():
    import ingestion.sources.registry as registry
    from ingestion.sources.flight_routes import routes_for_source

    for name in ("clicair", "satena", "jetsmart", "wingo"):
        requests = registry.get_adapter(name).build_requests()
        expected = [(r.origin, r.destination, r.route_key) for r in routes_for_source(name)]
        actual = [(r.query["origin"], r.query["destination"], r.query["route_key"]) for r in requests]
        assert actual == expected
        assert all(r.transport == "http" for r in requests)


def test_jetsmart_and_wingo_filter_to_one_way_rows():
    from datetime import datetime, timezone
    from pathlib import Path
    from ingestion.models import SnapshotMetadata
    import ingestion.sources.registry as registry

    root = Path(__file__).parent / "fixtures" / "scraping"
    cases = (("jetsmart", "jetsmart.html", 6), ("wingo", "wingo_semantic.html", 1))
    for name, fixture, expected_count in cases:
        adapter = registry.get_adapter(name)
        meta = SnapshotMetadata(source=name, kind="flights", source_url=adapter.url, query_hash="q", captured_at=datetime(2026,10,6,tzinfo=timezone.utc).isoformat(), http_status=200, status="SUCCESS")
        rows = adapter.parse((root / fixture).read_text(), meta)
        assert len(rows) == expected_count
        assert all((row.get("trip_type") or "").lower().startswith("solo ida") for row in rows)
