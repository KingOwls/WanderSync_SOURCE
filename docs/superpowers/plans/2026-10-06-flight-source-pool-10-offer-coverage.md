# WanderSync Flight Source Pool + 10-Offer Coverage + Suggested Connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LATAM with JetSMART and Wingo HTTP sources, expand the five-city network toward all 20 directed pairs, expose at most 10 real offers per direction across all airlines, report truthful availability states, and add safe one-stop suggested connections without introducing mock data or changing direct-flight package/SAGA semantics.

**Architecture:** Four auditable public HTTP flight sources (`clicair`, `satena`, `jetsmart`, `wingo`) feed the existing snapshot → Dask → PostgreSQL pipeline through explicit `RouteSpec` entries and one semantic tabular parser. PostgreSQL preserves real provenance while a pure route-coverage read model consolidates MDE/EOH and selects at most 10 visible offers per directed tourist-city pair, classifying coverage as `AVAILABLE`, `PARTIAL`, `NO_OFFERS` or `SOURCE_UNAVAILABLE`. The GraphQL Gateway returns direct offers first, computes up to 10 one-stop candidates and exposes at most five suggestions when no direct same-date offer exists, and keeps connections out of `travelPackages` and the SAGA.

**Tech Stack:** Python 3.12, FastAPI, Strawberry GraphQL, PostgreSQL, Prefect, Dask Distributed, httpx, BeautifulSoup/lxml, React 19, Vite, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-flight-source-pool-10-offer-coverage-design.md`

## Global Constraints

- Zero mock fallback; never invent routes, dates, prices, availability, schedules, airports or source health.
- Active productive flight sources are exactly `clicair`, `satena`, `jetsmart`, `wingo`; LATAM is disabled by default with documented reason `ROBOTS_DISALLOWED`.
- Coverage target is exactly 20 directed tourist-city pairs and at most 10 visible real offers per direction total across all active airlines.
- PostgreSQL may preserve more than 10 real active rows for provenance; the 10-offer cap is applied by the read model/API and never by fabricating or deleting evidence.
- `AVAILABLE` means the direction has at least 10 real rows and exposes 10; `PARTIAL` means 1–9; `NO_OFFERS` means zero with healthy source observation; `SOURCE_UNAVAILABLE` means zero cannot be trusted because relevant source observation is incomplete.
- User-facing copy never asserts "sold out" unless a provider explicitly supplies that state.
- Route acquisition concurrency is capped at 2 simultaneous routes per source.
- Prefect server/client versions are pinned equal in the final release.
- Flight acquisition for all four active sources is public HTTP only in this phase; GHL and Alkilautos remain unchanged and continue using their existing collectors.
- Every productive URL is server-side, HTTPS and host-allowlisted; users never supply scraper URLs.
- `robots.txt` is evaluated before acquisition. A denied route is non-transient and must not be retried repeatedly in the same Prefect run.
- Cache and `STALE_FALLBACK` may reuse only prior real snapshots under the existing age policy.
- A configured `RouteSpec` never creates a visible route by itself. `travelNetwork` remains derived only from `flights.active = TRUE`.
- Tourist cities remain `BOG`, `MDE`, `CLO`, `CTG`, `SMR`; `MDE` consolidates real `MDE` and `EOH` airports only in read models.
- Suggested connections use exactly two real active legs, the exact selected date, one intermediate tourist city, `COP` on both legs and no cycles; build at most 10 candidates and expose at most five results.
- Suggested connections are never presented as guaranteed connections and always carry `Verifica los horarios exactos con las aerolíneas.`
- `travelPackages`, checkout and SAGA remain direct-flight only and retain 1–14-night round-trip semantics.
- No CAPTCHA bypass, fingerprint spoofing, proxy rotation or policy evasion.
- Final release ZIP excludes `.git`, `.env`, runtime snapshots, caches, `node_modules`, generated frontend build output and local virtual environments; it must include `ingestion/snapshots/__init__.py`, `manager.py`, and `metadata.py`.

## Review Focus

1. **Ten-offer cap without data loss:** more than ten real rows may exist in PostgreSQL, but API-visible offers for one direction must be deterministically capped at ten without deleting raw evidence. Covered in Task 4.
2. **Zero results with incomplete acquisition:** a route with no rows must become `SOURCE_UNAVAILABLE`, not `NO_OFFERS`, when relevant active sources are unhealthy or not run. Covered in Tasks 3, 4 and 6.
3. **Semantic-table drift and duplicate fares:** header aliases and Spanish dates must parse JetSMART/Wingo while duplicate rows do not inflate the ten-offer count. Covered in Task 2.
4. **False connections through airport/city mismatch or date mismatch:** `EOH` and `MDE` consolidate only in read logic; each suggested path uses exactly two real same-date legs and no origin/destination city as `via`. Covered in Task 5.
5. **Distributed-environment drift:** scheduler, both workers and runner must carry the same ingestion package and compatible Dask/Prefect environments; the final artifact must preserve `ingestion/snapshots`. Covered in Tasks 3 and 8.

---

## File Map

**Create**
- `ingestion/sources/flights_jetsmart.py` — JetSMART HTTP adapter backed by audited route specs.
- `tests/fixtures/scraping/jetsmart.html` — semantic-table fixture containing exact dated one-way offers.
- `tests/fixtures/scraping/wingo_semantic.html` — current Wingo semantic-table fixture while preserving the legacy fixture.
- `backend/gateway/route_coverage.py` — pure 20-direction coverage selection/status logic.
- `tests/test_route_coverage.py` — max-10, deduplication, MDE/EOH and availability-state tests.
- `backend/gateway/flight_connections.py` — pure one-stop connection engine.
- `tests/test_flight_connections.py` — direct-independent connection rules and edge cases.
- `tests/test_source_health.py` — sanitized four-source health aggregation contract.
- `tests/test_distributed_runtime_contract.py` — static/runtime-import contract for scheduler/workers/runner consistency where Docker is available.
- `docs/FLIGHT_SOURCE_POOL_CONNECTIONS.md` — source policy, connection semantics and demo notes.

**Modify**
- `ingestion/sources/flight_routes.py`
- `ingestion/sources/flights_clic.py`
- `ingestion/sources/flights_satena.py`
- `ingestion/sources/flights_wingo.py`
- `ingestion/sources/registry.py`
- `ingestion/parsers/flights.py`
- `ingestion/normalization/common.py`
- `ingestion/collectors/http_collector.py` only where tests require policy classification; preserve existing allowlist/DNS validation.
- `ingestion/flow.py`
- `.env.example`
- `backend/gateway/main.py`
- `schema.graphql`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`
- `scripts/demo_validation.py`
- `scripts/scraping_study.sql`
- `scripts/verify_project.py`
- `docs/ARCHITECTURE.md`
- `docs/COMPLIANCE.md`
- `docs/GRAPHQL.md`
- `docs/DEMO_GUIDE.md`
- existing relevant tests under `tests/`.

