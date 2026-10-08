from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from ingestion.collectors.base import SourceBlockedError, SourceChangedError, SourceUnavailableError
from ingestion.collectors.playwright_collector import collect_html
from ingestion.collectors.http_collector import collect_http
from ingestion.models import CaptureResult, ScrapeRequest, SnapshotRef, SourceRunResult
from ingestion.policies.cache import classify_snapshot_age
from ingestion.snapshots.manager import latest_snapshot, snapshot_key
from ingestion.sources.registry import get_adapter, get_enabled_adapters

class _Immediate:
    def __init__(self, value):
        self.value = value

    def result(self):
        return self.value


def _resolve_inline(value):
    return value.result() if isinstance(value, _Immediate) else value


try:
    from prefect import flow, task
except ImportError:  # Unit-test environment can validate pure pipeline logic without Prefect installed.
    def flow(*dargs, **dkwargs):
        def deco(fn):
            return fn
        return deco

    def task(*dargs, **dkwargs):
        def deco(fn):
            fn.submit = lambda *a, **k: _Immediate(
                fn(*[_resolve_inline(v) for v in a], **{key: _resolve_inline(v) for key, v in k.items()})
            )
            return fn
        return deco

DASK_SCHEDULER = os.getenv("DASK_SCHEDULER", "tcp://dask-scheduler:8786")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://wandersync:wandersync_dev_password@postgres:5432/wandersync")
SNAPSHOT_ROOT = os.getenv("SCRAPE_SNAPSHOT_ROOT", "/data/snapshots")
CACHE_MINUTES = int(os.getenv("SCRAPE_CACHE_MINUTES", "30"))
STALE_HOURS = int(os.getenv("SCRAPE_STALE_MAX_HOURS", "24"))
NAV_TIMEOUT = int(os.getenv("SCRAPE_NAVIGATION_TIMEOUT_SECONDS", "45"))
MAX_ROUTE_CONCURRENCY_PER_SOURCE = max(1, min(2, int(os.getenv("MAX_ROUTE_CONCURRENCY_PER_SOURCE", "2"))))


@dataclass(frozen=True)
class AcquisitionDecision:
    snapshot: SnapshotRef
    status: str
    error_message: str | None = None


def acquire_snapshot(
    request: ScrapeRequest,
    snapshot_root: str | Path = SNAPSHOT_ROOT,
    *,
    collector: Callable[..., CaptureResult] | None = None,
    now: datetime | None = None,
    cache_minutes: int = CACHE_MINUTES,
    stale_hours: int = STALE_HOURS,
    timeout_seconds: int = NAV_TIMEOUT,
) -> AcquisitionDecision:
    now = now or datetime.now(timezone.utc)
    key = snapshot_key(request)
    previous = latest_snapshot(request.source, request.kind, key, snapshot_root)
    previous_age = None
    if previous:
        captured = datetime.fromisoformat(previous.metadata.captured_at)
        previous_age = classify_snapshot_age(captured, now, cache_minutes, stale_hours)
        if previous_age == "FRESH":
            return AcquisitionDecision(previous, "CACHED")
    try:
        selected_collector = collector or (collect_http if request.transport == "http" else collect_html)
        result = selected_collector(request, snapshot_root, timeout_seconds)
        return AcquisitionDecision(result.snapshot, "SUCCESS")
    except SourceBlockedError as exc:
        if previous and previous_age == "STALE":
            return AcquisitionDecision(previous, "STALE_FALLBACK", f"SourceBlockedError: {exc}")
        raise
    except (SourceUnavailableError, SourceChangedError) as exc:
        if previous and previous_age == "STALE":
            return AcquisitionDecision(previous, "STALE_FALLBACK", f"{type(exc).__name__}: {exc}")
        raise SourceUnavailableError(f"{type(exc).__name__}: {exc}; no acceptable real snapshot fallback") from exc


