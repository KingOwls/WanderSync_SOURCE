# Flexible Round-Trip Travel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend WanderSync so real CLIC/SATENA Bogotá ↔ Medellín offers drive up to eight outbound dates, eight return dates, valid 1–14 night combinations, round-trip package pricing, and a two-flight SAGA checkout.

**Architecture:** Keep the validated scraping stack intact and extend the CLIC/SATENA adapters from one request to two directional requests per source. Add an isolated city/airport query resolver and availability engine in the GraphQL layer, then carry two explicit flight legs through package results, checkout, persistence, compensation, and the React UI.

**Tech Stack:** Python 3.12, FastAPI, Strawberry GraphQL, PostgreSQL, Prefect, Dask, HTTPX, React/Vite, Docker Compose, pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-flexible-roundtrip-travel-design.md`

## Global Constraints

- CLIC and SATENA each scrape both `BOG → EOH` and `EOH → BOG`; Wingo remains disabled by default.
- Persist only real `Solo ida` rows published by the source; never invent dates, prices, airport codes, or availability.
- Return at most 8 distinct outbound dates and 8 distinct return dates; fewer real dates is valid.
- User-facing Medellín remains `MDE`; flight matching resolves `MDE` to `[MDE, EOH]` without rewriting scraped rows.
- Valid trips require `returnDate > departureDate` and 1–14 nights inclusive.
- Availability returns at most 12 recommendations sorted by lowest flight total, then departure date, then return date.
- Package total is `outbound + return + hotel × nights + car × nights`; every participating price must be COP.
- Checkout reserves and compensates both flight legs using local academic holds only; it must never claim to book CLIC or SATENA externally.
- Existing GHL and Alkilautos collection behavior must remain unchanged.
- Database migrations must remain idempotent for existing PostgreSQL volumes.

## Review Focus

- One direction succeeds while the opposite route fails: keep valid real rows and do not deactivate them because another request failed; Task 1 adds this regression.
- `MDE` user selection with only `EOH` scraped rows: availability and packages must resolve the city without modifying stored provenance; Tasks 2–4 test it.
- Exactly 1-night and 14-night trips are valid while 0-night and 15-night trips are rejected; Tasks 3–4 test the boundaries.
- Return-flight hold failure after outbound hold success must compensate the outbound hold and leave the order cancelled/not charged; Task 5 tests the SAGA boundary.
- Fewer than eight real dates and one-airline-only availability must still produce a correct subset/recommendation list; Task 3 tests both cases.

---

### Task 1: Bidirectional flight source refresh

**Files:**
- Modify: `ingestion/sources/flights_clic.py:1-45`
- Modify: `ingestion/sources/flights_satena.py:1-45`
- Modify: `ingestion/flow.py:128-250`
- Modify: `tests/test_source_adapters.py`
- Modify: `tests/test_scrape_flow.py`
- Modify: `tests/test_scrape_persistence.py`

**Interfaces:**
- Consumes: existing `ScrapeRequest`, `AcquisitionDecision`, `SnapshotRef`, parser/normalizer and `persist_catalog()` contracts.
- Produces: each CLIC/SATENA adapter returns exactly two requests with metadata `direction=outbound|return`; `collect_source_batch(adapter_name: str) -> dict`; `parse_source_batch(state: dict) -> dict`; `normalize_source_batch(state: dict) -> dict`; one persistence call per source refresh containing rows from all successful directions.

- [ ] **Step 1: Write failing adapter tests for two directional requests.**

```python
def test_clic_and_satena_build_outbound_and_return_requests():
    for name in ("clicair", "satena"):
        requests = get_adapter(name).build_requests()
        assert [(r.metadata["origin"], r.metadata["destination"], r.metadata["direction"]) for r in requests] == [
            ("BOG", "EOH", "outbound"),
            ("EOH", "BOG", "return"),
        ]
        assert all(r.transport == "http" for r in requests)
```

- [ ] **Step 2: Run the adapter test and confirm RED.**

Run: `python -m pytest tests/test_source_adapters.py::test_clic_and_satena_build_outbound_and_return_requests -v`
Expected: FAIL because each adapter currently returns one request.

- [ ] **Step 3: Update both adapters to emit the approved outbound and return URLs.**

CLIC return URL: `https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-bogota`.
SATENA return URL: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-medellin-a-bogota`.
Keep `transport="http"`, `ready_selector="table"`, one-way filtering, and existing allowlists.

- [ ] **Step 4: Write failing batch-flow tests.**