**Do not modify unless a failing regression proves necessary**
- `backend/order_service/*`
- `backend/hotel_service/*`
- `backend/car_service/*`
- SAGA reservation schemas and migrations
- GHL/Alkilautos adapters and parsers.

---

### Task 1: Productive source pool, audited routes, and HTTP adapters

**Files:**
- Create: `ingestion/sources/flights_jetsmart.py`
- Modify: `ingestion/sources/flight_routes.py`
- Modify: `ingestion/sources/flights_wingo.py`
- Modify: `ingestion/sources/registry.py`
- Modify: `.env.example`
- Test: `tests/test_flight_route_registry.py`
- Test: `tests/test_source_adapters.py`
- Test: `tests/test_runner_sources.py`

**Interfaces:**
- Consumes: existing `RouteSpec(source, origin, destination, url, acquisition_mode="http")` and `routes_for_source(source)`.
- Produces: `JetSmartFlightsAdapter` with `name="jetsmart"`, `kind="flights"`, source-owned allowlist and `build_requests() -> list[ScrapeRequest]`.
- Produces: revised `WingoFlightsAdapter.build_requests() -> list[ScrapeRequest]` from route registry instead of the old single national page.
- Produces: default enabled adapters in exact order `clicair`, `satena`, `jetsmart`, `wingo`, `ghl_porton_medellin`, `alkilautos_national_medellin`.
- Produces default configuration `TARGET_OFFERS_PER_DIRECTION=10` and `MAX_ROUTE_CONCURRENCY_PER_SOURCE=2`.
- LATAM adapter may remain importable for historical evidence, but `latam` is absent from default enabled sources, source-health totals and productive flow scheduling.

- [ ] **Step 1: Write failing route-registry tests**

Update `tests/test_flight_route_registry.py` to keep existing CLIC/SATENA exact route assertions and add exact JetSMART/Wingo keys. Assert no route is automatically reversed.

JetSMART seed routes:
- `BOG→SMR` `https://jetsmart.com/ofertas/es-co/vuelos-desde-bogota-a-santa-marta`
- `SMR→BOG` `https://jetsmart.com/ofertas/es-co/vuelos-desde-santa-marta-a-bogota`
- `MDE→SMR` `https://jetsmart.com/ofertas/es-co/vuelos-desde-medellin-a-santa-marta`
- `CLO→SMR` `https://jetsmart.com/ofertas/es-co/vuelos-desde-cali-a-santa-marta`
- `CTG→BOG` `https://jetsmart.com/ofertas/es-co/vuelos-desde-cartagena-de-indias-a-bogota`
- `CTG→MDE` `https://jetsmart.com/ofertas/es-co/vuelos-desde-cartagena-de-indias-a-medellin`
- `CTG→CLO` `https://jetsmart.com/ofertas/es-co/vuelos-desde-cartagena-de-indias-a-cali`
- `MDE→CTG` `https://jetsmart.com/ofertas/es-co/vuelos-desde-medellin-a-cartagena-de-indias`

Wingo seed routes:
- `BOG→SMR` `https://www.wingo.com/es/vuelos-de-bogota-a-santa-marta`
- `MDE→SMR` `https://www.wingo.com/es/vuelos-de-medellin-a-santa-marta`
- `CTG→BOG` `https://www.wingo.com/es/vuelos-de-cartagena-a-bogota`
- `BOG→MDE` `https://www.wingo.com/es/vuelos-de-bogota-a-medellin`
- `MDE→BOG` `https://www.wingo.com/es/vuelos-de-medellin-a-bogota`

For all productive sources assert HTTPS, exact source-owned hostname, `acquisition_mode == "http"`, and `origin != destination`.

- [ ] **Step 2: Run registry tests to verify RED**

Run: `python -m pytest tests/test_flight_route_registry.py tests/test_source_adapters.py tests/test_runner_sources.py -q`

Expected: FAIL because JetSMART does not exist, Wingo still uses one national browser-style request, and LATAM is still default-enabled.

- [ ] **Step 3: Implement route constants and `JetSmartFlightsAdapter`**

`JetSmartFlightsAdapter.allowed_hosts = {"jetsmart.com", "www.jetsmart.com"}` and every request uses `ready_selector="table"`, query keys `origin`, `destination`, `route_key`, and `transport="http"` through `RouteSpec.acquisition_mode`.

- [ ] **Step 4: Convert Wingo to registry-backed HTTP requests**

`WingoFlightsAdapter.allowed_hosts = {"wingo.com", "www.wingo.com"}`; remove the productive dependence on `/es/vuelos-nacionales` and `text=Comprar`. Preserve the legacy parser path for old snapshots only.

- [ ] **Step 5: Change productive defaults**

Set `.env.example` to include exactly these flight defaults:

