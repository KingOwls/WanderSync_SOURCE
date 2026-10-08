from pathlib import Path

ROOT = Path(__file__).parents[1]
FRONTEND = (ROOT / "frontend" / "src" / "main.jsx").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")


def test_package_mode_bootstraps_from_direct_travel_availability_not_tomorrow():
    assert "travelAvailability" in FRONTEND
    assert "outboundLimit:90" in FRONTEND
    assert "returnLimit:90" in FRONTEND
    assert "tomorrow(" not in FRONTEND
    assert "combinations[0]" in FRONTEND


def test_package_mode_renders_outbound_and_return_recommendation_controls():
    assert "outboundDates" in FRONTEND
    assert "returnDates" in FRONTEND
    assert "date-chip" in FRONTEND
    assert "Fechas reales disponibles" in FRONTEND
    assert ".date-options" in CSS


def test_frontend_queries_roundtrip_packages_and_checkout_sends_both_flight_ids():
    assert "outboundFlight{" in FRONTEND
    assert "returnFlight{" in FRONTEND
    assert "flightTotal" in FRONTEND
    assert "outboundFlightId:$outbound" in FRONTEND
    assert "returnFlightId:$returnFlight" in FRONTEND
    assert "pkg.outboundFlight.id" in FRONTEND
    assert "pkg.returnFlight.id" in FRONTEND


def test_package_mode_surfaces_real_availability_without_manual_dates_and_requires_package_route():
    assert 'type="date"' in FRONTEND
    assert "No hay combinación de 1–14 noches entre las fechas publicadas." in FRONTEND
    assert "selectedRoute?.packageAvailable" in FRONTEND
    assert "selectedRoute?.packageAvailable" in FRONTEND


def test_flight_and_package_availability_are_separate_state_paths():
    assert "flightAvailability" in FRONTEND
    assert "packageAvailability" in FRONTEND
    assert "refreshFlightAvailability" in FRONTEND
    assert "refreshPackageAvailability" in FRONTEND