Test names/assertions:
- `test_flight_source_batch_collects_every_request_and_registers_each_snapshot`: two requests produce two snapshot refs.
- `test_flight_source_batch_combines_rows_before_single_refresh`: persistence receives outbound + return rows in one call.
- `test_flight_source_batch_keeps_successful_direction_when_other_direction_fails`: one failed request plus one valid request persists the valid rows and records diagnostics instead of synthetic data.

- [ ] **Step 5: Run the flow tests and confirm RED.**

Run: `python -m pytest tests/test_scrape_flow.py tests/test_scrape_persistence.py -v`
Expected: FAIL because `_collect_stage()` currently uses `build_requests()[0]` and tracks only one snapshot.

- [ ] **Step 6: Implement source-batch collection/parsing/normalization in `ingestion/flow.py`.**

Use exact public interfaces:
- `collect_source_batch(adapter_name: str) -> dict`
- `parse_source_batch(state: dict) -> dict`
- `normalize_source_batch(state: dict) -> dict`

State contains `captures: list[tuple[AcquisitionDecision, SnapshotRef]]`, request-level errors, and combined rows. Register each real snapshot before parsing. A source run is usable when at least one directional request yields normalized rows.

- [ ] **Step 7: Change flight persistence to deactivate a source once and upsert the combined batch once.**

Keep hotel/car persistence unchanged. Ensure one successful direction cannot deactivate rows from the other successful direction during the same refresh.

- [ ] **Step 8: Run Task 1 suite.**

Run: `python -m pytest tests/test_source_adapters.py tests/test_scrape_flow.py tests/test_scrape_persistence.py -v`
Expected: PASS.

- [ ] **Step 9: Commit.**

```bash
git add ingestion/sources/flights_clic.py ingestion/sources/flights_satena.py ingestion/flow.py tests/test_source_adapters.py tests/test_scrape_flow.py tests/test_scrape_persistence.py
git commit -m "feat: ingest round-trip flight routes"
```

### Task 2: City-to-airport resolver and flight-service filters

**Files:**
- Create: `backend/gateway/travel_logic.py`
- Modify: `backend/flight_service/main.py:23-33`
- Create: `tests/test_travel_logic.py`
- Modify: `tests/test_graphql_scraping_contract.py`

**Interfaces:**
- Consumes: active rows from `flights` and user-facing city codes.
- Produces: `ResolvedLocation`, `resolve_location(code: str) -> ResolvedLocation`, and a backward-compatible `/flights` query supporting exact date plus comma-separated origin/destination airport sets.

- [ ] **Step 1: Write failing resolver tests.**

```python
def test_mde_resolves_to_medellin_airports_without_rewriting_city_code():
    resolved = resolve_location("MDE")
    assert resolved.city_code == "MDE"
    assert resolved.flight_airports == ("MDE", "EOH")
    assert resolved.service_city == "MDE"
```

Also test `BOG -> ("BOG",)` and unknown codes default to themselves.

- [ ] **Step 2: Run resolver tests and confirm RED.**

Run: `python -m pytest tests/test_travel_logic.py -v`
Expected: FAIL because `travel_logic.py` does not exist.

- [ ] **Step 3: Implement `ResolvedLocation` and `resolve_location`.**

Use a frozen dataclass. Initial mappings are exactly `BOG` and `MDE`; preserve uppercase input/output.

- [ ] **Step 4: Write failing flight-service filtering tests/contract assertions.**

Required behavior:
- existing `origin=BOG&destination=EOH` still works;
- `origins=EOH,MDE&destinations=BOG&travel_date=2026-10-19` queries only active exact-date rows;
- parameter lists are bounded and uppercased before SQL.

- [ ] **Step 5: Extend `/flights` backward-compatibly.**

Signature accepts existing `origin`, `destination`, `limit` plus optional `origins`, `destinations`, `travel_date`. Build parameterized `= ANY(%s)` predicates for list forms; never interpolate airport codes into SQL text.

- [ ] **Step 6: Run Task 2 suite.**

Run: `python -m pytest tests/test_travel_logic.py tests/test_graphql_scraping_contract.py -v`
Expected: PASS.

- [ ] **Step 7: Commit.**

```bash
git add backend/gateway/travel_logic.py backend/flight_service/main.py tests/test_travel_logic.py tests/test_graphql_scraping_contract.py
git commit -m "feat: resolve city airports for flight queries"
```

### Task 3: GraphQL travel availability and date recommendations

**Files:**
- Modify: `backend/gateway/travel_logic.py`
- Modify: `backend/gateway/main.py:243-330`
- Modify: `schema.graphql:1-40`
- Modify: `tests/test_travel_logic.py`
- Modify: `tests/test_graphql_scraping_contract.py`