`SCRAPE_ENABLED_SOURCES=clicair,satena,jetsmart,wingo,ghl_porton_medellin,alkilautos_national_medellin`
`TARGET_OFFERS_PER_DIRECTION=10`
`MAX_ROUTE_CONCURRENCY_PER_SOURCE=2`

Update `ingestion/sources/registry.py` so `get_adapter("jetsmart")` works and default `get_enabled_adapters()` yields the six sources above in order. LATAM must not be in `_DEFAULT_ENABLED`.

- [ ] **Step 6: Run source-pool tests to verify GREEN**

Run: `python -m pytest tests/test_flight_route_registry.py tests/test_source_adapters.py tests/test_runner_sources.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ingestion/sources/flight_routes.py ingestion/sources/flights_jetsmart.py ingestion/sources/flights_wingo.py ingestion/sources/registry.py .env.example tests/test_flight_route_registry.py tests/test_source_adapters.py tests/test_runner_sources.py
git commit -m "feat: replace latam with public flight source pool"
```

---

### Task 2: Semantic flight-table parser and date normalization

**Files:**
- Create: `tests/fixtures/scraping/jetsmart.html`
- Create: `tests/fixtures/scraping/wingo_semantic.html`
- Modify: `ingestion/parsers/flights.py`
- Modify: `ingestion/normalization/common.py`
- Modify: `ingestion/sources/flights_clic.py`
- Modify: `ingestion/sources/flights_satena.py`
- Modify: `ingestion/sources/flights_jetsmart.py`
- Modify: `ingestion/sources/flights_wingo.py`
- Test: `tests/test_parsers.py`
- Test: `tests/test_normalization.py`
- Test: `tests/test_source_adapters.py`

**Interfaces:**
- Produces: `HEADER_ALIASES` mapping common fields to accepted folded headers: origin=`Desde`; destination=`Hasta|A|Hacia`; trip type=`Tipo de vuelo|Tipo de tarifa`; date=`Fecha|Fechas`; price=`Precio`.
- Produces: `is_one_way_trip_type(value: str | None) -> bool`, true for values beginning with folded `solo ida` such as `Solo ida` and `Solo ida/Económica`.
- `parse_flights(html, metadata)` continues returning raw dictionaries with `airline`, airport names/codes, `trip_type`, `travel_date`, `price_text`, and null departure/arrival timestamps.
- `iso_date(value)` gains support for Spanish weekday/date forms such as `sáb 24 oct 2026` without weakening existing `%d/%m/%Y`, `%Y-%m-%d`, and `Oct 12, 2026` support.

- [ ] **Step 1: Add failing semantic-parser fixtures/tests**

JetSMART fixture must contain a semantic table using `Desde | A | Tipo de tarifa | Fechas | Precio`, including `Bogotá (BOG) | Santa Marta (SMR) | Solo ida | sáb 24 oct 2026 | desde COP 158.230*...`.

Wingo fixture must contain `Desde | Hacia | Tipo de tarifa | Fechas | Precio`, including a one-way row such as `Medellín (MDE) | Santa Marta (SMR) | Solo ida/Económica | 28/01/2027 | Desde COP198,540*...`.

Tests assert:
- JetSMART resolves to `BOG→SMR`, airline `JetSMART`, exact date text and COP price text.
- Wingo resolves to `MDE→SMR`, airline `Wingo`.
- `A`, `Hacia` and the existing `Hasta` all map to destination.
- rows missing a concrete date or concrete COP price are ignored.
- duplicate semantic rows deduplicate by source/airline/origin/destination/date/price/type and therefore cannot inflate direction coverage;
- a fixture with more than five valid rows returns all valid rows, proving there is no hidden five-offer parser cap.
- CLIC and SATENA current fixtures remain unchanged and green.

- [ ] **Step 2: Add failing date-normalization tests**

In `tests/test_normalization.py`, assert `iso_date("sáb 24 oct 2026") == "2026-10-24"`, `iso_date("mié 18 nov 2026") == "2026-11-18"`, and existing date formats still normalize identically.

- [ ] **Step 3: Run parser/normalizer tests to verify RED**

Run: `python -m pytest tests/test_parsers.py tests/test_normalization.py tests/test_source_adapters.py -q`

Expected: FAIL on JetSMART/Wingo alias/date cases before implementation.

- [ ] **Step 4: Implement header alias resolution**

Replace fixed `EXPECTED_HEADERS`/fixed-index lookup with semantic field resolution. A table is eligible only when origin, destination, date and price aliases are all present; trip type is preserved when present. Do not parse monthly summary cards outside a qualifying offer table.

- [ ] **Step 5: Implement one-way filter and Spanish textual dates**

Use `is_one_way_trip_type()` in all four active flight adapters so `Solo ida` and `Solo ida/Económica` are accepted while round-trip rows do not enter the one-way catalog. Extend `iso_date()` only for the approved exact-day Spanish pattern.

- [ ] **Step 6: Preserve legacy Wingo regex fallback**

Keep `_extract_legacy_wingo()` only after semantic table extraction returns no rows, so historical snapshots remain parseable but new pages prefer the table contract.

- [ ] **Step 7: Run parser/normalizer suite to verify GREEN**

Run: `python -m pytest tests/test_parsers.py tests/test_normalization.py tests/test_source_adapters.py -q`

Expected: PASS including CLIC/SATENA regression tests.

- [ ] **Step 8: Commit**

```bash
git add ingestion/parsers/flights.py ingestion/normalization/common.py ingestion/sources/flights_clic.py ingestion/sources/flights_satena.py ingestion/sources/flights_jetsmart.py ingestion/sources/flights_wingo.py tests/fixtures/scraping/jetsmart.html tests/fixtures/scraping/wingo_semantic.html tests/test_parsers.py tests/test_normalization.py tests/test_source_adapters.py
git commit -m "feat: parse semantic airline offer tables"
```

