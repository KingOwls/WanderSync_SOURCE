# WanderSync Multi-City Flight Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand WanderSync from a Bogotá↔Medellín demo into a dynamic five-city flight network whose routes, destinations, dates and package availability are derived only from active scraped offers.

**Architecture:** CLIC, SATENA and LATAM feed a shared flight catalog through explicit route registry entries and source-specific parsers. The Flight Service aggregates active airport-pair routes, the GraphQL Gateway converts them to tourist-city edges and computes round-trip/package availability, and React renders two modes: “Explorar vuelos” for the whole active network and “Armar paquete” only where flights + hotel + car exist.

**Tech Stack:** Python 3.12, FastAPI, Strawberry GraphQL, PostgreSQL, Prefect, Dask, httpx, BeautifulSoup, React 19, Vite, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-06-multi-city-flight-network-design.md`

## Global Constraints

- Zero mock fallback and zero invented routes, dates, prices, airports or availability.
- Tourist cities are limited to `BOG`, `MDE`, `CLO`, `CTG`, `SMR`; Medellín resolves flights through `MDE` and `EOH`, services through `MDE`.
- CLIC and SATENA remain HTTP collectors with the existing tabular parser; LATAM uses HTTP only when public HTML is parseable.
- LATAM monthly summaries without an exact date must never enter `flights`.
- A configured `RouteSpec` is not a visible route until PostgreSQL has at least one active normalized offer for that direction.
- `travelAvailability` remains capped at 8 outbound dates, 8 return dates, 1–14 nights and 12 recommended combinations.
- GHL and Alkilautos collection logic is unchanged in this phase.
- Package reservations remain internal academic local holds; no external airline booking is claimed.
- No CAPTCHA bypass, proxy rotation, browser fingerprint spoofing or user-supplied scraping URLs.

## Review Focus

1. **Configured-but-empty route:** registry contains a URL but parser returns no active offers; `/routes` and `travelNetwork` must not expose it. Covered in Tasks 2–4.
2. **Partial source failure:** one of many CLIC/SATENA/LATAM route requests fails while others succeed; successful routes refresh and unseen routes remain active. Covered in Task 2.
3. **Medellín airport consolidation:** `EOH→CLO` and `MDE→CLO` must become one tourist edge `MDE→CLO` without rewriting stored flight rows. Covered in Tasks 3–4.
4. **Flight-only destination:** a route has active round-trip flights but no hotel/car catalog; “Explorar vuelos” shows it while “Armar paquete” excludes it and explains why. Covered in Tasks 4–5.
5. **No return offers:** one-way outbound offers remain explorable, but no round-trip combination or package is fabricated. Covered in Tasks 4–5.

---

## File Map

**Create**
- `ingestion/sources/flight_routes.py` — immutable auditable route registry.
- `ingestion/sources/flights_latam.py` — LATAM adapter.
- `ingestion/parsers/latam_flights.py` — LATAM exact-date offer parser.
- `tests/test_flight_route_registry.py` — registry and source coverage.
- `tests/test_latam_parser.py` — exact-date parsing / monthly-summary rejection.
- `tests/test_flight_routes_api.py` — active route aggregation.
- `tests/test_travel_network.py` — city graph and package flags.
- `tests/test_frontend_multi_city_contract.py` — dynamic UX contract.
- `docs/MULTI_CITY_FLIGHT_NETWORK.md` — operator/demo guide.

**Modify**
- `ingestion/sources/flights_clic.py`
- `ingestion/sources/flights_satena.py`
- `ingestion/sources/registry.py`
- `ingestion/flow.py`
- `ingestion/runner.py` only if source readiness needs LATAM coverage; do not change readiness semantics.
- `.env.example`
- `docker-compose.yml`
- `backend/flight_service/main.py`
- `backend/gateway/travel_logic.py`
- `backend/gateway/main.py`
- `schema.graphql`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`
- `scripts/scraping_study.sql`
- `scripts/demo_validation.py`
- `scripts/verify_project.py`
- `docs/ARCHITECTURE.md`
- `docs/GRAPHQL.md`
- `docs/DEMO_GUIDE.md`
- existing relevant contract/unit tests.

---

### Task 1: Auditable multi-city route registry and LATAM adapter