**Interfaces:**
- Consumes: `resolve_location`, flight-service rows with `travel_date`, `price`, `currency`, `origin`, `destination`.
- Produces: `DateCombination`, `TravelAvailability`, `build_availability(...)`, GraphQL `travelAvailability(origin,destination,outboundLimit=8,returnLimit=8)`.

- [ ] **Step 1: Write failing pure availability tests.**

Cover:
- distinct dates sorted ascending and capped at 8;
- fewer than 8 dates returns the real subset;
- one airline only still works;
- no outbound rows returns empty outbound/return/combinations;
- outbound rows with no return after departure preserves outbound dates but returns no recommendations;
- 1-night and 14-night combinations valid; 0 and 15 invalid;
- at most 12 combinations, sorted by `lowest_flight_total`, then dates.

- [ ] **Step 2: Run pure tests and confirm RED.**

Run: `python -m pytest tests/test_travel_logic.py -v`
Expected: FAIL because availability builder/types are missing.

- [ ] **Step 3: Implement pure recommendation logic.**

Exact signatures:
- `build_availability(outbound_rows: list[dict], return_rows: list[dict], outbound_limit: int = 8, return_limit: int = 8, recommendation_limit: int = 12) -> AvailabilityResult`
- limits clamp to 1–8 for date lists and 1–12 for recommendations.
- only COP-priced rows participate in lowest-price calculations.

- [ ] **Step 4: Add Strawberry availability types and query.**

`TravelAvailability` fields: `origin`, `destination`, `airport_codes`, `outbound_dates`, `return_dates`, `outbound_offer_count`, `return_offer_count`, `combinations`.
`DateCombination` fields: `departure_date`, `return_date`, `nights`, `lowest_outbound_price`, `lowest_return_price`, `lowest_flight_total`.
The resolver fetches outbound and reverse-direction rows using resolved airport sets.

- [ ] **Step 5: Update `schema.graphql` and contract tests.**

Assert the schema exposes `travelAvailability`, both date arrays, airport codes and combination price fields, with default limits of 8.

- [ ] **Step 6: Run Task 3 suite.**

Run: `python -m pytest tests/test_travel_logic.py tests/test_graphql_scraping_contract.py -v`
Expected: PASS.

- [ ] **Step 7: Commit.**

```bash
git add backend/gateway/travel_logic.py backend/gateway/main.py schema.graphql tests/test_travel_logic.py tests/test_graphql_scraping_contract.py
git commit -m "feat: expose flexible round-trip availability"
```

### Task 4: Round-trip package generation

**Files:**
- Modify: `backend/gateway/main.py:92-330`
- Modify: `schema.graphql:1-40`
- Modify: `tests/test_travel_logic.py`
- Modify: `tests/test_graphql_scraping_contract.py`

**Interfaces:**
- Consumes: exact selected dates, resolved airport sets, active outbound/return flight rows, destination hotel/car rows.
- Produces: `TravelPackage(outbound_flight, return_flight, hotel, car, nights, flight_total, total)` and exact-date `travelPackages(...)` results.

- [ ] **Step 1: Write failing package-combination tests.**

Test a 3-night case containing CLIC/SATENA on both directions and assert mixed-airline pairs are allowed. Assert total equals `outbound + return + hotel*3 + car*3`, all inputs require COP, and results are sorted by total.

- [ ] **Step 2: Add boundary tests.**

`travelPackages` must reject 0 nights and 15 nights with `BAD_USER_INPUT`, accept 1 and 14, and return `[]` if either exact flight leg is unavailable.

- [ ] **Step 3: Run tests and confirm RED.**

Run: `python -m pytest tests/test_travel_logic.py tests/test_graphql_scraping_contract.py -v`
Expected: FAIL because `TravelPackage` still has one `flight`.

- [ ] **Step 4: Replace one-leg package model/resolver with two explicit legs.**

Fetch outbound and return flights concurrently with hotel/car requests. Reverse the airport sets for the return query. Cap package output at `min(max(limit,1),12)` and rank by full package total.

- [ ] **Step 5: Update GraphQL schema.**

Replace `flight` with `outboundFlight`, `returnFlight`, add `flightTotal`, preserve `hotel`, `car`, `nights`, `total`.

- [ ] **Step 6: Run Task 4 suite.**

Run: `python -m pytest tests/test_travel_logic.py tests/test_graphql_scraping_contract.py -v`
Expected: PASS.

