from urllib.parse import urlparse

from ingestion.sources.flight_routes import RouteSpec, routes_for_source


def _keys(source):
    return {f"{r.origin}-{r.destination}" for r in routes_for_source(source)}


def test_registry_has_exact_audited_route_keys():
    assert _keys("clicair") == {
        "BOG-EOH", "EOH-BOG", "BOG-CLO", "CLO-BOG", "EOH-CLO", "CLO-EOH",
        "EOH-CTG", "CTG-EOH", "CLO-CTG", "CTG-CLO",
    }
    assert _keys("satena") == {
        "BOG-EOH", "EOH-BOG", "BOG-CLO", "CLO-BOG", "EOH-CLO", "CLO-EOH",
    }
    assert _keys("jetsmart") == {
        "BOG-SMR", "SMR-BOG", "MDE-SMR", "CLO-SMR", "CTG-BOG", "CTG-MDE", "CTG-CLO", "MDE-CTG",
    }
    assert _keys("wingo") == {"BOG-SMR", "MDE-SMR", "CTG-BOG", "BOG-MDE", "MDE-BOG"}
    assert "SMR-CTG" not in _keys("jetsmart")
    assert "SMR-MDE" not in _keys("wingo")


def test_registry_routes_are_https_source_owned_and_http_acquired():
    owned = {
        "clicair": {"clicair.co", "www.clicair.co"},
        "satena": {"rutas-destinos.satena.com"},
        "jetsmart": {"jetsmart.com", "www.jetsmart.com"},
        "wingo": {"wingo.com", "www.wingo.com"},
    }
    for source in owned:
        for route in routes_for_source(source):
            assert isinstance(route, RouteSpec)
            parsed = urlparse(route.url)
            assert parsed.scheme == "https"
            assert parsed.hostname in owned[source]
            assert route.acquisition_mode == "http"
            assert route.origin != route.destination