**Files:**
- Create: `ingestion/sources/flight_routes.py`
- Create: `ingestion/sources/flights_latam.py`
- Create: `ingestion/parsers/latam_flights.py`
- Create: `tests/test_flight_route_registry.py`
- Create: `tests/test_latam_parser.py`
- Modify: `ingestion/sources/flights_clic.py`
- Modify: `ingestion/sources/flights_satena.py`
- Modify: `ingestion/sources/registry.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Test: `tests/test_source_adapters.py`
- Test: `tests/test_parsers.py`

**Interfaces:**
- Produces: `RouteSpec(source: str, origin: str, destination: str, url: str, acquisition_mode: str)`.
- Produces: `routes_for_source(source: str) -> tuple[RouteSpec, ...]`.
- Produces: `LatamFlightsAdapter.build_requests() -> list[ScrapeRequest]`.
- Produces: `parse_latam_flights(html: str, metadata: SnapshotMetadata) -> list[dict]` returning only exact-date one-way rows.
- CLIC/SATENA continue returning `ScrapeRequest` with `transport="http"` and route context in `query`.

- [ ] **Step 1: Write failing registry tests**

Assert exact route keys:
- CLIC: `BOG-EOH`, `EOH-BOG`, `BOG-CLO`, `CLO-BOG`, `EOH-CLO`, `CLO-EOH`, `EOH-CTG`, `CTG-EOH`, `CLO-CTG`, `CTG-CLO`.
- SATENA: `BOG-EOH`, `EOH-BOG`, `BOG-CLO`, `CLO-BOG`, `EOH-CLO`, `CLO-EOH`.
- LATAM: `BOG-SMR`, `SMR-BOG`, `MDE-SMR`, `SMR-MDE`, `CLO-SMR`, `SMR-CLO`, `CTG-SMR`.
- Explicitly assert `SMR-CTG` is absent.
- Assert every URL is HTTPS, source-owned and acquisition mode is `http`.

- [ ] **Step 2: Run registry tests and verify RED**

Run: `python -m pytest tests/test_flight_route_registry.py tests/test_source_adapters.py -q`
Expected: FAIL because registry and LATAM adapter do not exist and CLIC/SATENA still own fixed URLs.

- [ ] **Step 3: Implement `RouteSpec` and route constants**

Use these exact registry URLs:

**CLIC**
- `BOG→EOH`: `https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin`
- `EOH→BOG`: `https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-bogota`
- `BOG→CLO`: `https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-cali`
- `CLO→BOG`: `https://clicair.co/destinos-colombia/es/vuelos-desde-cali-a-bogota`
- `EOH→CLO`: `https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-cali`
- `CLO→EOH`: `https://clicair.co/destinos-colombia/es/vuelos-desde-cali-a-medellin`
- `EOH→CTG`: `https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-cartagena`
- `CTG→EOH`: `https://clicair.co/destinos-colombia/es/vuelos-desde-cartagena-a-medellin`
- `CLO→CTG`: `https://clicair.co/destinos-colombia/es/vuelos-desde-cali-a-cartagena`
- `CTG→CLO`: `https://clicair.co/destinos-colombia/es/vuelos-desde-cartagena-a-cali`

**SATENA**
- `BOG→EOH`: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-medellin`
- `EOH→BOG`: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-medellin-a-bogota`
- `BOG→CLO`: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-cali`
- `CLO→BOG`: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-cali-a-bogota`
- `EOH→CLO`: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-medellin-a-cali`
- `CLO→EOH`: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-cali-a-medellin`

**LATAM**
- `BOG→SMR`: `https://www.latamairlines.com/co/es/destinos/vuelos-desde-bogota-a-santa-marta`
- `SMR→BOG`: `https://www.latamairlines.com/co/es/destinos/vuelos-desde-santa-marta-a-bogota`
- `MDE→SMR`: `https://www.latamairlines.com/co/es/destinos/vuelos-desde-medellin-a-santa-marta`
- `SMR→MDE`: `https://www.latamairlines.com/co/es/destinos/vuelos-desde-santa-marta-a-medellin`
- `CLO→SMR`: `https://www.latamairlines.com/co/es/destinos/vuelos-desde-cali-a-santa-marta`
- `SMR→CLO`: `https://www.latamairlines.com/co/es/destinos/vuelos-desde-santa-marta-a-cali`
- `CTG→SMR`: `https://www.latamairlines.com/co/es/destinos/vuelos-desde-cartagena-a-santa-marta`

