from pathlib import Path

ROOT = Path(__file__).parents[1]
FRONTEND = (ROOT / "frontend" / "src" / "main.jsx").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")


def test_frontend_bootstraps_dynamic_network_and_has_two_modes():
    assert "const cities =" not in FRONTEND
    assert "travelNetwork" in FRONTEND
    assert "Explorar vuelos" in FRONTEND
    assert "Armar paquete" in FRONTEND
    assert "network.routes" in FRONTEND
    assert "packageAvailable" in FRONTEND


def test_flight_mode_uses_flight_availability_without_free_dates():
    assert 'type="date"' not in FRONTEND
    assert "flightAvailability(origin:$origin,destination:$destination)" in FRONTEND
    assert "flightAvailability" in FRONTEND
    assert "date-chip" in FRONTEND
    assert "travelAvailability" in FRONTEND  # packages keep their direct roundtrip availability


def test_flight_mode_queries_flight_search_for_exact_selected_date_and_provenance():
    assert "flightSearch(origin:$origin,destination:$destination,travelDate:$travelDate,limit:50)" in FRONTEND
    assert "directOffers" in FRONTEND
    assert "connections" in FRONTEND
    for token in ("via", "stops", "totalPrice", "currency", "warning", "legs"):
        assert token in FRONTEND
    for token in ("sourceUrl", "scrapedAt", "airline", "travelDate"):
        assert token in FRONTEND


def test_all_twenty_direction_routes_remain_selectable_in_flight_mode():
    assert "searchMode === 'packages' ? route.packageAvailable : true" in FRONTEND
    assert "route.outboundAvailable" not in FRONTEND.split("const eligibleRoutes", 1)[1].split("const originCodes", 1)[0]
    assert "route.destination !== form.origin" in FRONTEND


def test_frontend_has_exact_coverage_and_connection_copy():
    required = [
        "10 ofertas disponibles",
        "Encontramos menos opciones de lo habitual para esta ruta.",
        "No encontramos vuelos disponibles actualmente.",
        "No pudimos comprobar completamente esta ruta porque algunas fuentes no estuvieron disponibles.",
        "No hay ofertas directas para esta fecha. Estas son conexiones sugeridas.",
        "No encontramos vuelos ni conexiones de una escala para esta fecha.",
        "Conexiones sugeridas",
        "Verifica los horarios exactos con las aerolíneas.",
    ]
    for message in required:
        assert message in FRONTEND


def test_connection_cards_render_two_legs_via_scale_total_and_no_checkout():
    assert "connection.legs.map" in FRONTEND
    assert "1 escala" in FRONTEND
    assert "connection.via" in FRONTEND
    assert "connection.totalPrice" in FRONTEND
    block = FRONTEND.split('className="connection-card"', 1)[1].split("</article>", 1)[0]
    assert "checkout(" not in block
    assert "Reservar" not in block


def test_frontend_queries_source_health_and_has_sanitized_health_banner_and_filters():
    assert "sourceHealth" in FRONTEND
    assert "Fuentes activas:" in FRONTEND
    assert "Algunas fuentes no estuvieron disponibles durante la última actualización." in FRONTEND
    for token in ("Todos", "Directos", "Conexiones", "Todas", "Menor precio"):
        assert token in FRONTEND
    assert ".health-banner" in CSS
    assert ".connection-card" in CSS
    assert ".result-filters" in CSS


def test_package_query_is_only_triggered_from_package_mode_path_and_connections_never_checkout():
    assert "searchPackages" in FRONTEND
    assert "searchFlights" in FRONTEND
    assert "searchMode === 'packages'" in FRONTEND
    assert "travelPackages" in FRONTEND
    checkout_block = FRONTEND.split("async function checkout", 1)[1].split("async function loadOrders", 1)[0]
    assert "connection" not in checkout_block


def test_origin_change_reselects_destination_from_dynamic_route_options():
    assert "[eligibleRoutes, originCodes, searchMode, form.origin, form.destination]" in FRONTEND
    assert "destinations[0]?.destination || ''" in FRONTEND
