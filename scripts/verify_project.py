from pathlib import Path
import json
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
checks: list[tuple[str, bool, str]] = []


def check(name: str, condition: object, detail: str = "") -> None:
    checks.append((name, bool(condition), detail))


def text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


required = [
    "docker-compose.yml", ".env.example", "schema.graphql",
    "backend/gateway/main.py", "backend/flight_service/main.py", "backend/hotel_service/main.py",
    "backend/car_service/main.py", "backend/order_service/main.py",
    "ingestion/flow.py", "ingestion/runner.py", "ingestion/Dockerfile", "ingestion/requirements.txt",
    "ingestion/collectors/playwright_collector.py", "ingestion/sources/registry.py",
    "ingestion/sources/flights_clic.py", "ingestion/sources/flights_satena.py", "ingestion/sources/flights_jetsmart.py", "ingestion/sources/flights_wingo.py",
    "ingestion/sources/flight_routes.py", "ingestion/parsers/flights.py",
    "ingestion/sources/hotels_public.py", "ingestion/sources/cars_public.py",
    "ingestion/snapshots/__init__.py", "ingestion/snapshots/manager.py", "ingestion/snapshots/metadata.py", "frontend/src/api.js",
    "docs/ARCHITECTURE.md", "docs/SAGA.md", "docs/SECURITY.md", "docs/COMPLIANCE.md", "docs/DATABASE.md",
    "docs/MULTI_CITY_FLIGHT_NETWORK.md", "docs/FLIGHT_SOURCE_POOL_CONNECTIONS.md",
    "FINAL_COMPLIANCE_REVIEW.md", "SCRAPING_FLIGHT_SOURCES.md", "ROUNDTRIP_FLEXIBLE_DATES.md", "scripts/scraping_study.sql",
    "security/audit.sh", "security/audit.ps1", "scripts/db_check.ps1", "scripts/db_check.sh",
]
for rel in required:
    check(f"file:{rel}", (ROOT / rel).exists())

compose_text = text("docker-compose.yml")
compose = yaml.safe_load(compose_text)
services = compose.get("services", {})
expected_services = {
    "postgres", "db-bootstrap", "redis", "flight-service", "hotel-service", "car-service", "order-service",
    "graphql-gateway", "prefect-server", "dask-scheduler", "dask-worker-1", "dask-worker-2",
    "ingestion-runner", "adminer", "frontend",
}
check("compose:exact-services", set(services) == expected_services, f"found={sorted(services)}")
check("scraping:no-provider-service", "provider-service" not in services)
check("scraping:no-provider-url", "PROVIDER_URL" not in compose_text)
check("scraping:no-legacy-provider-code", not (ROOT / "backend/provider_service").exists())

volumes = compose.get("volumes", {})
check("scraping:snapshot-volume", "scrape_snapshots" in volumes)
required_scrape_env = {
    "SCRAPE_SNAPSHOT_ROOT": "${SCRAPE_SNAPSHOT_ROOT:-/data/snapshots}",
    "SCRAPE_CACHE_MINUTES": "${SCRAPE_CACHE_MINUTES:-30}",
    "SCRAPE_STALE_MAX_HOURS": "${SCRAPE_STALE_MAX_HOURS:-24}",
    "SCRAPE_MIN_INTERVAL_SECONDS": "${SCRAPE_MIN_INTERVAL_SECONDS:-90}",
    "SCRAPE_MAX_INTERVAL_SECONDS": "${SCRAPE_MAX_INTERVAL_SECONDS:-180}",
    "SCRAPE_MAX_CONCURRENCY_PER_SOURCE": "${SCRAPE_MAX_CONCURRENCY_PER_SOURCE:-1}",
    "SCRAPE_NAVIGATION_TIMEOUT_SECONDS": "${SCRAPE_NAVIGATION_TIMEOUT_SECONDS:-45}",
    "SCRAPE_RETRY_LIMIT": "${SCRAPE_RETRY_LIMIT:-2}",
    "SCRAPE_ENABLED_SOURCES": "${SCRAPE_ENABLED_SOURCES:-clicair,satena,jetsmart,wingo,ghl_porton_medellin,alkilautos_national_medellin,ghl_bogota,spiwak_cali,ghl_cartagena,ghl_santa_marta,alkilautos_national_bogota,alkilautos_national_cali,alkilautos_national_cartagena,alkilautos_national_santa_marta}",
    "TARGET_OFFERS_PER_DIRECTION": "${TARGET_OFFERS_PER_DIRECTION:-10}",
    "MAX_ROUTE_CONCURRENCY_PER_SOURCE": "${MAX_ROUTE_CONCURRENCY_PER_SOURCE:-2}",
}
for service_name in ("dask-worker-1", "dask-worker-2", "ingestion-runner"):
    cfg = services[service_name]
    check(f"scraping:snapshot-mount:{service_name}", "scrape_snapshots:/data/snapshots" in cfg.get("volumes", []))
    check(f"dask-pythonpath:{service_name}", cfg.get("environment", {}).get("PYTHONPATH") == "/app")
    for key, expected in required_scrape_env.items():
        check(f"scraping:env:{service_name}:{key}", cfg.get("environment", {}).get(key) == expected)