Keep airport codes exactly as published (`EOH` for CLIC/SATENA Medellín routes; `MDE` for LATAM Medellín routes). Do not add `SMR→CTG` until a verified public page produces exact-date normalized offers.

- [ ] **Step 4: Write failing LATAM parser tests**

Tests must prove:
- `Vuelo directo Desde Bogotá Santa Marta Solo ida 09/11/26 Economy Precio desde COP 181.970 Tasas incluidas` becomes `BOG→SMR`, `2026-11-09`, `181970`, `COP`, `trip_type="Solo ida"`.
- A monthly summary such as `Viaja en noviembre de 2026 desde 181970 COP` yields no flight row.
- Multiple dated offers are preserved and sorted/normalized later; parser does not fabricate departure/arrival timestamps.

- [ ] **Step 5: Run LATAM tests and verify RED**

Run: `python -m pytest tests/test_latam_parser.py -q`
Expected: FAIL because parser/adapter do not exist.

- [ ] **Step 6: Implement LATAM parser and adapter**

`parse_latam_flights()` must infer the page route only from supported page headings/text (`Vuelos a <destination> desde <origin>`) plus the exact dated `Solo ida` offer text; map only the five approved city names to IATA codes. Reuse `normalize_flight()`.

- [ ] **Step 7: Register LATAM and make it enabled by default**

Default sources become `clicair,satena,latam,ghl_porton_medellin,alkilautos_national_medellin`; Wingo remains registered but disabled by default.

- [ ] **Step 8: Run source/parser suite**

Run: `python -m pytest tests/test_flight_route_registry.py tests/test_latam_parser.py tests/test_source_adapters.py tests/test_parsers.py tests/test_normalization.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

`git add ingestion/sources ingestion/parsers tests/test_flight_route_registry.py tests/test_latam_parser.py tests/test_source_adapters.py tests/test_parsers.py .env.example docker-compose.yml && git commit -m "feat: add multi-city flight route registry"`

---

### Task 2: Multi-route ingestion with partial-route preservation

**Files:**
- Modify: `ingestion/flow.py`
- Test: `tests/test_scrape_flow.py`
- Test: `tests/test_scrape_persistence.py`
- Modify: `tests/test_compose_scraping_contract.py`

**Interfaces:**
- Consumes: adapters whose `build_requests()` may return 1..N route requests.
- Produces: one `SourceRunResult` per source while persisting all successfully parsed routes.
- Invariant: when any request in a source fails, `persist_catalog_batch(..., preserve_unseen_routes=True)` refreshes only successful route pairs.

- [ ] **Step 1: Add failing N-route batch tests**

Cover a source with three requests where request 2 fails acquisition: requests 1 and 3 must be parsed/normalized/persisted, error diagnostics must include request 2 URL, and no SQL may deactivate an unseen route.

- [ ] **Step 2: Add failing LATAM Prefect-chain test**

Assert an enabled `latam` adapter is submitted through its own collect task and shares the generic parse/normalize/persist flight tasks.

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_scrape_flow.py tests/test_scrape_persistence.py -q`
Expected: at least the LATAM-chain test fails before implementation.

- [ ] **Step 4: Implement `collect_latam_flights` and source scheduling**

Add `@task(name="collect LATAM flights", retries=2, retry_delay_seconds=10)` and include `latam` in `travel_scraping_flow()` without changing partial-result behavior.

- [ ] **Step 5: Make batch diagnostics route-specific where necessary**

Preserve URL/error pairs for failed requests; do not convert a partial source run into `SOURCE_UNAVAILABLE` when at least one route persisted successfully. Existing status precedence `SUCCESS > STALE_FALLBACK > CACHED` remains.

- [ ] **Step 6: Run ingestion/persistence tests**