- [ ] **Step 7: Commit.**

```bash
git add backend/gateway/main.py schema.graphql tests/test_travel_logic.py tests/test_graphql_scraping_contract.py
git commit -m "feat: build round-trip travel packages"
```

### Task 5: Two-flight SAGA checkout and idempotent order migration

**Files:**
- Modify: `infra/postgres/init.sql:153-210`
- Modify: `backend/order_service/main.py:12-195`
- Modify: `backend/gateway/main.py:92-110,230-240,448-480`
- Modify: `schema.graphql`
- Modify: `tests/test_saga_compensation.py`
- Modify: `tests/test_local_holds.py`
- Create: `tests/test_roundtrip_order_migration.py`

**Interfaces:**
- Consumes: round-trip package IDs, current local reservation endpoints and `CompensationStep`.
- Produces: checkout request fields `outbound_flight_id`, `return_flight_id`, `hotel_id`, `car_id`, `nights`; orders expose both flight IDs; authoritative total includes both flight prices.

- [ ] **Step 1: Write failing migration contract test.**

Assert `init.sql` idempotently adds `outbound_flight_id` and `return_flight_id` before queries use them, backfills `outbound_flight_id=flight_id` for historical rows when possible, leaves legacy `flight_id` available for compatibility, and makes new checkout code write both explicit leg IDs.

- [ ] **Step 2: Write failing authoritative-total test.**

Assert `_authoritative_total(outbound_id, return_id, hotel_id, car_id, nights)` sums both active flights plus hotel/car and rejects any inactive/missing component.

- [ ] **Step 3: Write failing SAGA compensation test for return-flight failure.**

Sequence must be outbound flight hold → return flight hold → hotel → car → billing. If return hold fails, outbound reservation is cancelled, order becomes `CANCELLED/NOT_CHARGED`, and no hotel/car/payment action runs.

- [ ] **Step 4: Run SAGA/migration tests and confirm RED.**

Run: `python -m pytest tests/test_saga_compensation.py tests/test_local_holds.py tests/test_roundtrip_order_migration.py -v`
Expected: FAIL because checkout/orders currently contain one `flight_id`.

- [ ] **Step 5: Implement idempotent database migration.**