---

### Task 3: Robots-aware non-retry path and resilient multi-route orchestration

**Files:**
- Modify: `ingestion/flow.py`
- Modify: `ingestion/collectors/http_collector.py` only if needed to expose the existing policy distinction cleanly.
- Test: `tests/test_http_collector.py`
- Test: `tests/test_scrape_flow.py`
- Test: `tests/test_scrape_persistence.py`
- Test: `tests/test_scrape_security.py`
- Create: `tests/test_distributed_runtime_contract.py`
- Modify: `ingestion/requirements.txt` or the existing shared ingestion dependency file used by scheduler/workers/runner.
- Modify: Prefect server image/configuration in `docker-compose.yml` or its referenced dependency file so server/client versions match.

**Interfaces:**
- `collect_http()` continues raising `SourceBlockedError` before calling `httpx.get` when `robots_allowed(url)` is false.
- `acquire_snapshot()` continues returning `STALE_FALLBACK` for an acceptable real stale snapshot; without fallback, a policy denial remains distinguishable as non-transient instead of becoming an indistinguishable retryable timeout-style error.
- Batch state gains a boolean classification such as `non_retryable`/`policy_blocked` that `_prefect_collect()` can honor without raising into Prefect retry machinery.
- Transient DNS/timeout/429/5xx paths retain bounded retry/backoff behavior.

- [ ] **Step 1: Write failing no-network-on-robots test**

In `tests/test_http_collector.py`, monkeypatch `robots_allowed` false and an `httpx.get` spy. Assert `SourceBlockedError` is raised, `httpx.get` call count is zero, and no retry sleep is invoked.

- [ ] **Step 2: Write failing acquisition classification test**

In `tests/test_scrape_flow.py`, cover a denied request with no prior snapshot and assert the flow can identify it as policy-denied/non-retryable; preserve the existing test proving a valid stale real snapshot may still yield `STALE_FALLBACK`.

- [ ] **Step 3: Write failing all-routes-blocked Prefect-stage test**

For a multi-route adapter where every request raises policy denial, assert `_prefect_collect()` returns/propagates a terminal unavailable state without raising a retry-triggering exception. The resulting `SourceRunResult` is `SOURCE_UNAVAILABLE` with a compact diagnostic containing `ROBOTS_DISALLOWED` once, not one repeated stack message per route.

- [ ] **Step 4: Write partial-route regression test**

One blocked/transient route among successful requests must preserve successful captures and persist them. Only successfully observed empty routes may deactivate old rows; unseen failed routes remain active.

- [ ] **Step 5: Write failing bounded-concurrency test**

Instrument a source with at least four independent route requests. Assert no more than `MAX_ROUTE_CONCURRENCY_PER_SOURCE=2` acquisitions overlap, all routes eventually complete, and one slow route does not serialize the entire source.

- [ ] **Step 6: Write environment/version contract tests**

Assert ingestion requirements pin Dask/Distributed consistently for runner/scheduler/workers and Prefect server/client to the same version. Add a static contract that `ingestion/snapshots/__init__.py`, `manager.py`, and `metadata.py` exist in source and are included by the shared ingestion Docker build context.

- [ ] **Step 7: Run policy/flow tests to verify RED**

Run: `python -m pytest tests/test_http_collector.py tests/test_scrape_flow.py tests/test_scrape_persistence.py tests/test_scrape_security.py tests/test_distributed_runtime_contract.py -q`

Expected: FAIL on non-retry policy classification/compact diagnostics before implementation.

- [ ] **Step 8: Implement non-transient policy handling and bounded per-source route scheduling**

Separate `SourceBlockedError` from transient acquisition failures after stale-fallback evaluation. Schedule independent route acquisitions through a per-source semaphore capped at `MAX_ROUTE_CONCURRENCY_PER_SOURCE` (default 2). Record `ROBOTS_DISALLOWED` as the route diagnostic and mark an all-policy-blocked source non-retryable. `_prefect_collect()` must not raise for that terminal policy state, allowing parse/normalize/persist tasks to short-circuit cleanly and the flow to continue other sources. Pin Prefect server/client to one exact version and keep Dask/Distributed dependencies shared by scheduler, workers and runner.

- [ ] **Step 9: Add JetSMART and renamed Wingo Prefect tasks**

Expose independent collection tasks named `collect JetSMART flights` and `collect Wingo flights`; remove LATAM from the default scheduling path. Keep task retries available for transient source failures, but policy-blocked state must not trigger them.

- [ ] **Step 10: Run policy/flow suite to verify GREEN**