Run: `python -m pytest tests/test_scrape_flow.py tests/test_scrape_persistence.py tests/test_snapshot_cache.py tests/test_http_collector.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

`git add ingestion/flow.py tests/test_scrape_flow.py tests/test_scrape_persistence.py tests/test_compose_scraping_contract.py && git commit -m "feat: ingest partial multi-route flight sources"`

---

### Task 3: Active airport-route aggregation and five-city resolver

**Files:**
- Create: `tests/test_flight_routes_api.py`
- Modify: `backend/flight_service/main.py`
- Modify: `backend/gateway/travel_logic.py`
- Modify: `tests/test_travel_logic.py`

**Interfaces:**
- Produces Flight Service `GET /routes` rows: `origin`, `destination`, `offer_count`, `sources`, `first_date`, `last_date`, `lowest_price`.
- Produces `resolve_location(code: str) -> ResolvedLocation` for all five tourist cities.
- Produces `city_code_for_airport(code: str) -> str | None`; `EOH` and `MDE` both map to tourist city `MDE`.

- [ ] **Step 1: Write failing `/routes` tests**

Monkeypatch `fetch_all` and assert SQL contains `active=TRUE`, groups by `origin,destination`, aggregates distinct `source`, min/max `travel_date`, and minimum `price`. Returned inactive rows must never be possible through this query.

- [ ] **Step 2: Write failing location tests**

Assert:
- `resolve_location("CLO").flight_airports == ("CLO",)` and service city `CLO`.
- equivalent checks for `CTG`, `SMR`, `BOG`.
- `city_code_for_airport("EOH") == "MDE"`, `city_code_for_airport("MDE") == "MDE"`.
- unsupported airport returns `None` for graph exposure instead of inventing a tourist city.

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_flight_routes_api.py tests/test_travel_logic.py -q`
Expected: FAIL for missing endpoint/helper/cities.

- [ ] **Step 4: Implement `/routes` and resolver helpers**

Do not alter stored `flights.origin`/`destination`; all consolidation is read-time.

- [ ] **Step 5: Run GREEN**

Run: `python -m pytest tests/test_flight_routes_api.py tests/test_travel_logic.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

`git add backend/flight_service/main.py backend/gateway/travel_logic.py tests/test_flight_routes_api.py tests/test_travel_logic.py && git commit -m "feat: expose active multi-city flight routes"`

---

### Task 4: GraphQL `travelNetwork` and package-aware route graph

**Files:**
- Create: `tests/test_travel_network.py`
- Modify: `backend/gateway/travel_logic.py`
- Modify: `backend/gateway/main.py`
- Modify: `schema.graphql`
- Modify: `tests/test_graphql_scraping_contract.py`

**Interfaces:**
- Produces pure `build_travel_network(route_rows: list[dict], service_flags: dict[str, tuple[bool, bool]]) -> NetworkResult`, where `NetworkResult` contains `cities: tuple[str, ...]` and `routes: tuple[NetworkRouteSummary, ...]`; `NetworkRouteSummary` fields are `origin`, `destination`, `offer_count`, `sources`, `outbound_available`, `round_trip_available`, `package_available`, `first_date`, `last_date`, `lowest_price`.
- Produces GraphQL `travelNetwork: TravelNetwork!` with `TravelCity` and `TravelRoute` fields from the spec. `TravelNetwork.cities` contains only supported tourist cities participating in at least one active edge.
- `packageAvailable = roundTripAvailable AND has_hotel AND has_car` for destination service city.

- [ ] **Step 1: Write failing pure graph tests**

Use route rows including `EOH→CLO`, `MDE→CLO`, `CLO→EOH`, `BOG→SMR`. Assert:
- `EOH→CLO` and `MDE→CLO` collapse into one `MDE→CLO` edge with combined count/sources/min-max dates/lowest price.
- `MDE→CLO` is `round_trip_available=True` only when `CLO→MDE/EOH` exists.
- `BOG→SMR` remains flight-only if no `SMR→BOG` row.
- a configured route with zero active route rows is absent.

- [ ] **Step 2: Write failing package-flag tests**

Service flags for destination `MDE=(hotel=True, car=True)` should make a round-trip route to Medellín package-capable; `CLO=(False, False)` must remain flight-only even with round-trip flights.

- [ ] **Step 3: Write failing GraphQL contract tests**

Assert `schema.graphql` exposes `travelNetwork`, `TravelCity`, `TravelRoute`, `packageAvailable`, `roundTripAvailable`, `sources`, `firstDate`, `lastDate`, `lowestPrice`.

- [ ] **Step 4: Run RED**

Run: `python -m pytest tests/test_travel_network.py tests/test_graphql_scraping_contract.py -q`
Expected: FAIL because network query/types do not exist.

- [ ] **Step 5: Implement gateway network query**

`travel_network()` must:
1. GET `{FLIGHT_SERVICE_URL}/routes` once.
2. Convert supported airport pairs to tourist-city pairs.
3. Determine the set of destination service cities represented in the graph (max five).
4. For each such city, query existing Hotel and Car services with `limit=1`; no new hotel/car endpoints.
5. Build and return consolidated network types.

Use `asyncio.gather` for service-availability lookups. Failure of hotel/car lookup must make `packageAvailable=False` for that city rather than inventing availability; flight graph still returns. Extend GraphQL `flightOffers` backward-compatibly with optional `travelDate: String`; when provided, pass it as `travel_date` to the Flight Service so Explore mode can display the exact selected scraped date.

- [ ] **Step 6: Verify generic availability and package queries remain city-resolved**

Add tests proving `travelAvailability("CLO","MDE")` requests `CLO → [MDE,EOH]` and reverse; no Bogotá-specific branch is allowed.

- [ ] **Step 7: Run GREEN**

Run: `python -m pytest tests/test_travel_network.py tests/test_graphql_scraping_contract.py tests/test_travel_logic.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