Add nullable explicit leg columns with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`; backfill outbound from legacy `flight_id` only where valid. Do not delete historical orders merely because return ID is null. New orders write both explicit IDs. Update legacy cleanup predicates so provenance cleanup understands both columns.

- [ ] **Step 6: Implement two-leg checkout and compensation.**

Keep reservation service key `flight` for both remote calls, but record SAGA event steps as `outbound_flight` and `return_flight`. Store enough compensation data so both flight reservations cancel through the flight service in reverse order. Support failure injection values `outbound_flight`, `return_flight`, `hotel`, `car`, `billing`.

- [ ] **Step 7: Update Gateway booking/checkout GraphQL contracts.**

`Booking` exposes `outbound_flight_id`, `return_flight_id`, hotel/car IDs; `checkoutPackage` takes both flight IDs. Keep reading legacy `flight_id` only as an optional compatibility field if present in historical rows.

- [ ] **Step 8: Run Task 5 suite.**

Run: `python -m pytest tests/test_saga_compensation.py tests/test_local_holds.py tests/test_roundtrip_order_migration.py tests/test_graphql_scraping_contract.py -v`
Expected: PASS.

- [ ] **Step 9: Commit.**

```bash
git add infra/postgres/init.sql backend/order_service/main.py backend/gateway/main.py schema.graphql tests/test_saga_compensation.py tests/test_local_holds.py tests/test_roundtrip_order_migration.py tests/test_graphql_scraping_contract.py
git commit -m "feat: reserve both flight legs in saga"
```

### Task 6: Flexible-date React experience and round-trip cards

**Files:**
- Modify: `frontend/src/main.jsx:1-180`
- Modify: `frontend/src/styles.css`
- Create: `tests/test_frontend_roundtrip_contract.py`

**Interfaces:**
- Consumes: GraphQL `travelAvailability`, round-trip `travelPackages`, and two-flight `checkoutPackage`.
- Produces: route bootstrap from real scraped dates, up to 8 outbound date chips, valid return-date chips, recommended combinations, round-trip package cards, and two-leg checkout variables.

- [ ] **Step 1: Write failing frontend contract tests.**

Assert frontend:
- queries `travelAvailability(origin,destination,outboundLimit:8,returnLimit:8)`;
- no longer uses `tomorrow()` as the fallback bootstrap for package search;
- selects first recommended combination when available;
- renders outbound and return date recommendation controls;
- queries `outboundFlight` and `returnFlight` in packages;
- checkout sends both flight IDs;
- unsupported manual dates surface nearest real scraped choices instead of only the old generic empty message.

- [ ] **Step 2: Run frontend contract test and confirm RED.**

Run: `python -m pytest tests/test_frontend_roundtrip_contract.py -v`
Expected: FAIL against current one-flight UI.

- [ ] **Step 3: Implement availability bootstrap and route-change refresh.**

Use `travelAvailability` as the source of truth. If combinations exist, select the first combination. If not, preserve route selection and display the real available date subset/empty state without inventing dates.

- [ ] **Step 4: Implement date recommendation controls.**

Display up to 8 outbound dates. Once outbound is selected, show only return dates producing 1–14 nights. Keep native date inputs for manual selection and highlight/suggest nearest actual choices when unsupported.

- [ ] **Step 5: Implement round-trip result cards and checkout.**

Show both flight legs with airline/date/price/source, hotel/car per-night prices, nights, `flightTotal`, and package `total`. Update failure-demo controls to include `return_flight` or equivalent approved injection label.

- [ ] **Step 6: Run frontend tests/build.**

Run: `python -m pytest tests/test_frontend_roundtrip_contract.py tests/test_graphql_scraping_contract.py -v`
Expected: PASS.
Run: `cd frontend && npm test --if-present && npm run build`
Expected: exit 0.

- [ ] **Step 7: Commit.**

```bash
git add frontend/src/main.jsx frontend/src/styles.css tests/test_frontend_roundtrip_contract.py
git commit -m "feat: add flexible round-trip search ui"
```

### Task 7: Demo evidence, documentation, and final verification

**Files:**
- Modify: `scripts/demo_validation.py`
- Modify: `scripts/scraping_study.sql`
- Modify: `scripts/verify_project.py`
- Modify: `docs/GRAPHQL.md`
- Modify: `docs/SAGA.md`
- Modify: `docs/DEMO_GUIDE.md`
- Modify: `README.md`
- Create: `ROUNDTRIP_FLEXIBLE_DATES.md`
- Modify: `tests/test_demo_validation_contract.py`
- Modify: `tests/test_docs_real_scraping_contract.py`

**Interfaces:**
- Consumes: all completed round-trip APIs and database columns.
- Produces: reproducible commands/evidence proving bidirectional snapshots, 8-date availability behavior, mixed-airline package generation, and two-leg SAGA compensation.

- [ ] **Step 1: Write failing demo/documentation contract tests.**

Require documentation and scripts to demonstrate:
- snapshots for both route directions/source;
- `travelAvailability` query;
- exact round-trip package query;
- successful two-flight checkout;
- injected return-flight failure and compensation evidence;
- SQL showing outbound vs return offer counts/date ranges/prices by source.

- [ ] **Step 2: Run documentation/demo tests and confirm RED.**

Run: `python -m pytest tests/test_demo_validation_contract.py tests/test_docs_real_scraping_contract.py -v`
Expected: FAIL until new round-trip evidence is documented.

- [ ] **Step 3: Update demo scripts and study SQL.**

`demo_validation.py` must discover a recommended real combination before querying packages. `scraping_study.sql` compares CLIC/SATENA by route direction, count, date range and min/avg/max price.

- [ ] **Step 4: Update operator documentation.**

Explain MDE↔EOH mapping, up-to-eight real dates, 1–14-night rule, mixed-airline combinations, two-flight SAGA semantics, and that external airlines are never booked by WanderSync.

- [ ] **Step 5: Run full verification.**

Run: `python -m pytest -q`
Expected: all tests PASS.
Run: `python scripts/verify_project.py`
Expected: all static checks PASS.
Run: `python -m compileall backend ingestion scripts tests`
Expected: exit 0.
Run: `docker compose config -q`
Expected: exit 0 where Docker is available; otherwise record environment limitation without claiming runtime verification.

- [ ] **Step 6: Package and verify the ZIP.**

Create the final archive without `.git`, caches, runtime snapshots, secrets, or local `.env`. Extract it to a fresh directory and rerun `python -m pytest -q`, `python scripts/verify_project.py`, and Python compile checks against the extracted tree.

- [ ] **Step 7: Commit.**

```bash
git add scripts docs README.md ROUNDTRIP_FLEXIBLE_DATES.md tests/test_demo_validation_contract.py tests/test_docs_real_scraping_contract.py
git commit -m "docs: add round-trip demo evidence"
```
