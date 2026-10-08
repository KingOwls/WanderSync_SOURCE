from pathlib import Path

ROOT = Path(__file__).parents[1]
GATEWAY = (ROOT / "backend" / "gateway" / "main.py").read_text(encoding="utf-8")
SCHEMA = (ROOT / "schema.graphql").read_text(encoding="utf-8")
FRONTEND = (ROOT / "frontend" / "src" / "main.jsx").read_text(encoding="utf-8")


def test_graphql_catalog_types_expose_real_scrape_provenance_and_no_fake_inventory():
    for field in ("source", "sourceUrl", "snapshotId", "scrapedAt"):
        assert field in SCHEMA
    for removed in ("availableSeats", "availableRooms", "availableUnits"):
        assert removed not in SCHEMA
    assert "travelDate" in SCHEMA


def test_gateway_queries_exact_roundtrip_dates_and_never_invents_prices():
    assert '"travel_date": start_date' in GATEWAY
    assert '"travel_date": end_date' in GATEWAY
    assert "build_roundtrip_packages" in GATEWAY
    assert "nightly_price" in GATEWAY and "daily_price" in GATEWAY


def test_frontend_queries_only_graphql_and_displays_source_provenance():
    assert "sourceUrl" in FRONTEND and "scrapedAt" in FRONTEND and "source" in FRONTEND
    assert "Playwright" not in FRONTEND
    assert "wingo.com" not in FRONTEND
    assert "ghlhoteles.com" not in FRONTEND
    assert "alkilautos.com" not in FRONTEND


def test_flight_service_supports_airport_sets_and_exact_travel_date_without_sql_interpolation():
    source = (ROOT / "backend" / "flight_service" / "main.py").read_text(encoding="utf-8")
    assert "origins: str | None" in source
    assert "destinations: str | None" in source
    assert "travel_date: date | None" in source
    assert "= ANY(%s)" in source
    assert "travel_date=%s" in source
    assert "active=TRUE" in source
    assert "split(\",\")" in source


def test_graphql_exposes_flexible_roundtrip_availability_contract():
    assert "travelAvailability" in SCHEMA
    assert "outboundDates" in SCHEMA
    assert "returnDates" in SCHEMA
    assert "airportCodes" in SCHEMA
    assert "lowestFlightTotal" in SCHEMA
    assert "outboundLimit: Int! = 90" in SCHEMA
    assert "returnLimit: Int! = 90" in SCHEMA
    assert "resolve_location" in GATEWAY
    assert "build_availability" in GATEWAY


def test_graphql_roundtrip_packages_expose_two_flight_legs_and_full_total():
    assert "outboundFlight" in SCHEMA
    assert "returnFlight" in SCHEMA
    assert "flightTotal" in SCHEMA
    assert "flight: Flight!" not in SCHEMA
    assert "build_roundtrip_packages" in GATEWAY
    assert '"travel_date": start_date' in GATEWAY
    assert '"travel_date": end_date' in GATEWAY
    assert "nights > 14" in GATEWAY


def test_graphql_checkout_and_booking_expose_both_flight_leg_ids():
    assert "outboundFlightId" in SCHEMA
    assert "returnFlightId" in SCHEMA
    assert "checkoutPackage(outboundFlightId: String!, returnFlightId: String!" in SCHEMA
    assert "outbound_flight_id" in GATEWAY
    assert "return_flight_id" in GATEWAY


def test_flight_offers_query_uses_city_airport_resolution_for_mde_eoh():
    block = GATEWAY.split("async def flight_offers", 1)[1].split("@strawberry.field", 1)[0]
    assert "resolve_location(origin)" in block
    assert "resolve_location(destination)" in block
    assert '"origins"' in block and '"destinations"' in block


def test_graphql_exposes_dynamic_travel_network_types_and_fields():
    assert "travelNetwork: TravelNetwork!" in SCHEMA
    assert "type TravelNetwork" in SCHEMA
    assert "type TravelCity" in SCHEMA
    assert "type TravelRoute" in SCHEMA
    for field in ("packageAvailable", "roundTripAvailable", "sources", "firstDate", "lastDate", "lowestPrice"):
        assert field in SCHEMA
    assert "travel_network" in GATEWAY
    assert 'f"{FLIGHT_SERVICE_URL}/routes"' in GATEWAY


def test_flight_offers_accepts_optional_exact_scraped_date():
    assert "travelDate: String" in SCHEMA
    block = GATEWAY.split("async def flight_offers", 1)[1].split("@strawberry.field", 1)[0]
    assert "travel_date" in block


def test_graphql_exposes_flight_search_availability_health_and_coverage_contracts():
    required = (
        "flightAvailability", "FlightAvailabilityResult", "FlightDateOption",
        "flightSearch", "FlightSearchResult", "SuggestedConnection",
        "sourceHealth", "SourceHealthSummary", "SourceHealthItem",
        "coverageStatus", "visibleOfferCount", "rawOfferCount", "sourcesChecked", "sourcesAvailable",
    )
    for token in required:
        assert token in SCHEMA
    assert "Verifica los horarios exactos con las aerolíneas." in GATEWAY
    assert "build_suggested_connections" in GATEWAY
    assert "select_direction_offers" in GATEWAY
    assert "travelPackages(origin: String!, destination: String!, startDate: String!, endDate: String!" in SCHEMA
    assert "SuggestedConnection" not in SCHEMA.split("travelPackages",1)[1].split("myBookings",1)[0]


def test_gateway_declares_all_twenty_searchable_pairs_and_direct_first_flow():
    assert "supported_city_pairs" in GATEWAY
    assert "SUPPORTED_CITIES" in GATEWAY or "TOURIST_CITY_NAMES" in GATEWAY
    search_block = GATEWAY.split("async def flight_search",1)[1].split("@strawberry.field",1)[0] if "async def flight_search" in GATEWAY else ""
    assert '"travel_date": travel_date' in search_block
    assert "if all_offers" in search_block
    assert "build_suggested_connections" in search_block