def snapshot_identity(ref: SnapshotRef) -> str:
    raw = "|".join(
        [ref.metadata.source, ref.metadata.kind, ref.metadata.query_hash, ref.metadata.captured_at, ref.metadata.html_sha256 or ""]
    )
    return "SNAP-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def parse_snapshot(adapter_name: str, ref: SnapshotRef) -> list[dict]:
    adapter = get_adapter(adapter_name)
    html = ref.html_path.read_text(encoding="utf-8")
    rows = adapter.parse(html, ref.metadata)
    if not rows:
        raise SourceChangedError(f"Parser returned zero rows for {adapter_name}; previous catalog is preserved")
    return rows


def normalize_rows(adapter_name: str, raw_rows: list[dict], ref: SnapshotRef) -> list[dict]:
    adapter = get_adapter(adapter_name)
    sid = snapshot_identity(ref)
    normalized = [adapter.normalize(row, ref.metadata, sid) for row in raw_rows]
    return [row for row in normalized if row is not None]


def parse_normalize_snapshot(adapter: Any, ref: SnapshotRef) -> list[dict]:
    html = ref.html_path.read_text(encoding="utf-8")
    raw = adapter.parse(html, ref.metadata)
    if not raw:
        raise SourceChangedError("Parser returned zero rows; previous catalog is preserved")
    sid = snapshot_identity(ref)
    rows = [adapter.normalize(row, ref.metadata, sid) for row in raw]
    return [row for row in rows if row is not None]


def _connect():
    import psycopg
    return psycopg.connect(DATABASE_URL)


def _begin_run(adapter_name: str) -> int:
    adapter = get_adapter(adapter_name)
    request = adapter.build_requests()[0]
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO scrape_runs(source,kind,query_hash,source_url,status)
               VALUES(%s,%s,%s,%s,'RUNNING') RETURNING id""",
            (adapter.name, adapter.kind, snapshot_key(request), request.url),
        )
        return int(cur.fetchone()[0])


def _finish_run(run_id: int, status: str, *, snapshot_id: str | None = None, items: int = 0, error: str | None = None) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """UPDATE scrape_runs SET finished_at=NOW(),status=%s,snapshot_id=%s,items_found=%s,error_message=%s
               WHERE id=%s""",
            (status, snapshot_id, items, error, run_id),
        )


def register_snapshot(ref: SnapshotRef) -> str:
    """Persist snapshot provenance before parsing so failed parsers can still reference it safely."""
    sid = snapshot_identity(ref)
    meta = ref.metadata
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO scrape_snapshots(id,source,kind,source_url,query_hash,captured_at,http_status,status,snapshot_path,html_sha256)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(id) DO UPDATE SET snapshot_path=EXCLUDED.snapshot_path,status=EXCLUDED.status""",
            (sid, meta.source, meta.kind, meta.source_url, meta.query_hash, meta.captured_at, meta.http_status,
             meta.status, str(ref.html_path), meta.html_sha256),
        )
    return sid


