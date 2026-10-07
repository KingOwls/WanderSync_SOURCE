# WanderSync Real Scraping Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace WanderSync's mock travel catalog with a traceable, low-frequency, Playwright-based scraping pipeline that feeds Dask, Prefect, PostgreSQL, GraphQL, the frontend, and the existing local SAGA without generating any tourist data synthetically.

**Architecture:** Public source adapters build fixed allowlisted scrape requests. Playwright captures rendered HTML into shared snapshots; offline parsers and normalizers run through Dask, Prefect orchestrates and retries the pipeline, and PostgreSQL stores both catalog rows and provenance. Existing catalog services expose active scraped offers while SAGA creates only local holds, never claiming external inventory reservation.

**Tech Stack:** Python 3.12, Playwright/Chromium, BeautifulSoup4 + lxml, httpx, Dask Distributed, Prefect 3, psycopg 3, FastAPI, Strawberry GraphQL, PostgreSQL 17, Redis 7, React/Vite, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-05-real-scraping-design.md`

## Global Constraints

- No tourist-facing mock/generated catalog data and no mock fallback.
- All enabled source URLs are fixed/operator-controlled and host-allowlisted; no user-supplied arbitrary URLs.
- Acquisition concurrency is exactly 1 per source.
- Default cache freshness: `SCRAPE_CACHE_MINUTES=30`.
- Default stale real-snapshot fallback window: `SCRAPE_STALE_MAX_HOURS=24`.
- Default pacing: `SCRAPE_MIN_INTERVAL_SECONDS=90`, `SCRAPE_MAX_INTERVAL_SECONDS=180`.
- Default navigation timeout: `SCRAPE_NAVIGATION_TIMEOUT_SECONDS=45`.
- Default capture retry limit: `SCRAPE_RETRY_LIMIT=2`.
- No CAPTCHA solving, proxy rotation for evasion, fingerprint spoofing, stealth plugins, private-login scraping, or anti-bot bypass.
- Frontend searches only persisted catalog data; user searches never start Playwright.
- Existing Argon2id, session rotation, rate limiting, GraphQL gateway, Docker Compose, Prefect, Dask, and SAGA requirements remain operational.
- A source failure may use only a previously captured real snapshot within the stale window; otherwise return/source-state `SOURCE_UNAVAILABLE`.
- Catalog rows must retain `source`, `source_url`, `scraped_at`, and snapshot provenance.
- SAGA reservation endpoints create/cancel local holds against active scraped offers; they do not decrement or claim external inventory.

## Review Focus

- Source HTML changes or selector disappearance must record `SOURCE_CHANGED`/`PARSER_ERROR` without deleting the previous catalog.
- A `429`, `403`, CAPTCHA/challenge, or timeout must never trigger bypass behavior; retry/fallback rules must be deterministic and observable.
- A valid snapshot cache hit must avoid browser navigation while still allowing parsing/persistence and a `CACHED` scrape run.
- Catalog records with missing optional source fields such as rating, exact times, category, or price must remain valid where the spec permits nulls and must not be filled with invented values.
- SAGA compensation must remain idempotent when local holds already have `CANCELLED` status and must not mutate scraped catalog availability fields.

---

## File Structure Locked by This Plan

### New ingestion modules

- `ingestion/models.py` — shared `ScrapeRequest`, `SnapshotMetadata`, `CaptureResult`, normalized-offer types.
- `ingestion/collectors/base.py` — collector protocol and typed errors.
- `ingestion/collectors/playwright_collector.py` — allowlisted low-concurrency HTML capture only.
- `ingestion/sources/registry.py` — enabled source adapters and fixed source selection.
- `ingestion/sources/flights_wingo.py` — real flight-source request/parser adapter.
- `ingestion/sources/hotels_public.py` — real hotel-source request/parser adapter(s).
- `ingestion/sources/cars_public.py` — real car-source request/parser adapter.
- `ingestion/parsers/flights.py`, `hotels.py`, `cars.py` — offline DOM extraction helpers.
- `ingestion/normalization/flights.py`, `hotels.py`, `cars.py` — canonical field normalization without invention.
- `ingestion/snapshots/manager.py` — filesystem snapshot lookup/write/hash logic.
- `ingestion/snapshots/metadata.py` — metadata serialization/validation.
- `ingestion/policies/cache.py` — freshness/stale-window decisions.
- `ingestion/policies/pacing.py` — per-source lock and pacing calculation.
- `ingestion/policies/robots.py` — robots policy lookup/evaluation for configured source paths.
- `ingestion/policies/retry.py` — bounded retry/backoff helpers and `Retry-After` parsing.

### Existing files modified

- `ingestion/flow.py` — Prefect/Dask acquisition → snapshot → parse → normalize → persist orchestration.
- `ingestion/runner.py` — dependency wait without provider-service; recurring flow execution.
- `ingestion/requirements.txt`, `ingestion/Dockerfile` — Playwright/Chromium/parser dependencies.
- `infra/postgres/init.sql` — real-scraping catalog schema, provenance, scrape runs/snapshots, local holds.
- `backend/flight_service/main.py`, `backend/hotel_service/main.py`, `backend/car_service/main.py` — active scraped catalog queries + local holds.
- `backend/order_service/main.py` — same SAGA contract against local holds; no catalog inventory mutation.
- `backend/gateway/main.py`, `schema.graphql` — nullable source-derived fields + provenance fields.
- `frontend/src/main.jsx` — source/updated-at badges and source-unavailable messaging.
- `docker-compose.yml`, `.env.example` — remove provider-service, add snapshot volume and `SCRAPE_*` variables.
- `scripts/verify_project.py`, `scripts/db_check.sh`, `scripts/db_check.ps1`, `scripts/demo_validation.py` — real-scraping assertions and demo checks.
- `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/DEMO_GUIDE.md`, `docs/COMPLIANCE.md`, `README.md` — final operating/demo documentation.
- `security/audit.sh`, `security/audit.ps1` — include ingestion Playwright/parser dependency audit evidence.

### New tests

- `tests/test_snapshot_cache.py`
- `tests/test_scrape_security.py`
- `tests/test_parsers.py`
- `tests/test_normalization.py`
- `tests/test_scrape_persistence.py`
- `tests/test_local_holds.py`
- `tests/test_scrape_flow.py`

---

### Task 1: Define scraping contracts, cache policy, and snapshot storage

**Files:**
- Create: `ingestion/models.py`
- Create: `ingestion/snapshots/__init__.py`
- Create: `ingestion/snapshots/metadata.py`
- Create: `ingestion/snapshots/manager.py`
- Create: `ingestion/policies/__init__.py`
- Create: `ingestion/policies/cache.py`
- Test: `tests/test_snapshot_cache.py`

**Interfaces:**
- Produces: `ScrapeRequest`, `SnapshotMetadata`, `SnapshotRef`; `snapshot_key(request) -> str`; `save_snapshot(html, metadata, root) -> SnapshotRef`; `latest_snapshot(source, kind, query_hash, root) -> SnapshotRef | None`; `classify_snapshot_age(captured_at, now, cache_minutes, stale_hours) -> Literal['FRESH','STALE','EXPIRED']`.
- Consumes: only Python stdlib/pathlib/dataclasses/datetime/hashlib.

- [ ] **Step 1: Write failing snapshot/cache tests** covering deterministic query hashes, `.html` + `.json` creation, SHA-256 metadata, fresh/stale/expired boundaries at 30 minutes and 24 hours, and cache lookup returning only matching source/kind/query hash.
- [ ] **Step 2: Run** `pytest -q tests/test_snapshot_cache.py` and verify failures are due to missing modules/functions.
- [ ] **Step 3: Implement the contracts and snapshot/cache functions** with UTC timestamps and filesystem-safe paths under `/data/snapshots/<kind>/<source>/<query_hash>/`.
- [ ] **Step 4: Run** `pytest -q tests/test_snapshot_cache.py` and require all tests PASS.
- [ ] **Step 5: Commit** `git add ingestion/models.py ingestion/snapshots ingestion/policies/cache.py tests/test_snapshot_cache.py && git commit -m "feat: add scraping snapshot and cache contracts"`.

### Task 2: Add safe browser collection, robots policy, pacing, and bounded retry

**Files:**
- Create: `ingestion/collectors/__init__.py`
- Create: `ingestion/collectors/base.py`
- Create: `ingestion/collectors/playwright_collector.py`
- Create: `ingestion/policies/pacing.py`
- Create: `ingestion/policies/robots.py`
- Create: `ingestion/policies/retry.py`
- Modify: `ingestion/requirements.txt`
- Modify: `ingestion/Dockerfile`
- Test: `tests/test_scrape_security.py`

**Interfaces:**
- Consumes: `ScrapeRequest`, `SnapshotMetadata`, `save_snapshot(...)` from Task 1.
- Produces: `validate_request_url(request, allowed_hosts) -> None`; `collect_html(request, snapshot_root, timeout_seconds) -> CaptureResult`; typed `SourceBlockedError`, `SourceUnavailableError`, `SourceChangedError`; `retry_after_seconds(headers) -> int | None`.

- [ ] **Step 1: Write failing security/policy tests** for HTTPS/HTTP-only URLs, allowlisted hosts, rejection of localhost/private-IP/user-supplied hosts, one-per-source semaphore behavior, bounded retry counts, `Retry-After`, and explicit no-retry classification for CAPTCHA/403 persistent block.
- [ ] **Step 2: Run** `pytest -q tests/test_scrape_security.py` and verify expected failures.
- [ ] **Step 3: Implement collector/policies** so Playwright uses `domcontentloaded`, waits for adapter-provided selector, records main-response status, captures `page.content()`, never stores cookies/secrets, and always closes browser/context.
- [ ] **Step 4: Add dependencies** `playwright`, `beautifulsoup4`, `lxml` and make the ingestion image install Chromium plus Linux dependencies using the supported Playwright installation path; keep one identical ingestion image for scheduler, workers, and runner.
- [ ] **Step 5: Run** `pytest -q tests/test_scrape_security.py` and a container smoke check `python -c "from playwright.sync_api import sync_playwright; print('playwright-ok')"`; require PASS.
- [ ] **Step 6: Commit** collector/policy/Docker dependency changes with `feat: add safe Playwright collector`.

### Task 3: Implement real public source adapters and offline parsers

**Files:**
- Create: `ingestion/sources/__init__.py`
- Create: `ingestion/sources/registry.py`
- Create: `ingestion/sources/flights_wingo.py`
- Create: `ingestion/sources/hotels_public.py`
- Create: `ingestion/sources/cars_public.py`
- Create: `ingestion/parsers/__init__.py`
- Create: `ingestion/parsers/flights.py`
- Create: `ingestion/parsers/hotels.py`
- Create: `ingestion/parsers/cars.py`
- Create: `ingestion/normalization/__init__.py`
- Create: `ingestion/normalization/flights.py`
- Create: `ingestion/normalization/hotels.py`
- Create: `ingestion/normalization/cars.py`
- Test: `tests/test_parsers.py`
- Test: `tests/test_normalization.py`

**Interfaces:**
- Consumes: Task 1 models; Task 2 collector-ready selectors/allowlists.
- Produces: `get_enabled_adapters() -> list[SourceAdapter]`; each adapter implements `build_requests()`, `ready_selector(request)`, `parse(html, metadata)`; normalizers return canonical dictionaries matching the real catalog schema.

- [ ] **Step 1: Verify current public source pages manually/web-side** and lock one enabled source per category whose public DOM exposes the required fields for a common demo destination; record exact host, source URL template, ready selector, card selectors, and attribution in adapter constants.
- [ ] **Step 2: Save minimal real-HTML parser fixtures** under `tests/fixtures/scraping/` containing only enough captured public HTML structure to exercise selectors without network access during unit tests.
- [ ] **Step 3: Write failing parser tests** proving real DOM extraction for flight route/date/price, hotel name/city/price where published, and car provider/model/city/daily price; missing optional fields must return `None`, never fabricated defaults.
- [ ] **Step 4: Write failing normalization tests** for COP price strings, whitespace/case/city normalization, nullable date/time/rating/category, stable IDs based on source identity, and rejection of rows missing required source-observed fields.
- [ ] **Step 5: Implement adapters/parsers/normalizers** using BeautifulSoup/lxml offline; parsing functions accept HTML strings and metadata only and perform no network calls.
- [ ] **Step 6: Run** `pytest -q tests/test_parsers.py tests/test_normalization.py` and require PASS.
- [ ] **Step 7: Commit** with `feat: add real travel source adapters and parsers`.

### Task 4: Migrate PostgreSQL to provenance-first scraped catalog and scrape observability

**Files:**
- Modify: `infra/postgres/init.sql`
- Create: `tests/test_scrape_persistence.py`
- Modify: `scripts/db_check.sh`
- Modify: `scripts/db_check.ps1`

**Interfaces:**
- Consumes: normalized row dictionaries from Task 3.
- Produces: tables `scrape_snapshots`, `scrape_runs`; provenance columns on `flights`, `hotels`, `cars`; local reservation tables used as holds; idempotent schema bootstrap.

- [ ] **Step 1: Write failing persistence tests** against a temporary/test PostgreSQL schema or SQL contract checks asserting required provenance columns, nullable optional source fields, no `available_seats/available_rooms/available_units` dependency, and successful upsert retaining `snapshot_id`/`source_url`.
- [ ] **Step 2: Run** `pytest -q tests/test_scrape_persistence.py` and verify FAIL against the old schema.
- [ ] **Step 3: Update `init.sql` idempotently** to add `scrape_snapshots`/`scrape_runs`, replace catalog inventory columns with provenance/active/freshness fields, retain reservation/order history structures, and make optional fields nullable exactly as specified.
- [ ] **Step 4: Add an explicit development migration cleanup path** that removes old provider-generated catalog/demo orders while preserving users; document that a clean academic install should recreate the PostgreSQL volume once.
- [ ] **Step 5: Update DB diagnostics** to show counts grouped by `source`, latest scrape runs, snapshot provenance, and a transactional write probe.
- [ ] **Step 6: Run** persistence tests and static SQL bootstrap validation; require PASS.
- [ ] **Step 7: Commit** with `feat: migrate catalog to scraped provenance schema`.

### Task 5: Rebuild Prefect/Dask ingestion around capture, snapshots, parsing, and persistence

**Files:**
- Modify: `ingestion/flow.py`
- Modify: `ingestion/runner.py`
- Create: `tests/test_scrape_flow.py`

**Interfaces:**
- Consumes: adapters from Task 3, collector/policies from Task 2, snapshot/cache from Task 1, PostgreSQL schema from Task 4.
- Produces: `process_source(adapter_name: str) -> SourceRunResult`; Prefect flow `travel_scraping_flow()` named `WanderSync real scraping ingestion`; Dask tasks for capture/parse/normalize/persist; scrape-run statuses `SUCCESS`, `CACHED`, `STALE_FALLBACK`, `BLOCKED`, `SOURCE_CHANGED`, `SOURCE_UNAVAILABLE`.

- [ ] **Step 1: Write failing flow tests** with mocked collector/snapshot/database boundaries for fresh-cache no-navigation, new-capture success, blocked-source stale fallback, blocked-source no-snapshot unavailable, zero-row parser alert without catalog deletion, and database failure leaving snapshot available for reprocessing.
- [ ] **Step 2: Run** `pytest -q tests/test_scrape_flow.py` and verify FAIL.
- [ ] **Step 3: Implement orchestration** so acquisition is submitted through Dask with per-source concurrency 1, while parse/normalize/persist work is distributed after snapshot capture; record `scrape_runs` and `scrape_snapshots` for every path.
- [ ] **Step 4: Update runner dependency checks** to require Prefect, Dask, PostgreSQL, and DNS/network reachability only; remove all provider-service checks and `PROVIDER_URL` use.
- [ ] **Step 5: Run** `pytest -q tests/test_scrape_flow.py` plus `python -m compileall ingestion`; require PASS.
- [ ] **Step 6: Commit** with `feat: orchestrate real scraping with Prefect and Dask`.

### Task 6: Convert catalog reservation semantics to local holds without fake external inventory

**Files:**
- Modify: `backend/flight_service/main.py`
- Modify: `backend/hotel_service/main.py`
- Modify: `backend/car_service/main.py`
- Modify: `backend/order_service/main.py`
- Modify: `tests/test_saga_compensation.py`
- Create: `tests/test_local_holds.py`

**Interfaces:**
- Consumes: active scraped offers from Task 4 schema.
- Produces: unchanged HTTP reservation contract `POST /reservations` and `DELETE /reservations/{id}`, but semantics are local WanderSync holds; catalog rows are never decremented/incremented.

- [ ] **Step 1: Write failing local-hold tests** proving reserve checks offer existence/`active`, creates a local reservation row, leaves catalog data unchanged, cancel is idempotent, and simulated failures remain available for SAGA testing.
- [ ] **Step 2: Extend compensation tests** so failed car/billing steps cancel preceding holds exactly once and never change scraped catalog source fields/prices/active status.
- [ ] **Step 3: Run** `pytest -q tests/test_local_holds.py tests/test_saga_compensation.py` and verify FAIL where old inventory mutation remains.
- [ ] **Step 4: Implement service changes** and preserve current order-service happy-path/compensation API; update response wording/status documentation to call these local/demo WanderSync reservations.
- [ ] **Step 5: Run** both test files and require PASS.
- [ ] **Step 6: Commit** with `refactor: use local holds for scraped travel offers`.

### Task 7: Expose source provenance through GraphQL and frontend without coupling search to scraping

**Files:**
- Modify: `backend/gateway/main.py`
- Modify: `schema.graphql`
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/styles.css`
- Modify: `scripts/demo_validation.py`