Run: `python -m pytest tests/test_http_collector.py tests/test_scrape_flow.py tests/test_scrape_persistence.py tests/test_scrape_security.py tests/test_snapshot_cache.py tests/test_distributed_runtime_contract.py -q`

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add ingestion/flow.py ingestion/collectors/http_collector.py ingestion/requirements.txt docker-compose.yml tests/test_http_collector.py tests/test_scrape_flow.py tests/test_scrape_persistence.py tests/test_scrape_security.py tests/test_distributed_runtime_contract.py
git commit -m "fix: stop retrying robots-disallowed flight routes"
```

---

### Task 4: Ten-offer direction coverage read model and truthful availability states

**Files:**
- Create: `backend/gateway/route_coverage.py`
- Create: `tests/test_route_coverage.py`
- Modify: `backend/gateway/travel_logic.py` only to export/reuse airport-to-tourist-city mapping.

**Interfaces:**
- Produces constant `TARGET_OFFERS_PER_DIRECTION = 10` loaded from environment with a safe default of 10 and clamped to 1..10 for the public contract.
- Produces `select_direction_offers(rows: list[dict], *, origin: str, destination: str, limit: int = 10) -> tuple[dict, ...]`.
- Produces `DirectionCoverage(status: str, visible_count: int, raw_count: int, offers: tuple[dict, ...], sources_checked: int, sources_available: int)`.
- Produces `build_direction_coverage(rows, *, origin, destination, source_health, expected_sources, limit=10) -> DirectionCoverage`.
- Produces `supported_city_pairs() -> tuple[tuple[str, str], ...]` containing exactly the 20 ordered pairs across `BOG`, `MDE`, `CLO`, `CTG`, `SMR`, excluding same-city pairs.
- Airport rows map through the existing tourist-city resolver so `MDE` and `EOH` both count as Medellín while returned offers preserve their real airport codes.

- [ ] **Step 1: Write failing max-10 selection tests**

Provide 14 active real rows across CLIC/SATENA/JetSMART/Wingo for one tourist direction. Assert `raw_count == 14`, `visible_count == 10`, exactly ten rows are returned and input rows are not mutated or deleted. Sort is deterministic by `(travel_date, price, source, id)`.

- [ ] **Step 2: Write failing deduplication and multi-source tests**

Assert an exact duplicate `(source, origin, destination, travel_date, price, trip_type)` counts once, while two different sources or prices on the same date remain separate valid offers.

- [ ] **Step 3: Write failing Medellín consolidation tests**

Rows `BOG→EOH` and `BOG→MDE` both satisfy tourist direction `BOG→MDE`; original airport fields remain unchanged in returned offers. Assert `supported_city_pairs()` returns exactly 20 ordered pairs and includes zero-offer pairs such as `BOG→SMR`.

- [ ] **Step 4: Write failing availability-state tests**

Assert:
- 10+ raw real offers -> `AVAILABLE`, visible 10;
- 1–9 -> `PARTIAL`;
- zero plus all expected active sources healthy/observed -> `NO_OFFERS`;
- zero plus any required source `SOURCE_UNAVAILABLE`/`NOT_RUN` -> `SOURCE_UNAVAILABLE`.

Also assert user-facing state logic never manufactures an offer and never labels zero results as sold out.

- [ ] **Step 5: Run coverage tests to verify RED**

Run: `python -m pytest tests/test_route_coverage.py tests/test_travel_logic.py tests/test_travel_network.py -q`

Expected: FAIL because the coverage read model does not exist.

- [ ] **Step 6: Implement the pure coverage read model**

Operate only on supplied rows and source-health summaries. Do not mutate PostgreSQL, deactivate excess rows, infer routes, fabricate dates/prices or make network calls.

- [ ] **Step 7: Run coverage tests to verify GREEN**

Run: `python -m pytest tests/test_route_coverage.py tests/test_travel_logic.py tests/test_travel_network.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/gateway/route_coverage.py backend/gateway/travel_logic.py tests/test_route_coverage.py tests/test_travel_logic.py tests/test_travel_network.py
git commit -m "feat: cap visible route coverage at ten real offers"
```

---

### Task 5: Pure one-stop suggested connection engine

**Files:**
- Create: `backend/gateway/flight_connections.py`
- Create: `tests/test_flight_connections.py`
- Modify: `backend/gateway/travel_logic.py` only if a reusable airport→tourist-city helper must be exported; do not change package calculation semantics.

**Interfaces:**
- Consumes: active flight dictionaries with fields `id`, `origin`, `destination`, `travel_date`, `price`, `currency`, `source`, plus normal Flight provenance fields.
- Produces:
  - `@dataclass(frozen=True) SuggestedConnectionCandidate` with `via: str`, `total_price: float`, `currency: str`, `legs: tuple[dict, dict]`.
  - `build_suggested_connections(outgoing_rows: list[dict], incoming_rows: list[dict], *, origin: str, destination: str, travel_date: str, limit: int = 10) -> tuple[SuggestedConnectionCandidate, ...]`.
- `origin`/`destination` are tourist city codes; airport rows map through existing `city_code_for_airport()` so `EOH` and `MDE` resolve to tourist city `MDE` without rewriting legs.

- [ ] **Step 1: Write failing happy-path connection test**

Given active same-date legs `CTG→BOG` and `BOG→SMR`, assert one candidate with `via="BOG"`, `stops=1` at GraphQL mapping time, two original legs, currency `COP`, and `total_price` equal to exact sum.

- [ ] **Step 2: Write failing safety-rule tests**

Assert the builder rejects:
- date mismatch;
- USD/non-COP leg;
- `via == origin` or `via == destination`;
- a pair where first-leg destination city differs from second-leg origin city;
- duplicate `(leg1.id, leg2.id)` combinations;
- same leg ID used twice.

Assert `EOH` and `MDE` may match each other as the same intermediate tourist city while each returned leg preserves its original airport code.

- [ ] **Step 3: Write failing ordering/limit test**

Provide more than ten valid candidates. Assert candidate result length is ten and sort key is `(total_price, via, leg1.source, leg2.source, leg1.id, leg2.id)` for deterministic output.

- [ ] **Step 4: Run connection-engine tests to verify RED**

Run: `python -m pytest tests/test_flight_connections.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 5: Implement `build_suggested_connections()`**

Use only the supplied real rows. Do not query services, mutate rows, persist connections or infer missing data inside this pure module. Clamp internal candidate `limit` to `1..10`; GraphQL/UI later exposes only the best five suggestions.

- [ ] **Step 6: Run connection-engine and travel-logic tests to verify GREEN**

Run: `python -m pytest tests/test_flight_connections.py tests/test_travel_logic.py tests/test_travel_network.py -q`