def persist_catalog(adapter_name: str, ref: SnapshotRef, rows: list[dict]) -> dict[str, Any]:
    adapter = get_adapter(adapter_name)
    sid = register_snapshot(ref)
    with _connect() as conn, conn.cursor() as cur:
        if adapter.kind == "flights":
            cur.execute("UPDATE flights SET active=FALSE WHERE source=%s", (adapter.name,))
            sql = """INSERT INTO flights(id,airline,origin,destination,travel_date,departure_at,arrival_at,price,currency,source,source_url,snapshot_id,scraped_at,active,updated_at)
                     VALUES(%(id)s,%(airline)s,%(origin)s,%(destination)s,%(travel_date)s,%(departure_at)s,%(arrival_at)s,%(price)s,%(currency)s,%(source)s,%(source_url)s,%(snapshot_id)s,%(scraped_at)s,%(active)s,NOW())
                     ON CONFLICT(id) DO UPDATE SET price=EXCLUDED.price,currency=EXCLUDED.currency,source_url=EXCLUDED.source_url,
                     snapshot_id=EXCLUDED.snapshot_id,scraped_at=EXCLUDED.scraped_at,active=TRUE,updated_at=NOW()"""
        elif adapter.kind == "hotels":
            cur.execute("UPDATE hotels SET active=FALSE WHERE source=%s", (adapter.name,))
            sql = """INSERT INTO hotels(id,name,room_type,city,nightly_price,currency,rating,source,source_url,snapshot_id,scraped_at,active,updated_at)
                     VALUES(%(id)s,%(name)s,%(room_type)s,%(city)s,%(nightly_price)s,%(currency)s,%(rating)s,%(source)s,%(source_url)s,%(snapshot_id)s,%(scraped_at)s,%(active)s,NOW())
                     ON CONFLICT(id) DO UPDATE SET nightly_price=EXCLUDED.nightly_price,currency=EXCLUDED.currency,rating=EXCLUDED.rating,
                     source_url=EXCLUDED.source_url,snapshot_id=EXCLUDED.snapshot_id,scraped_at=EXCLUDED.scraped_at,active=TRUE,updated_at=NOW()"""
        elif adapter.kind == "cars":
            cur.execute("UPDATE cars SET active=FALSE WHERE source=%s", (adapter.name,))
            sql = """INSERT INTO cars(id,provider,model,city,daily_price,currency,category,source,source_url,snapshot_id,scraped_at,active,updated_at)
                     VALUES(%(id)s,%(provider)s,%(model)s,%(city)s,%(daily_price)s,%(currency)s,%(category)s,%(source)s,%(source_url)s,%(snapshot_id)s,%(scraped_at)s,%(active)s,NOW())
                     ON CONFLICT(id) DO UPDATE SET daily_price=EXCLUDED.daily_price,currency=EXCLUDED.currency,category=EXCLUDED.category,
                     source_url=EXCLUDED.source_url,snapshot_id=EXCLUDED.snapshot_id,scraped_at=EXCLUDED.scraped_at,active=TRUE,updated_at=NOW()"""
        else:
            raise ValueError(f"Unsupported kind: {adapter.kind}")
        for row in rows:
            cur.execute(sql, row)
            price = row.get("price", row.get("nightly_price", row.get("daily_price")))
            cur.execute("INSERT INTO offer_observations(kind,offer_id,snapshot_id,source,price,captured_at) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (adapter.kind, row["id"], row["snapshot_id"], adapter.name, price, row["scraped_at"]))
    return {"snapshot_id": sid, "rows": len(rows), "kind": adapter.kind, "source": adapter.name}


def persist_catalog_batch(
    adapter_name: str,
    batches: list[tuple[SnapshotRef, list[dict]]],
    preserve_unseen_routes: bool = False,
    empty_routes: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Refresh successful routes together; preserve unseen routes during a partial source failure."""
    adapter = get_adapter(adapter_name)
    if adapter.kind != "flights":
        raise ValueError("Batch catalog refresh is only used for flight sources")
    snapshot_ids = [register_snapshot(ref) for ref, _ in batches]
    rows = [row for _, batch_rows in batches for row in batch_rows]
    with _connect() as conn, conn.cursor() as cur:
        if preserve_unseen_routes:
            routes = {(row["origin"], row["destination"]) for row in rows}
            routes.update(empty_routes or [])
            for origin, destination in sorted(routes):
                cur.execute(
                    "UPDATE flights SET active=FALSE WHERE source=%s AND origin=%s AND destination=%s",
                    (adapter.name, origin, destination),
                )
        else:
            cur.execute("UPDATE flights SET active=FALSE WHERE source=%s", (adapter.name,))
        sql = """INSERT INTO flights(id,airline,origin,destination,travel_date,departure_at,arrival_at,price,currency,source,source_url,snapshot_id,scraped_at,active,updated_at)
                 VALUES(%(id)s,%(airline)s,%(origin)s,%(destination)s,%(travel_date)s,%(departure_at)s,%(arrival_at)s,%(price)s,%(currency)s,%(source)s,%(source_url)s,%(snapshot_id)s,%(scraped_at)s,%(active)s,NOW())
                 ON CONFLICT(id) DO UPDATE SET price=EXCLUDED.price,currency=EXCLUDED.currency,source_url=EXCLUDED.source_url,
                 snapshot_id=EXCLUDED.snapshot_id,scraped_at=EXCLUDED.scraped_at,active=TRUE,updated_at=NOW()"""
        for row in rows:
            cur.execute(sql, row)
            price = row.get("price", row.get("nightly_price", row.get("daily_price")))
            cur.execute("INSERT INTO offer_observations(kind,offer_id,snapshot_id,source,price,captured_at) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (adapter.kind, row["id"], row["snapshot_id"], adapter.name, price, row["scraped_at"]))
    return {"snapshot_id": snapshot_ids[0] if snapshot_ids else None, "snapshot_ids": snapshot_ids,
            "rows": len(rows), "kind": adapter.kind, "source": adapter.name}


def _dask_call(fn, *args):
    from dask.distributed import Client
    with Client(DASK_SCHEDULER, timeout="20s") as client:
        future = client.submit(fn, *args, pure=False)
        return client.gather(future)


def record_route_result(request, status, *, items=0, snapshot_id=None, error=None):
    with _connect() as conn:
        conn.execute("INSERT INTO scrape_route_runs(source,origin,destination,source_url,status,items_found,snapshot_id,error_message) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                     (request.source, request.query["origin"], request.query["destination"], request.url, status, items, snapshot_id, error))


def collect_source_batch(adapter_name: str) -> dict:
    adapter = get_adapter(adapter_name)
    run_id = _begin_run(adapter_name)
    requests = list(adapter.build_requests())
    captures: list[AcquisitionDecision] = []
    captured_by_request_url: dict[str, AcquisitionDecision] = {}
    request_errors: list[dict] = []

    def acquire_one(request: ScrapeRequest):
        try:
            decision = _dask_call(acquire_snapshot, request, SNAPSHOT_ROOT)
            _dask_call(register_snapshot, decision.snapshot)
            return (request, decision, None, False)
        except SourceBlockedError as exc:
            return (request, None, f"SourceBlockedError: {exc}", True)
        except Exception as exc:
            return (request, None, f"{type(exc).__name__}: {exc}", False)

    with ThreadPoolExecutor(max_workers=MAX_ROUTE_CONCURRENCY_PER_SOURCE) as pool:
        futures = [pool.submit(acquire_one, request) for request in requests]
        for future in as_completed(futures):
            request, decision, error_text, policy_blocked = future.result()
            if decision is not None:
                captured_by_request_url[request.url] = decision
            else:
                record_route_result(request, "SOURCE_UNAVAILABLE", error=error_text)
                request_errors.append({"url": request.url, "error": "ROBOTS_DISALLOWED" if policy_blocked else error_text, **({"policy_blocked": True} if policy_blocked else {})})

    # Preserve deterministic registry order even when requests complete concurrently.
    captures = [captured_by_request_url[request.url] for request in requests if request.url in captured_by_request_url]
    blocked_count = sum(1 for item in request_errors if item.get("policy_blocked"))
    all_policy_blocked = bool(requests) and not captures and blocked_count == len(requests)
    error = None
    non_retryable = False
    if not captures:
        if all_policy_blocked:
            error = "ROBOTS_DISALLOWED"
            non_retryable = True
        else:
            unique = []
            for item in request_errors:
                text = item["error"]
                if text not in unique:
                    unique.append(text)
            error = "; ".join(unique) or "No route request produced a snapshot"
        _finish_run(run_id, "SOURCE_UNAVAILABLE", error=error)
    return {"adapter": adapter_name, "run_id": run_id, "captures": captures,
            "request_errors": request_errors, "error": error, "non_retryable": non_retryable}


def parse_source_batch(state: dict) -> dict:
    if state.get("error") or not state.get("captures"):
        return state
    parsed = []
    for decision in state["captures"]:
        try:
            rows = _dask_call(parse_snapshot, state["adapter"], decision.snapshot)
            parsed.append((decision, rows))
        except Exception as exc:
            request = next((r for r in get_adapter(state["adapter"]).build_requests() if snapshot_key(r) == decision.snapshot.metadata.query_hash), None)
            if request:
                record_route_result(request, "SOURCE_CHANGED", snapshot_id=snapshot_identity(decision.snapshot), error=str(exc))
            state.setdefault("request_errors", []).append({"url": decision.snapshot.metadata.source_url, "error": str(exc)})
    if not parsed:
        state["error"] = "No route snapshot produced parseable rows"
        first = state["captures"][0].snapshot
        _finish_run(state["run_id"], "SOURCE_CHANGED", snapshot_id=snapshot_identity(first), error=state["error"])
    else:
        state["parsed_captures"] = parsed
    return state


def normalize_source_batch(state: dict) -> dict:
    if state.get("error") or not state.get("parsed_captures"):
        return state
    adapter = get_adapter(state["adapter"])
    request_routes = {
        snapshot_key(request): (request.query.get("origin"), request.query.get("destination"))
        for request in adapter.build_requests()
    }
    normalized = []
    empty_routes: list[tuple[str, str]] = []
    for decision, raw_rows in state["parsed_captures"]:
        rows = _dask_call(normalize_rows, state["adapter"], raw_rows, decision.snapshot)
        if rows:
            normalized.append((decision, rows))
        else:
            state.setdefault("request_errors", []).append({
                "url": decision.snapshot.metadata.source_url,
                "error": "No valid normalized rows for route snapshot",
            })
            route = request_routes.get(decision.snapshot.metadata.query_hash) or next(((r.query.get("origin"), r.query.get("destination")) for r in adapter.build_requests() if r.url == decision.snapshot.metadata.source_url), None)
            if route and route[0] and route[1]:
                empty_routes.append((str(route[0]), str(route[1])))
    state["normalized_captures"] = normalized
    state["empty_routes"] = empty_routes
    state["rows"] = [row for _, rows in normalized for row in rows]
    return state


def _batch_status(decisions: list[AcquisitionDecision]) -> str:
    statuses = {decision.status for decision in decisions}
    if "SUCCESS" in statuses:
        return "SUCCESS"
    if "STALE_FALLBACK" in statuses:
        return "STALE_FALLBACK"
    return "CACHED"


def _collect_stage(adapter_name: str) -> dict:
    adapter = get_adapter(adapter_name)
    if len(adapter.build_requests()) > 1:
        return collect_source_batch(adapter_name)
    run_id = _begin_run(adapter_name)
    request = adapter.build_requests()[0]
    try:
        decision = _dask_call(acquire_snapshot, request, SNAPSHOT_ROOT)
        _dask_call(register_snapshot, decision.snapshot)
        return {"adapter": adapter_name, "run_id": run_id, "decision": decision, "error": None}
    except SourceBlockedError:
        _finish_run(run_id, "SOURCE_UNAVAILABLE", error="ROBOTS_DISALLOWED")
        return {"adapter": adapter_name, "run_id": run_id, "decision": None, "error": "ROBOTS_DISALLOWED", "non_retryable": True}
    except Exception as exc:
        _finish_run(run_id, "SOURCE_UNAVAILABLE", error=f"{type(exc).__name__}: {exc}")
        return {"adapter": adapter_name, "run_id": run_id, "decision": None, "error": str(exc), "non_retryable": False}


def _parse_stage(state: dict) -> dict:
    if "captures" in state:
        return parse_source_batch(state)
    if state.get("error") or not state.get("decision"):
        return state
    try:
        state["raw_rows"] = _dask_call(parse_snapshot, state["adapter"], state["decision"].snapshot)
    except Exception as exc:
        _finish_run(state["run_id"], "SOURCE_CHANGED", snapshot_id=snapshot_identity(state["decision"].snapshot), error=str(exc))
        state["error"] = str(exc)
    return state


def _normalize_stage(state: dict) -> dict:
    if "captures" in state:
        return normalize_source_batch(state)
    if state.get("error") or "raw_rows" not in state:
        return state
    rows = _dask_call(normalize_rows, state["adapter"], state["raw_rows"], state["decision"].snapshot)
    if not rows:
        _finish_run(state["run_id"], "PARSER_ERROR", snapshot_id=snapshot_identity(state["decision"].snapshot), error="No valid normalized rows")
        state["error"] = "No valid normalized rows"
    else:
        state["rows"] = rows
    return state


def _persist_stage(state: dict) -> SourceRunResult:
    adapter = get_adapter(state["adapter"])
    if state.get("error") or "rows" not in state:
        return SourceRunResult(adapter.name, adapter.kind, "SOURCE_UNAVAILABLE", 0, error_message=state.get("error"))
    if "normalized_captures" in state:
        batches = [(decision.snapshot, rows) for decision, rows in state["normalized_captures"]]
        persisted = _dask_call(
            persist_catalog_batch, state["adapter"], batches, bool(state.get("request_errors")), state.get("empty_routes", [])
        )
        decisions = [decision for decision, _ in state["normalized_captures"]] or list(state.get("captures", []))
        status = _batch_status(decisions)
        diagnostics = "; ".join(item["error"] for item in state.get("request_errors", [])) or None
        first_ref = decisions[0].snapshot
        persisted_snapshot_id = persisted["snapshot_id"] or snapshot_identity(first_ref)
        for request in adapter.build_requests():
            decision = next((d for d in state.get("captures", []) if d.snapshot.metadata.query_hash == snapshot_key(request)), None)
            if decision is None:
                continue
            count = sum(1 for row in state["rows"] if row["origin"] == request.query["origin"] and row["destination"] == request.query["destination"])
            failed = any(item["url"] in {request.url, decision.snapshot.metadata.source_url} for item in state.get("request_errors", []))
            record_route_result(request, "SOURCE_CHANGED" if failed else decision.status, items=count,
                                snapshot_id=snapshot_identity(decision.snapshot), error="Parser or normalization failed" if failed else decision.error_message)
        _finish_run(state["run_id"], status, snapshot_id=persisted_snapshot_id, items=persisted["rows"], error=diagnostics)
        return SourceRunResult(adapter.name, adapter.kind, status, persisted["rows"], str(first_ref.html_path), diagnostics)
    persisted = _dask_call(persist_catalog, state["adapter"], state["decision"].snapshot, state["rows"])
    status = state["decision"].status
    _finish_run(state["run_id"], status, snapshot_id=persisted["snapshot_id"], items=persisted["rows"], error=state["decision"].error_message)
    return SourceRunResult(adapter.name, adapter.kind, status, persisted["rows"], str(state["decision"].snapshot.html_path), state["decision"].error_message)


def process_source(adapter_name: str) -> SourceRunResult:
    return _persist_stage(_normalize_stage(_parse_stage(_collect_stage(adapter_name))))


def _prefect_collect(adapter_name: str) -> dict:
    state = _collect_stage(adapter_name)
    if state.get("error") and not state.get("non_retryable"):
        raise SourceUnavailableError(state["error"])
    return state


@task(name="collect CLIC flights", retries=2, retry_delay_seconds=10)
def collect_clicair_flights(): return _prefect_collect("clicair")

@task(name="collect SATENA flights", retries=2, retry_delay_seconds=10)
def collect_satena_flights(): return _prefect_collect("satena")

@task(name="collect JetSMART flights", retries=2, retry_delay_seconds=10)
def collect_jetsmart_flights(): return _prefect_collect("jetsmart")

@task(name="collect Wingo flights", retries=2, retry_delay_seconds=10)
def collect_wingo_flights(): return _prefect_collect("wingo")

# Backward-compatible name used by older tests/operator imports.
collect_flights = collect_wingo_flights
@task(name="parse flights")
def parse_flights_task(state): return _parse_stage(state)
@task(name="normalize flights")
def normalize_flights_task(state): return _normalize_stage(state)
@task(name="persist flights")
def persist_flights_task(state): return _persist_stage(state)

@task(name="collect hotels", retries=2, retry_delay_seconds=10)
def collect_hotels(): return _prefect_collect("ghl_porton_medellin")
@task(name="parse hotels")
def parse_hotels_task(state): return _parse_stage(state)
@task(name="normalize hotels")
def normalize_hotels_task(state): return _normalize_stage(state)
@task(name="persist hotels")
def persist_hotels_task(state): return _persist_stage(state)

@task(name="collect cars", retries=2, retry_delay_seconds=10)
def collect_cars(): return _prefect_collect("alkilautos_national_medellin")
@task(name="parse cars")
def parse_cars_task(state): return _parse_stage(state)
@task(name="normalize cars")
def normalize_cars_task(state): return _normalize_stage(state)
@task(name="persist cars")
def persist_cars_task(state): return _persist_stage(state)


def _submit_task(task_fn, *args):
    if hasattr(task_fn, "submit"):
        return task_fn.submit(*args)
    resolved = [arg.result() if hasattr(arg, "result") else arg for arg in args]
    return _Immediate(task_fn(*resolved))


def _submit_chain(collect_task, parse_task, normalize_task, persist_task):
    collected = _submit_task(collect_task)
    parsed = _submit_task(parse_task, collected)
    normalized = _submit_task(normalize_task, parsed)
    return _submit_task(persist_task, normalized)


def _partial_failure_result(adapter_name: str, exc: Exception) -> SourceRunResult:
    adapter = get_adapter(adapter_name)
    error_message = f"{type(exc).__name__}: {exc}"
    # When a downstream Prefect future is NotReady, the useful root cause is already
    # recorded by _collect_stage. Prefer that message when PostgreSQL is reachable.
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT error_message FROM scrape_runs
                   WHERE source=%s AND error_message IS NOT NULL
                   ORDER BY id DESC LIMIT 1""",
                (adapter.name,),
            )
            row = cur.fetchone()
            if row and row[0]:
                error_message = row[0]
    except Exception:
        pass
    return SourceRunResult(adapter.name, adapter.kind, "SOURCE_UNAVAILABLE", 0, error_message=error_message)


@task(name="collect city service", retries=2, retry_delay_seconds=10)
def collect_city_source(name): return _prefect_collect(name)
@task(name="parse city service")
def parse_city_source(state): return _parse_stage(state)
@task(name="normalize city service")
def normalize_city_source(state): return _normalize_stage(state)
@task(name="persist city service")
def persist_city_source(state): return _persist_stage(state)


@flow(name="WanderSync real scraping ingestion", retries=1, retry_delay_seconds=15, log_prints=True)
def travel_scraping_flow():
    # Submit independent source chains before waiting so Prefect/Dask can use both workers.
    enabled = {adapter.name for adapter in get_enabled_adapters()}
    futures: list[tuple[str, Any]] = []
    if "clicair" in enabled:
        futures.append(("clicair", _submit_chain(collect_clicair_flights, parse_flights_task, normalize_flights_task, persist_flights_task)))
    if "satena" in enabled:
        futures.append(("satena", _submit_chain(collect_satena_flights, parse_flights_task, normalize_flights_task, persist_flights_task)))
    if "jetsmart" in enabled:
        futures.append(("jetsmart", _submit_chain(collect_jetsmart_flights, parse_flights_task, normalize_flights_task, persist_flights_task)))
    if "wingo" in enabled:
        futures.append(("wingo", _submit_chain(collect_wingo_flights, parse_flights_task, normalize_flights_task, persist_flights_task)))
    if "ghl_porton_medellin" in enabled:
        futures.append(("ghl_porton_medellin", _submit_chain(collect_hotels, parse_hotels_task, normalize_hotels_task, persist_hotels_task)))
    if "alkilautos_national_medellin" in enabled:
        futures.append(("alkilautos_national_medellin", _submit_chain(collect_cars, parse_cars_task, normalize_cars_task, persist_cars_task)))

    for adapter in get_enabled_adapters():
        if adapter.name in {name for name, _ in futures}:
            continue
        collected = _submit_task(collect_city_source, adapter.name)
        parsed = _submit_task(parse_city_source, collected)
        normalized = _submit_task(normalize_city_source, parsed)
        futures.append((adapter.name, _submit_task(persist_city_source, normalized)))

    results: list[SourceRunResult] = []
    for adapter_name, future in futures:
        try:
            value = future.result() if hasattr(future, "result") else future
            results.append(value)
        except Exception as exc:
            results.append(_partial_failure_result(adapter_name, exc))

    print(f"Real scraping ingestion completed: {results}")
    return results


# Backward-compatible import name for old operator scripts; it no longer uses a provider/mock source.
travel_ingestion_flow = travel_scraping_flow

if __name__ == "__main__":
    travel_scraping_flow()