for service_name in ("dask-scheduler", "dask-worker-1", "dask-worker-2", "ingestion-runner"):
    check(f"scraping:shared-image-context:{service_name}", services[service_name].get("build") == "./ingestion")
check("dask-pythonpath:scheduler", services["dask-scheduler"].get("environment", {}).get("PYTHONPATH") == "/app")

requirements = text("ingestion/requirements.txt").lower()
dockerfile = text("ingestion/Dockerfile")
check("scraping:playwright-dependency", "playwright>=" in requirements)
check("scraping:beautifulsoup-dependency", "beautifulsoup4" in requirements)
check("scraping:chromium-installed", "playwright install --with-deps chromium" in dockerfile)
check("dask-dashboard:bokeh", "bokeh>=3.1" in requirements)
check("dask-pythonpath:dockerfile", "PYTHONPATH=/app" in dockerfile)
check("dask-package-layout:dockerfile", "COPY . /app/ingestion" in dockerfile)
check("dask-package-layout:runner", services["ingestion-runner"].get("command") == "python -m ingestion.runner")
check("dask-package-layout:init", (ROOT / "ingestion/__init__.py").exists())

registry = text("ingestion/sources/registry.py")
for source_name in ("clicair", "satena", "jetsmart", "wingo", "ghl_porton_medellin", "alkilautos_national_medellin"):
    check(f"scraping:source:{source_name}", source_name in registry)
collector = text("ingestion/collectors/playwright_collector.py")
for marker in ("robots_allowed", "source_lock", "page.content()", "Challenge/CAPTCHA", "Host is not allowlisted"):
    check(f"scraping:collector:{marker}", marker in collector)

flow = text("ingestion/flow.py")
check("scraping:prefect-flow", 'name="WanderSync real scraping ingestion"' in flow)
check("scraping:dask-submit", "client.submit" in flow and "client.gather" in flow)
check("scraping:real-snapshot-fallback-only", "STALE_FALLBACK" in flow and "no acceptable real snapshot fallback" in flow)
check("scraping:no-mock-production-constants", all(token not in flow for token in ("PROVIDER_URL", "FL-0000", "MockProvider", "mock provider")))
check("scraping:visible-stages", all(marker in flow for marker in ("collect CLIC flights", "collect SATENA flights", "collect JetSMART flights", "collect Wingo flights", "parse flights", "normalize flights", "persist flights")))
check("scraping:no-latam-productive-stage", "collect LATAM flights" not in flow)
check("scraping:route-concurrency-cap", "MAX_ROUTE_CONCURRENCY_PER_SOURCE" in flow and "min(2" in flow)

sql = text("infra/postgres/init.sql").lower()
for table in ("users", "flights", "hotels", "cars", "orders", "saga_events", "billing_events", "scrape_runs", "scrape_snapshots"):
    check(f"db-table:{table}", f"create table if not exists {table}" in sql)