Expected: PASS; existing `build_roundtrip_packages()` behavior remains unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/gateway/flight_connections.py backend/gateway/travel_logic.py tests/test_flight_connections.py tests/test_travel_logic.py tests/test_travel_network.py
git commit -m "feat: add one-stop suggested connection engine"
```

---

### Task 6: GraphQL 20-direction network, `flightAvailability`, `flightSearch`, and source health

**Files:**
- Modify: `backend/gateway/main.py`
- Modify: `schema.graphql`
- Create: `tests/test_source_health.py`
- Modify: `tests/test_graphql_scraping_contract.py`
- Modify: `tests/test_flight_routes_api.py` only if service-query contracts need an explicit regression.

**Interfaces:**
- Produces GraphQL:

```graphql
flightAvailability(origin: String!, destination: String!): FlightAvailabilityResult!
flightSearch(origin: String!, destination: String!, travelDate: String!, limit: Int = 20): FlightSearchResult!
```

- Produces Strawberry/GraphQL types equivalent to:
  - `FlightAvailabilityResult { origin, destination, dates }` with `FlightDateOption { travelDate, directOfferCount, connectionCandidateCount }`;
  - `FlightSearchResult { origin, destination, travelDate, status, availableCount, sourcesChecked, sourcesAvailable, directOffers, connections }`
  - `SuggestedConnection { via, stops, totalPrice, currency, legs, warning }`
- Warning is exactly `Verifica los horarios exactos con las aerolíneas.`
- Produces GraphQL `sourceHealth: SourceHealthSummary!` with active flight sources only:
  - `SourceHealthSummary { activeCount, totalCount, sources }`
  - `SourceHealthItem { source, status, available, itemsFound, finishedAt }`
- `available=True` only for latest statuses `SUCCESS`, `CACHED`, `STALE_FALLBACK`; missing run becomes `NOT_RUN`; raw `error_message` is never exposed.
- `travelNetwork.cities` always contains the five supported tourist cities and `travelNetwork.routes` contains all 20 ordered pairs with `coverageStatus`, `visibleOfferCount`, `rawOfferCount`, `sourcesChecked`, `sourcesAvailable` and existing direct/package capability fields. Zero-offer pairs stay searchable.

- [ ] **Step 1: Write failing schema contract tests**

Assert `schema.graphql` exposes `flightAvailability`, `FlightAvailabilityResult`, `FlightDateOption`, `flightSearch`, `FlightSearchResult`, `SuggestedConnection`, `sourceHealth`, and route coverage fields on `travelNetwork`; assert the exact fields above. Assert `travelNetwork` contains all five cities/20 pairs rather than filtering zero-offer pairs out. Assert `travelPackages` signatures are unchanged and do not mention `SuggestedConnection`.

- [ ] **Step 2: Write failing `flightAvailability` tests**

For a direct route, assert dates come only from active real direct offers and are capped to 10 date options. For a pair with no direct rows but valid same-date one-stop legs, assert that date appears with `directOfferCount=0` and positive `connectionCandidateCount`. For a pair with neither direct nor valid connection data, assert `dates == []`.

`flightAvailability` must never synthesize a date from min/max ranges or current date.

- [ ] **Step 3: Write failing direct-first resolver test**

Mock Flight Service calls. For `BOG→SMR` on a selected date where the direct request returns rows, assert `flightSearch` returns at most 10 selected direct rows and does not issue outgoing/incoming graph-expansion requests; `connections == []`.

- [ ] **Step 4: Write failing one-stop resolver test**

When the direct request returns `[]`, assert resolver fetches:
- outgoing real offers from the origin airport set for the exact date;
- incoming real offers to the destination airport set for the exact date;
then calls `build_suggested_connections(limit=10)` and returns at most the best five suggestions.

Assert a date with no usable rows returns both arrays empty rather than GraphQL error and maps zero-result status from route/source health as `NO_OFFERS` or `SOURCE_UNAVAILABLE`, never a fabricated direct offer.

- [ ] **Step 5: Write failing source-health tests**

Using monkeypatched DB rows, verify:
- only `clicair`, `satena`, `jetsmart`, `wingo` count toward `totalCount=4`;
- success/cache/stale count as available;
- unavailable and missing latest rows do not;
- LATAM never increases total count;
- result contains no stack trace/error-message field.

- [ ] **Step 6: Run GraphQL/health tests to verify RED**

Run: `python -m pytest tests/test_graphql_scraping_contract.py tests/test_source_health.py tests/test_route_coverage.py tests/test_flight_connections.py -q`

Expected: FAIL because the new queries/types/resolvers do not exist.

- [ ] **Step 7: Implement `travelNetwork`, `flightAvailability`, and direct-first `flightSearch`**

Build the 20-pair `travelNetwork` through Task 4 coverage data. Implement `flightAvailability` from real direct rows plus same-date one-stop candidates only. Resolve tourist locations through `resolve_location()`. For `flightSearch`, first call Flight Service `/flights` with origin/destination airport sets and exact `travel_date`. Pass returned direct rows through `select_direction_offers(..., limit=10)` before GraphQL mapping. Only when that returns empty, request same-date outgoing and incoming pools with service limit 100 and pass them to the pure connection engine.

- [ ] **Step 8: Implement `sourceHealth`**

Query latest `scrape_runs` per active flight source with parameterized SQL. Fill missing sources as `NOT_RUN`; map status to boolean without forwarding raw errors.

- [ ] **Step 9: Update `schema.graphql` and run GREEN**

Run: `python -m pytest tests/test_graphql_scraping_contract.py tests/test_source_health.py tests/test_route_coverage.py tests/test_flight_connections.py tests/test_travel_logic.py tests/test_travel_network.py -q`

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/gateway/main.py backend/gateway/route_coverage.py backend/gateway/flight_connections.py schema.graphql tests/test_graphql_scraping_contract.py tests/test_source_health.py tests/test_flight_connections.py tests/test_flight_routes_api.py
git commit -m "feat: expose flight search and source health"
```

---

### Task 7: React ten-offer coverage, direct/connection UX, and source-health banner