**Interfaces:**
- Consumes: catalog-service JSON containing provenance and nullable source fields.
- Produces: GraphQL `Flight`, `Hotel`, `Car` fields `source`, `sourceUrl`, `scrapedAt`; nullable source-derived fields; existing `travelPackages` and checkout mutation names retained.

- [ ] **Step 1: Add/adjust automated GraphQL validation** to assert provenance fields are returned and package building excludes missing-price items rather than inventing prices.
- [ ] **Step 2: Modify gateway types/mappers** so `departure_at`, `arrival_at`, `rating`, `category`, and availability observations are nullable where source data is absent; package calculations use only persisted prices.
- [ ] **Step 3: Update frontend cards** to display source + last capture, label data as public-source data, and show a category/source-unavailable message when a complete package cannot be built.
- [ ] **Step 4: Ensure frontend search performs only the GraphQL query** and contains no scrape/source URL calls.
- [ ] **Step 5: Run** frontend build plus runtime demo script syntax/contract validation; require PASS.
- [ ] **Step 6: Commit** with `feat: surface scraped data provenance in GraphQL and UI`.

### Task 8: Remove mock provider from deployment and configure the shared browser/snapshot runtime

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.gitignore`
- Modify: `scripts/verify_project.py`

**Interfaces:**
- Consumes: final ingestion image and flow from Tasks 2/5.
- Produces: Compose stack with no `provider-service`, no `PROVIDER_URL`, shared `scrape_snapshots` volume, identical ingestion image across scheduler/workers/runner, and operator-controlled source settings only.

- [ ] **Step 1: Add failing static verifier assertions** requiring absence of `provider-service`/`PROVIDER_URL` and presence of Playwright, source registry, snapshot volume, `SCRAPE_*` settings, provenance schema, and no mock-source constants in production ingestion.
- [ ] **Step 2: Modify Compose/env** to mount `scrape_snapshots:/data/snapshots` into runner and both workers, pass cache/pacing/retry settings, and remove provider dependencies/service.
- [ ] **Step 3: Confirm scheduler/workers/runner build from the same `./ingestion` context/image contract** and preserve `PYTHONPATH=/app` to prevent Dask deserialization regressions.
- [ ] **Step 4: Run** `docker compose config` and `python scripts/verify_project.py`; require zero validation errors and all static checks PASS.
- [ ] **Step 5: Commit** with `chore: deploy real scraping pipeline in compose`.

### Task 9: End-to-end runtime acceptance, security audit, and delivery documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DATABASE.md`
- Modify: `docs/DEMO_GUIDE.md`
- Modify: `docs/COMPLIANCE.md`
- Modify: `security/audit.sh`
- Modify: `security/audit.ps1`
- Modify: `FINAL_COMPLIANCE_REVIEW.md`
- Create: `REAL_SCRAPING_ACCEPTANCE.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: reproducible demo/verification evidence and final ZIP.

- [ ] **Step 1: Run full unit/static suite**: `pytest -q`, `python scripts/verify_project.py`, Python compile checks, frontend `npm run build`; require all PASS.
- [ ] **Step 2: Build and start the stack** with a clean academic development volume once, then run `docker compose ps`; require critical services healthy and no provider-service.
- [ ] **Step 3: Verify Dask/Prefect runtime**: exactly two Dask workers registered; Prefect flow `WanderSync real scraping ingestion` records visible capture/parse/normalize/persist tasks.
- [ ] **Step 4: Verify real acquisition provenance**: at least one real `.html` snapshot per category, non-empty `scrape_runs`, and every demonstrated catalog row traces to `source_url` + `snapshot_id` + snapshot path.
- [ ] **Step 5: Verify cache/fallback behavior**: immediate rerun records `CACHED` without new browser capture; controlled source failure uses only a <=24h real snapshot or returns `SOURCE_UNAVAILABLE`.
- [ ] **Step 6: Verify application path**: GraphQL returns scraped provenance; frontend builds at least one complete package from real scraped data; normal SAGA confirms local holds; simulated failure compensates and cancels them.
- [ ] **Step 7: Re-run security evidence** for Argon2id/session fixation/rate limiting plus `pip-audit` on backend + ingestion and `npm audit` on frontend; save reports.
- [ ] **Step 8: Update documentation** with exact sources, attribution, operating limits, troubleshooting, demo sequence, source-unavailable behavior, and the statement that external provider reservations are not performed.
- [ ] **Step 9: Create `REAL_SCRAPING_ACCEPTANCE.md`** mapping all 20 spec acceptance criteria to command/evidence/result.
- [ ] **Step 10: Package final ZIP** excluding `.env`, caches, browser profiles, secrets, `node_modules`, `__pycache__`, and transient snapshots unless a deliberately selected attribution-safe evidence snapshot is explicitly included for the academic demo.
- [ ] **Step 11: Verify the extracted ZIP again** with static/unit checks and report its SHA-256.
- [ ] **Step 12: Commit** final docs/evidence with `docs: finalize real scraping acceptance evidence`.

## Plan Self-Review Result

- Spec coverage: all design sections 1-23 map to Tasks 1-9; no mock fallback remains.
- Type consistency: snapshot/provenance interfaces are defined once in Task 1 and consumed downstream; reservation HTTP contracts remain stable.
- Review-focus coverage: source changes, blocking, cache, nullable source fields, and idempotent SAGA compensation each have an owning test task.
- Scope: one migration plan with sequential dependencies; tasks are independently testable but share a single catalog/source contract.
- No placeholders/TBDs remain. Concrete DOM selectors are intentionally locked during Task 3 only after live source verification because they are external facts that may change and must not be invented in the plan.