for column in ("source_url", "snapshot_id", "scraped_at", "active"):
    check(f"db-provenance:{column}", column in sql)

for service_name in ("flight-service", "hotel-service", "car-service", "order-service"):
    check(f"network-private:{service_name}", "ports" not in services[service_name])
for service_name in ("flight-service", "hotel-service", "car-service", "order-service", "graphql-gateway", "dask-scheduler"):
    check(f"readiness-healthcheck:{service_name}", "healthcheck" in services[service_name])
check("readiness:order-waits-healthy", all(services["order-service"]["depends_on"][s]["condition"] == "service_healthy" for s in ("flight-service", "hotel-service", "car-service")))
check("readiness:gateway-waits-healthy", all(services["graphql-gateway"]["depends_on"][s]["condition"] == "service_healthy" for s in ("flight-service", "hotel-service", "car-service", "order-service")))
check("readiness:frontend-waits-gateway", services["frontend"]["depends_on"]["graphql-gateway"]["condition"] == "service_healthy")

frontend_api = text("frontend/src/api.js")
check("frontend-only-graphql-url", "VITE_GRAPHQL_URL" in frontend_api and all(s not in frontend_api for s in ("flight-service", "hotel-service", "car-service")))
gateway = text("backend/gateway/main.py")
check("security:argon2", "hash_password" in gateway and "verify_password" in gateway)
check("security:session-rotation", "redis_client.delete" in gateway and "new_session_id" in gateway)
check("security:rate-limits", all(marker in gateway for marker in ("rl:login", "rl:checkout", "rl:payment")))
check("security:no-untrusted-xff", 'request.headers.get("x-forwarded-for")' not in gateway.lower())
check("graphql:provenance", all(marker in gateway for marker in ("source_url", "snapshot_id", "scraped_at", "flight_offers")))
check("graphql:roundtrip-availability", all(marker in gateway for marker in ("travel_availability", "build_availability", "outbound_flight", "return_flight")))
check("graphql:city-airport-resolver", "resolve_location" in gateway and (ROOT / "backend/gateway/travel_logic.py").exists())
check("graphql:travel-network", all(marker in gateway for marker in ("class TravelNetwork", "travel_network", "package_available", "round_trip_available")))
check("graphql:five-tourist-cities", all(city in text("backend/gateway/travel_logic.py") for city in ("BOG", "MDE", "CLO", "CTG", "SMR")))
check("graphql:flight-date-filter", "travel_date" in gateway and "flight_offers" in gateway)
check("graphql:coverage-search-health", all(marker in gateway for marker in ("flight_availability", "flight_search", "source_health", "build_suggested_connections", "select_direction_offers")))
check("graphql:twenty-directions", "supported_city_pairs" in gateway and "SUPPORTED_CITIES" in text("backend/gateway/route_coverage.py"))
check("graphql:target-ten", "TARGET_OFFERS_PER_DIRECTION" in text("backend/gateway/route_coverage.py"))

order = text("backend/order_service/main.py")
check("saga:compensation", "_compensate" in order and "reverse_compensation_order" in order)
check("saga:failure-injection", "simulate_failure" in order)
check("checkout:authoritative-total", "def _authoritative_total" in order and "authoritative_total" in order and "req.total" not in order)
check("saga:two-flight-legs", all(marker in order for marker in ("outbound_flight_id", "return_flight_id", "outbound_flight", "return_flight")))
check("db:roundtrip-order-columns", "outbound_flight_id" in sql and "return_flight_id" in sql)
route_registry = text("ingestion/sources/flight_routes.py")
check("scraping:bidirectional-clic", all(marker in route_registry for marker in ("vuelos-desde-bogota-a-medellin", "vuelos-desde-medellin-a-bogota")))
check("scraping:bidirectional-satena", all(marker in route_registry for marker in ("vuelos-baratos-desde-bogota-a-medellin", "vuelos-baratos-desde-medellin-a-bogota")))
check("scraping:jetsmart-santa-marta", all(marker in route_registry for marker in ("jetsmart", "vuelos-desde-bogota-a-santa-marta", "vuelos-desde-santa-marta-a-bogota")))
check("scraping:wingo-public-routes", "wingo" in route_registry and "vuelos-de-bogota-a-santa-marta" in route_registry)
check("scraping:latam-not-default", "latam" not in text(".env.example").split("SCRAPE_ENABLED_SOURCES=",1)[1].splitlines()[0].lower())
for rel in ("backend/flight_service/main.py", "backend/hotel_service/main.py", "backend/car_service/main.py"):
    service_text = text(rel)
    check(f"holds:no-external-inventory:{rel}", all(x not in service_text for x in ("available_seats", "available_rooms", "available_units")))
    check(f"holds:local-scope:{rel}", "WANDERSYNC_LOCAL_HOLD" in service_text)