**Files:**
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/styles.css`
- Modify: `tests/test_frontend_multi_city_contract.py`
- Modify: `tests/test_frontend_roundtrip_contract.py`
- Modify: `tests/test_graphql_scraping_contract.py`

**Interfaces:**
- Consumes: `travelNetwork` with all five cities/20 pairs, existing `travelAvailability` for packages, new `flightAvailability` for flight mode, `flightSearch`, `travelPackages`, and `sourceHealth`.
- Keeps origin/destination derived from the five supported cities in `travelNetwork`, excludes only same-city destination, and keeps flight-mode date chips derived only from `flightAvailability`. Package-mode dates remain derived from direct `travelAvailability`.
- Flight mode state holds `directOffers` (maximum 10), `connections` (maximum 5 shown) and route coverage state separately; package mode remains direct-only.
- Source-health banner shows `Fuentes activas: X de 4` and optional generic warning `Algunas fuentes no estuvieron disponibles durante la última actualización.` without raw diagnostic text.

- [ ] **Step 1: Replace flight-mode contract test with `flightSearch`**

Assert frontend queries `flightAvailability(origin:$origin,destination:$destination)` before date selection, then:
`flightSearch(origin:$origin,destination:$destination,travelDate:$travelDate,limit:50)`
and requests direct-offer provenance plus connection `via/stops/totalPrice/currency/warning/legs` provenance.

- [ ] **Step 2: Add failing connection UX tests**

Assert all five cities remain selectable even for zero-direct pairs such as Bogotá→Santa Marta, and assert literal UI copy exists:
- `10 ofertas disponibles`
- `Encontramos menos opciones de lo habitual para esta ruta.`
- `No encontramos vuelos disponibles actualmente.`
- `No pudimos comprobar completamente esta ruta porque algunas fuentes no estuvieron disponibles.`
- `No hay ofertas directas para esta fecha. Estas son conexiones sugeridas.`
- `No encontramos vuelos ni conexiones de una escala para esta fecha.`
- `Conexiones sugeridas`
- `Verifica los horarios exactos con las aerolíneas.`

Assert connection cards render both legs, intermediate city, one scale, total COP price, and never contain a checkout/package action.

- [ ] **Step 3: Add failing health/filter tests**

Assert frontend queries `sourceHealth`, renders `Fuentes activas:` and offers simple controls for result type (`Todos`, `Directos`, `Conexiones`) and airline when direct/leg sources are present. Keep `Menor precio` as the deterministic price sort; selected date remains fixed by the date chip.

- [ ] **Step 4: Add package-isolation regression tests**

Assert `searchMode === 'packages'` still calls only `travelPackages`; `SuggestedConnection`/connection state is not passed to checkout; package destinations continue requiring `packageAvailable`.

- [ ] **Step 5: Run frontend contract tests to verify RED**

Run: `python -m pytest tests/test_frontend_multi_city_contract.py tests/test_frontend_roundtrip_contract.py tests/test_graphql_scraping_contract.py -q`

Expected: FAIL because frontend still uses `flightOffers` and has no connection/health UX.

- [ ] **Step 6: Implement `flightSearch` rendering**

For flight mode, origin is any supported city and destination is any other supported city. Load real date chips from `flightAvailability`; when there are no date options, render route status immediately and never show a free date input. Then:
- direct offers present → render no more than 10 direct cards and leave connection section empty;
- no direct + connections present → render the exact suggested-connection notice and cards;
- neither → render the `NO_OFFERS` or `SOURCE_UNAVAILABLE` message according to server status, with no claim that seats were definitely sold out.

Each leg continues displaying airline/source/travel date/provenance; connection card shows `1 escala · <via>` and the server warning.

- [ ] **Step 7: Implement source health and filters**

Fetch `sourceHealth` during bootstrap independently from `travelNetwork`; a health-query failure must not block route searching. Render only sanitized status counts. Apply client-side type/airline/price filtering to already-returned search results; do not issue arbitrary new scraper requests.

- [ ] **Step 8: Run frontend contracts and build**

Run: `python -m pytest tests/test_frontend_multi_city_contract.py tests/test_frontend_roundtrip_contract.py tests/test_graphql_scraping_contract.py -q`

Expected: PASS.

If `frontend/node_modules` is available, also run: `npm --prefix frontend run build`

Expected: exit 0. If dependencies are intentionally absent in the clean source tree, record the limitation and verify the build later inside the Docker frontend build stage instead of committing `node_modules`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/main.jsx frontend/src/styles.css tests/test_frontend_multi_city_contract.py tests/test_frontend_roundtrip_contract.py tests/test_graphql_scraping_contract.py
git commit -m "feat: show direct flights and suggested connections"
```

---

### Task 8: Coverage evidence, distributed-runtime regression, and clean release ZIP

**Files:**
- Create: `docs/FLIGHT_SOURCE_POOL_CONNECTIONS.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/COMPLIANCE.md`
- Modify: `docs/GRAPHQL.md`
- Modify: `docs/DEMO_GUIDE.md`
- Modify: `scripts/demo_validation.py`
- Modify: `scripts/scraping_study.sql`
- Modify: `scripts/verify_project.py`
- Modify: `tests/test_demo_validation_contract.py`
- Modify: `tests/test_docs_real_scraping_contract.py`
- Modify: `tests/test_compose_scraping_contract.py`

**Interfaces:**
- Demo proves four active flight sources are configured, LATAM is documented as disabled by policy, `travelNetwork` is database-derived, `flightSearch` can demonstrate a direct result and a suggested connection when catalog data supports one, and packages remain direct-only.
- Study SQL compares source/routing coverage without creating or mutating catalog rows.
- Static verifier rejects reintroduction of LATAM into default `SCRAPE_ENABLED_SOURCES`, browser transport for active flight sources, free date inputs, filtering zero-offer city pairs out of the supported 20-direction network, mock/provider runtime dependencies, and connection checkout leakage.

- [ ] **Step 1: Write failing documentation/demo/static contracts**