`git add backend/gateway schema.graphql tests/test_travel_network.py tests/test_graphql_scraping_contract.py tests/test_travel_logic.py && git commit -m "feat: add dynamic GraphQL travel network"`

---

### Task 5: Dynamic two-mode frontend with scrape-only dates

**Files:**
- Create: `tests/test_frontend_multi_city_contract.py`
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/styles.css`
- Test: `tests/test_frontend_roundtrip_contract.py`

**Interfaces:**
- Consumes GraphQL `travelNetwork`, `travelAvailability`, `flightOffers`, `travelPackages`.
- Produces UI modes `flights` and `packages` under the existing search tab.
- No tourist search control contains `<input type="date">`.

- [ ] **Step 1: Write failing frontend contract tests**

Assert source code:
- removes hardcoded `const cities =`.
- queries `travelNetwork` on bootstrap.
- contains mode controls with visible text `Explorar vuelos` and `Armar paquete`.
- derives destination options from `network.routes` for selected origin.
- contains no `type="date"`.
- calls `travelAvailability` after origin/destination selection.
- only calls `travelPackages` in package mode.
- calls `flightOffers(origin,destination,travelDate:selectedOutboundDate)` in flight mode and renders airline, date, price, source and scraped timestamp.

- [ ] **Step 2: Add failing state-message tests**

Require the four spec messages or semantically exact equivalents:
- no active offers;
- outbound but no return;
- flights available but package catalog missing;
- no 1–14 night combination.

- [ ] **Step 3: Run RED**

Run: `python -m pytest tests/test_frontend_multi_city_contract.py tests/test_frontend_roundtrip_contract.py -q`
Expected: FAIL because current UI hardcodes cities and date inputs.

- [ ] **Step 4: Implement network bootstrap and dependent selects**

Initial origin is first city with an outgoing route. Destination list is only active outgoing routes for that origin. On origin change, clear selected dates/results, select first valid destination if available, then load availability.

- [ ] **Step 5: Implement “Explorar vuelos” mode**

Show outbound real dates as chips. If return dates exist, show compatible return chips/combinations; one-way exploration remains valid. Render actual `flightOffers` cards without requiring hotel/car.

- [ ] **Step 6: Implement “Armar paquete” mode**

Filter destination routes to `packageAvailable=true`. Preserve current round-trip package cards and SAGA checkout. If user is viewing a flight-only route, provide a mode switch rather than generic failure.

- [ ] **Step 7: Remove free-date inputs and update responsive styling**

The only values assigned to `startDate/endDate` come from `travelAvailability` chips/combinations.

- [ ] **Step 8: Run frontend tests and build**

Run: `python -m pytest tests/test_frontend_multi_city_contract.py tests/test_frontend_roundtrip_contract.py tests/test_graphql_scraping_contract.py -q`
Expected: PASS.

Run: `npm --prefix frontend install && npm --prefix frontend run build`
Expected: Vite build exit 0. If package registry networking is unavailable in the execution environment, record the environmental limitation and still run the build in Docker/user runtime before release.

- [ ] **Step 9: Commit**

`git add frontend/src tests/test_frontend_multi_city_contract.py tests/test_frontend_roundtrip_contract.py && git commit -m "feat: add dynamic multi-city flight exploration"`

---

### Task 6: Academic evidence, study queries and demo validation

**Files:**
- Create: `docs/MULTI_CITY_FLIGHT_NETWORK.md`
- Modify: `scripts/scraping_study.sql`
- Modify: `scripts/demo_validation.py`
- Modify: `scripts/verify_project.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/GRAPHQL.md`
- Modify: `docs/DEMO_GUIDE.md`
- Test: `tests/test_demo_validation_contract.py`
- Test: `tests/test_docs_real_scraping_contract.py`

**Interfaces:**
- Produces repeatable demo evidence for sources → snapshots → active graph → frontend.
- `scraping_study.sql` must report city-pair route stats after mapping `EOH` to tourist city `MDE` for analysis only.

- [ ] **Step 1: Write failing documentation/verification contracts**

Require documentation to name all five tourist cities, the three flight sources, dynamic route semantics, two UI modes and scrape-only date selection.

- [ ] **Step 2: Extend `scraping_study.sql`**

Add queries for:
- active offer counts by tourist origin/destination and source;
- min/avg/max price by route;
- first/last active date;
- distinct one-way directed routes;
- tourist city pairs having both directions;
- destinations package-capable according to current hotel/car active rows.

Do not update stored airport codes in SQL; use `CASE WHEN code IN ('EOH','MDE') THEN 'MDE' ELSE code END` only in reporting expressions.

- [ ] **Step 3: Update `demo_validation.py`**

Validate `travelNetwork`, select one real network route, query its availability, and prove Bogotá↔Medellín regression if active. The script must not assume every city pair or package exists.

- [ ] **Step 4: Run docs/demo contracts**

Run: `python -m pytest tests/test_demo_validation_contract.py tests/test_docs_real_scraping_contract.py -q`
Expected: PASS.

- [ ] **Step 5: Run static project verification**

Run: `python scripts/verify_project.py`
Expected: every check PASS; update exact expected total if the verifier intentionally gains new checks.

- [ ] **Step 6: Commit**

`git add docs scripts tests/test_demo_validation_contract.py tests/test_docs_real_scraping_contract.py && git commit -m "docs: add multi-city scraping evidence workflow"`

---

### Task 7: Full regression, runtime contract and release ZIP

**Files:**
- Modify only if tests reveal a spec mismatch: `docker-compose.yml`, `.env.example`, contract tests, docs.
- Output artifact: `/mnt/data/WanderSync_Travel_Solutions_MULTI_CITY_NETWORK.zip`

**Interfaces:**
- Release preserves all prior round-trip/SAGA/security behavior plus multi-city network functionality.

- [ ] **Step 1: Run full Python suite**

Run: `python -m pytest -q`
Expected: 0 failures.

- [ ] **Step 2: Compile Python**

Run: `python -m compileall -q backend ingestion scripts`
Expected: exit 0.

- [ ] **Step 3: Verify Compose/source contract**

Run: `python -m pytest tests/test_compose_scraping_contract.py tests/test_runner_sources.py -q`
Expected: PASS with CLIC, SATENA, LATAM enabled by default and Wingo not default.

- [ ] **Step 4: Verify frontend build**

Run: `npm --prefix frontend run build`
Expected: exit 0 when dependencies are installed.

- [ ] **Step 5: Runtime commands for the user's Docker host**

Run externally where Docker is available:
- `docker compose up -d`
- confirm two Dask workers registered;
- `docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python -m ingestion.runner`
- query `scrape_runs`, `flights`, and GraphQL `travelNetwork`.

Acceptance evidence:
- at least one active multi-city edge outside `BOG↔MDE` when current sources publish one;
- Santa Marta appears only if LATAM produced active valid offers;
- frontend destinations match `travelNetwork`;
- no free date inputs;
- flight-only route can be explored even if `packageAvailable=false`.

- [ ] **Step 6: Package a clean ZIP**

Create the archive from tracked/release files only. Exclude `.git`, `.env`, `.pytest_cache`, `__pycache__`, `node_modules`, `frontend/dist`, live snapshots, diagnostic screenshots and security reports containing local runtime information.

- [ ] **Step 7: Extract ZIP into a new directory and rerun verification**

Run in extracted archive:
- `python -m pytest -q`
- `python scripts/verify_project.py`
- `python -m compileall -q backend ingestion scripts`
- frontend build when package registry/dependencies are available.

- [ ] **Step 8: Commit release metadata**

`git add . && git commit -m "release: finalize multi-city flight network"`