frontend_main = text("frontend/src/main.jsx")
check("frontend:travel-network", "travelNetwork" in frontend_main)
check("frontend:date-range-and-observed-dates", 'type="date"' in frontend_main and "date-chip" in frontend_main)
check("frontend:two-search-modes", "Explorar vuelos" in frontend_main and "Armar paquete" in frontend_main)
check("frontend:no-hardcoded-city-list", "const cities =" not in frontend_main)
check("frontend:flight-availability", "flightAvailability" in frontend_main)
check("frontend:flight-search", "flightSearch" in frontend_main and "connections" in frontend_main)
check("frontend:source-health", "sourceHealth" in frontend_main and "Fuentes activas:" in frontend_main)
check("frontend:no-zero-route-filter", "route.outboundAvailable" not in frontend_main.split("const eligibleRoutes",1)[1].split("const originCodes",1)[0])

check("prefect:server-client-parity", "prefect==3.8.8" in requirements and "3.8.8" in str(services["prefect-server"].get("image")))
source_doc = text("docs/FLIGHT_SOURCE_POOL_CONNECTIONS.md").lower()
check("docs:four-active-sources", all(x in source_doc for x in ("clic", "satena", "jetsmart", "wingo")))
check("docs:latam-policy-disabled", "latam" in source_doc and "robots_disallowed" in source_doc and "deshabilitada" in source_doc)
check("docs:20-directions-10-offers", "20 direcciones" in source_doc and "10 ofertas" in source_doc)

for service_name, cfg in services.items():
    if "build" in cfg:
        build = cfg["build"]
        context = build if isinstance(build, str) else build.get("context")
        check(f"build-context:{service_name}", bool(context) and (ROOT / context).exists(), str(context))

try:
    subprocess.run([sys.executable, "-m", "compileall", "-q", str(ROOT / "backend"), str(ROOT / "ingestion"), str(ROOT / "scripts")], check=True, cwd=ROOT)
    check("python-syntax", True)
except subprocess.CalledProcessError as exc:
    check("python-syntax", False, str(exc))

try:
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")], check=False, cwd=ROOT, capture_output=True, text=True)
    check("pytest-suite", result.returncode == 0, (result.stdout + result.stderr).strip()[-1200:])
except Exception as exc:
    check("pytest-suite", False, str(exc))

try:
    json.loads(text("frontend/package.json"))
    check("frontend-package-json", True)
except Exception as exc:
    check("frontend-package-json", False, str(exc))

passed = sum(ok for _, ok, _ in checks)
report = ["WANDERSYNC REAL-SCRAPING STATIC VERIFICATION", "=" * 45, f"Passed: {passed}/{len(checks)}", ""]
for name, ok, detail in checks:
    report.append(f"[{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail and not ok else ''}")
report.extend([
    "",
    "NOTE: This report validates source/configuration contracts and local unit tests.",
    "Docker/Chromium/network runtime evidence must be collected on a Docker host with Internet access using REAL_SCRAPING_ACCEPTANCE.md.",
])
output = "\n".join(report) + "\n"
(ROOT / "VERIFICATION_REPORT.txt").write_text(output, encoding="utf-8")
print(output)
if passed != len(checks):
    raise SystemExit(1)