Tests assert docs and demo name all four active sources, state LATAM `ROBOTS_DISALLOWED`/disabled, explain suggested connections are not schedule-guaranteed, and keep GHL/Alkilautos package scope explicit.

- [ ] **Step 2: Extend `scripts/scraping_study.sql`**

Add read-only result sets for:
- active offers/routes by source;
- coverage across `BOG/MDE/EOH/CLO/CTG/SMR`;
- all 20 directed tourist-city pairs with raw count, visible count capped at 10 and status;
- counts of `AVAILABLE`, `PARTIAL`, `NO_OFFERS`, `SOURCE_UNAVAILABLE`;
- direct tourist-city pairs;
- pairs lacking a direct edge but possessing at least one one-stop city path from active rows;
- min/avg/max direct prices by source/route;
- latest `scrape_runs` status and snapshot counts by source;
- baseline comparison: 77 active flight rows, 10 directed routes, 5 bidirectional pairs before JetSMART/Wingo.

The SQL may identify graph-connectable pairs, but must label them candidates and must not claim schedule feasibility.

- [ ] **Step 3: Update dynamic demo validation**

`demo_validation.py` must not hardcode one specific connection as guaranteed. It should:
1. query `travelNetwork` and confirm five cities plus 20 directed pairs;
2. choose an available direct route, query `flightAvailability`, then use one returned date for `flightSearch` direct demonstration;
3. inspect `flightAvailability` for a pair with no direct offer but a valid same-date one-stop candidate and demonstrate it when one exists;
4. report a clear SKIP/NOT AVAILABLE message when current external data has no connection candidate, rather than fabricate one;
5. demonstrate `travelPackages` only for a `packageAvailable=true` route.

- [ ] **Step 4: Update documentation**

Document source allowlists, robots behavior, parser aliases, direct-first algorithm, exact connection warning, source-health semantics, and operator commands for `scrape_runs`, route coverage and GraphQL.

- [ ] **Step 5: Run documentation/static checks to verify GREEN**

Run: `python -m pytest tests/test_demo_validation_contract.py tests/test_docs_real_scraping_contract.py tests/test_compose_scraping_contract.py -q`

Run: `python scripts/verify_project.py`

The verifier must also assert five supported cities/20 searchable directions, presence of `flightAvailability`, `TARGET_OFFERS_PER_DIRECTION=10`, `MAX_ROUTE_CONCURRENCY_PER_SOURCE=2`, Prefect version parity, four active flight sources without LATAM, and presence of all three `ingestion/snapshots` package files.

Expected: all contract tests PASS and verifier reports all checks passing.

- [ ] **Step 6: Run full regression suite**

Run: `python -m pytest -q`

Expected: PASS with zero failures.

- [ ] **Step 7: Compile Python sources**

Run: `python -m compileall -q backend ingestion scripts`

Expected: exit 0.

- [ ] **Step 8: Validate frontend build in an available environment**

Preferred: `npm --prefix frontend ci && npm --prefix frontend run build`

If network/dependency installation is unavailable in the implementation harness, use the project Docker frontend build in the user's runtime as the final build verification and do not commit `node_modules` or `frontend/dist`.

- [ ] **Step 9: Commit evidence and verification changes**

```bash
git add docs scripts tests/test_demo_validation_contract.py tests/test_docs_real_scraping_contract.py tests/test_compose_scraping_contract.py
git commit -m "docs: document flight source pool and connections"
```

- [ ] **Step 10: Verify distributed image consistency when Docker is available**

Rebuild `dask-scheduler`, `dask-worker-1`, `dask-worker-2`, and `ingestion-runner` from the same ingestion context. Verify in each runtime:
- `import ingestion.snapshots`;
- identical `dask`, `distributed`, `cloudpickle` versions;
- Prefect server/client pin parity;
- Dask smoke task returns `42`;
- remote worker can import `ingestion.snapshots.manager`.

If Docker is unavailable in the implementation harness, static contracts remain mandatory and these exact commands move to operator validation without claiming runtime success.

- [ ] **Step 11: Build release ZIP from versioned files only**

Create `WanderSync_Travel_Solutions_SOURCE_POOL_10_OFFER_COVERAGE.zip` from the committed tree. Exclude `.git`, `.env`, `.pytest_cache`, `__pycache__`, `.superpowers`, `.worktrees`, runtime `/data/snapshots`, `node_modules`, `frontend/dist`, virtualenvs and OS/editor junk.

- [ ] **Step 12: Extract ZIP into a fresh directory and verify the artifact**

On the extracted artifact run:
- `python -m pytest -q`
- `python scripts/verify_project.py`
- `python -m compileall -q backend ingestion scripts`
- archive hygiene scan proving excluded paths are absent.

If frontend dependencies are available, also run its production build from the extracted artifact.

- [ ] **Step 13: Record release hash**

Run `sha256sum WanderSync_Travel_Solutions_SOURCE_POOL_10_OFFER_COVERAGE.zip` and include the exact SHA-256 in the handoff.

---

## Expected Operator Validation After Handoff

The implementation environment cannot claim external runtime success until the user executes the real stack. The release handoff must ask for these runtime validations without weakening test completion:

1. `docker compose build --no-cache && docker compose up -d`
2. confirm two Dask workers plus PostgreSQL/Prefect are healthy;
3. run one real ingestion cycle;
4. inspect latest `scrape_runs`, route counts by source and the 20-direction coverage report;
5. query GraphQL `travelNetwork`, `sourceHealth`, one `AVAILABLE/PARTIAL` route and any zero-result route to verify `NO_OFFERS` vs `SOURCE_UNAVAILABLE`;
6. confirm no direction exposes more than 10 direct offers, connections show at most five suggestions, and packages still use only direct outbound/return flights.

A current external source returning no offers is a valid runtime state. The application must display only what the active real catalog supports and must never fill the gap with invented data.
