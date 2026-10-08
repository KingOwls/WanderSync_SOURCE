import pytest

@pytest.fixture(autouse=True)
def mock_route_audit(monkeypatch):
    import ingestion.flow as module
    monkeypatch.setattr(module, "record_route_result", lambda *a, **k: None)

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ingestion.collectors.base import SourceBlockedError, SourceUnavailableError
from ingestion.flow import acquire_snapshot, parse_normalize_snapshot
from ingestion.models import CaptureResult, ScrapeRequest, SnapshotMetadata
from ingestion.snapshots.manager import save_snapshot

NOW = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)


def request():
    return ScrapeRequest(
        source="wingo", kind="flights", url="https://www.wingo.com/es/vuelos-nacionales",
        ready_selector="body", query={"scope":"national"}, allowed_hosts=("www.wingo.com", "wingo.com")
    )


def seed_snapshot(tmp_path, age_minutes: int):
    req = request()
    meta = SnapshotMetadata.from_request(req, NOW - timedelta(minutes=age_minutes), 200, "SUCCESS")
    return save_snapshot("<html><body>cached real html</body></html>", meta, tmp_path)


def test_fresh_cache_avoids_navigation(tmp_path):
    seeded = seed_snapshot(tmp_path, 10)
    calls = []
    def collector(*args, **kwargs):
        calls.append(1)
        raise AssertionError("browser should not be called")
    decision = acquire_snapshot(request(), tmp_path, collector=collector, now=NOW, cache_minutes=30, stale_hours=24)
    assert decision.status == "CACHED"
    assert decision.snapshot.html_path == seeded.html_path
    assert calls == []


def test_new_capture_success(tmp_path):
    def collector(req, root, timeout_seconds):
        meta = SnapshotMetadata.from_request(req, NOW, 200, "SUCCESS")
        return CaptureResult(save_snapshot("<html>new real html</html>", meta, root))
    decision = acquire_snapshot(request(), tmp_path, collector=collector, now=NOW, cache_minutes=30, stale_hours=24)
    assert decision.status == "SUCCESS"
    assert decision.snapshot.html_path.exists()


def test_blocked_source_uses_only_nonexpired_real_snapshot(tmp_path):
    seeded = seed_snapshot(tmp_path, 60)
    def blocked(*args, **kwargs):
        raise SourceBlockedError("403")
    decision = acquire_snapshot(request(), tmp_path, collector=blocked, now=NOW, cache_minutes=30, stale_hours=24)
    assert decision.status == "STALE_FALLBACK"
    assert decision.snapshot.html_path == seeded.html_path


def test_blocked_source_without_snapshot_is_policy_denied(tmp_path):
    def blocked(*args, **kwargs):
        raise SourceBlockedError("403")
    with pytest.raises(SourceBlockedError):
        acquire_snapshot(request(), tmp_path, collector=blocked, now=NOW, cache_minutes=30, stale_hours=24)


def test_zero_row_parser_is_source_changed_and_snapshot_remains(tmp_path):
    ref = seed_snapshot(tmp_path, 1)
    class EmptyAdapter:
        name="x"
        kind="flights"
        def parse(self, html, metadata): return []
        def normalize(self, row, metadata, snapshot_id): return row
    with pytest.raises(Exception, match="zero rows"):
        parse_normalize_snapshot(EmptyAdapter(), ref)
    assert ref.html_path.exists()


def test_collect_stage_registers_snapshot_before_parser_can_fail(tmp_path, monkeypatch):
    import ingestion.flow as flow_module

    ref = seed_snapshot(tmp_path, 1)
    calls = []

    class Adapter:
        name = "wingo"
        kind = "flights"
        def build_requests(self):
            return [request()]

    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "_begin_run", lambda name: 77)

    def fake_dask(fn, *args):
        calls.append(fn.__name__)
        if fn.__name__ == "acquire_snapshot":
            return flow_module.AcquisitionDecision(ref, "SUCCESS")
        if fn.__name__ == "register_snapshot":
            return flow_module.snapshot_identity(ref)
        raise AssertionError(fn.__name__)

    monkeypatch.setattr(flow_module, "_dask_call", fake_dask)
    state = flow_module._collect_stage("wingo")

    assert state["error"] is None
    assert calls == ["acquire_snapshot", "register_snapshot"]


def test_prefect_flow_respects_enabled_source_registry(monkeypatch):
    import ingestion.flow as flow_module

    class Enabled:
        name = "wingo"

    monkeypatch.setattr(flow_module, "get_enabled_adapters", lambda: [Enabled()])
    monkeypatch.setattr(flow_module, "collect_wingo_flights", lambda: {"stage": "flight"})
    monkeypatch.setattr(flow_module, "parse_flights_task", lambda state: state)
    monkeypatch.setattr(flow_module, "normalize_flights_task", lambda state: state)
    monkeypatch.setattr(flow_module, "persist_flights_task", lambda state: "FLIGHT_RESULT")
    monkeypatch.setattr(flow_module, "collect_hotels", lambda: (_ for _ in ()).throw(AssertionError("hotel disabled")))
    monkeypatch.setattr(flow_module, "collect_cars", lambda: (_ for _ in ()).throw(AssertionError("car disabled")))

    assert flow_module.travel_scraping_flow() == ["FLIGHT_RESULT"]


def test_prefect_collect_task_raises_when_acquisition_is_unavailable(monkeypatch):
    import ingestion.flow as flow_module

    monkeypatch.setattr(
        flow_module,
        "_collect_stage",
        lambda name: {"adapter": name, "run_id": 1, "decision": None, "error": "timeout"},
    )

    with pytest.raises(flow_module.SourceUnavailableError, match="timeout"):
        flow_module.collect_flights()


def test_prefect_flow_submits_enabled_source_chains_before_waiting(monkeypatch):
    import ingestion.flow as flow_module

    events = []

    class Enabled:
        def __init__(self, name): self.name = name

    class Future:
        def __init__(self, value): self.value = value
        def result(self):
            events.append(("wait", self.value))
            return self.value

    class TaskSpy:
        def __init__(self, name): self.name = name
        def __call__(self, *args, **kwargs):
            raise AssertionError(f"{self.name} executed synchronously")
        def submit(self, *args, **kwargs):
            events.append(("submit", self.name))
            return Future(self.name)

    monkeypatch.setattr(flow_module, "get_enabled_adapters", lambda: [
        Enabled("wingo"), Enabled("ghl_porton_medellin"), Enabled("alkilautos_national_medellin")
    ])
    for name in (
        "collect_wingo_flights", "parse_flights_task", "normalize_flights_task", "persist_flights_task",
        "collect_hotels", "parse_hotels_task", "normalize_hotels_task", "persist_hotels_task",
        "collect_cars", "parse_cars_task", "normalize_cars_task", "persist_cars_task",
    ):
        monkeypatch.setattr(flow_module, name, TaskSpy(name))

    flow_module.travel_scraping_flow()

    first_wait = next(i for i, event in enumerate(events) if event[0] == "wait")
    assert len([e for e in events[:first_wait] if e[0] == "submit"]) == 12


def test_prefect_flow_returns_partial_results_when_one_source_future_fails(monkeypatch):
    import ingestion.flow as flow_module
    from ingestion.models import SourceRunResult

    class Enabled:
        def __init__(self, name): self.name = name

    class Future:
        def __init__(self, value=None, error=None):
            self.value = value
            self.error = error
        def result(self):
            if self.error:
                raise self.error
            return self.value

    monkeypatch.setattr(flow_module, "get_enabled_adapters", lambda: [
        Enabled("wingo"), Enabled("ghl_porton_medellin")
    ])

    def fake_submit_chain(collect_task, parse_task, normalize_task, persist_task):
        if collect_task is flow_module.collect_flights:
            return Future(error=RuntimeError("wingo unavailable"))
        return Future(value=SourceRunResult("ghl_porton_medellin", "hotels", "SUCCESS", 4))

    monkeypatch.setattr(flow_module, "_submit_chain", fake_submit_chain)

    results = flow_module.travel_scraping_flow()
    assert len(results) == 2
    assert results[0].source == "wingo"
    assert results[0].status == "SOURCE_UNAVAILABLE"
    assert "wingo unavailable" in (results[0].error_message or "")
    assert results[1].source == "ghl_porton_medellin"
    assert results[1].status == "SUCCESS"


def test_prefect_flow_runs_clicair_and_satena_as_independent_flight_sources(monkeypatch):
    import ingestion.flow as flow_module
    from ingestion.models import SourceRunResult

    class Enabled:
        def __init__(self, name): self.name = name

    class Future:
        def __init__(self, value): self.value = value
        def result(self): return self.value

    monkeypatch.setattr(flow_module, "get_enabled_adapters", lambda: [Enabled("clicair"), Enabled("satena")])
    monkeypatch.setattr(flow_module, "collect_clicair_flights", object(), raising=False)
    monkeypatch.setattr(flow_module, "collect_satena_flights", object(), raising=False)

    def fake_submit_chain(collect_task, parse_task, normalize_task, persist_task):
        if collect_task is flow_module.collect_clicair_flights:
            return Future(SourceRunResult("clicair", "flights", "SUCCESS", 10))
        if collect_task is flow_module.collect_satena_flights:
            return Future(SourceRunResult("satena", "flights", "SUCCESS", 10))
        raise AssertionError("unexpected source chain")

    monkeypatch.setattr(flow_module, "_submit_chain", fake_submit_chain)
    results = flow_module.travel_scraping_flow()
    assert [(r.source, r.status) for r in results] == [("clicair", "SUCCESS"), ("satena", "SUCCESS")]


def test_flight_source_batch_collects_every_request_and_registers_each_snapshot(tmp_path, monkeypatch):
    import ingestion.flow as flow_module
    from ingestion.models import ScrapeRequest

    requests = [
        ScrapeRequest("clicair", "flights", "https://example.test/out", "table", {"direction": "outbound"}),
        ScrapeRequest("clicair", "flights", "https://example.test/back", "table", {"direction": "return"}),
    ]
    refs = [seed_snapshot(tmp_path / "a", 1), seed_snapshot(tmp_path / "b", 1)]

    class Adapter:
        name = "clicair"
        kind = "flights"
        def build_requests(self): return requests

    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "_begin_run", lambda name: 10)
    collected = []
    registered = []
    ref_by_url = {requests[0].url: refs[0], requests[1].url: refs[1]}

    def fake_dask(fn, *args):
        if fn is flow_module.acquire_snapshot:
            collected.append(args[0].url)
            return flow_module.AcquisitionDecision(ref_by_url[args[0].url], "SUCCESS")
        if fn is flow_module.register_snapshot:
            registered.append(args[0].html_path)
            return flow_module.snapshot_identity(args[0])
        raise AssertionError(fn.__name__)

    monkeypatch.setattr(flow_module, "_dask_call", fake_dask)
    state = flow_module.collect_source_batch("clicair")
    assert sorted(collected) == sorted(r.url for r in requests)
    assert len(state["captures"]) == 2
    assert len(registered) == 2
    assert state["request_errors"] == []


def test_flight_source_batch_keeps_successful_direction_when_other_direction_fails(tmp_path, monkeypatch):
    import ingestion.flow as flow_module
    from ingestion.models import ScrapeRequest

    requests = [
        ScrapeRequest("clicair", "flights", "https://example.test/out", "table", {"direction": "outbound"}),
        ScrapeRequest("clicair", "flights", "https://example.test/back", "table", {"direction": "return"}),
    ]
    ref = seed_snapshot(tmp_path / "ok", 1)

    class Adapter:
        name = "clicair"
        kind = "flights"
        def build_requests(self): return requests

    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "_begin_run", lambda name: 11)
    def fake_dask(fn, *args):
        if fn is flow_module.acquire_snapshot:
            if args[0].url.endswith("/out"):
                return flow_module.AcquisitionDecision(ref, "SUCCESS")
            raise flow_module.SourceUnavailableError("return unavailable")
        if fn is flow_module.register_snapshot:
            return flow_module.snapshot_identity(args[0])
        raise AssertionError(fn.__name__)

    monkeypatch.setattr(flow_module, "_dask_call", fake_dask)
    state = flow_module.collect_source_batch("clicair")
    assert len(state["captures"]) == 1
    assert len(state["request_errors"]) == 1
    assert state["error"] is None


def test_batch_normalization_marks_empty_direction_as_partial_failure(monkeypatch, tmp_path):
    import ingestion.flow as flow_module

    ref1 = seed_snapshot(tmp_path / "a", 1)
    ref2 = seed_snapshot(tmp_path / "b", 1)
    d1 = flow_module.AcquisitionDecision(ref1, "SUCCESS")
    d2 = flow_module.AcquisitionDecision(ref2, "SUCCESS")
    state = {
        "adapter": "clicair",
        "run_id": 99,
        "captures": [d1, d2],
        "parsed_captures": [(d1, [{"x": 1}]), (d2, [{"x": 2}])],
        "request_errors": [],
        "error": None,
    }
    calls = 0
    def fake_dask(fn, *args):
        nonlocal calls
        assert fn is flow_module.normalize_rows
        calls += 1
        return [{"id": "ok"}] if calls == 1 else []
    monkeypatch.setattr(flow_module, "_dask_call", fake_dask)
    result = flow_module.normalize_source_batch(state)
    assert result["rows"] == [{"id": "ok"}]
    assert len(result["request_errors"]) == 1


def test_flight_source_batch_keeps_first_and_third_route_when_middle_acquisition_fails(tmp_path, monkeypatch):
    import ingestion.flow as flow_module
    from ingestion.models import ScrapeRequest

    requests = [
        ScrapeRequest("clicair", "flights", "https://example.test/r1", "table", {"route_key": "BOG-EOH"}),
        ScrapeRequest("clicair", "flights", "https://example.test/r2", "table", {"route_key": "BOG-CLO"}),
        ScrapeRequest("clicair", "flights", "https://example.test/r3", "table", {"route_key": "EOH-CTG"}),
    ]
    refs = [seed_snapshot(tmp_path / "a", 1), seed_snapshot(tmp_path / "c", 1)]

    class Adapter:
        name = "clicair"
        kind = "flights"
        def build_requests(self): return requests

    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "_begin_run", lambda name: 31)
    def fake_dask(fn, *args):
        if fn is flow_module.acquire_snapshot:
            url = args[0].url
            if url.endswith("/r2"):
                raise flow_module.SourceUnavailableError("middle route unavailable")
            return flow_module.AcquisitionDecision(refs[0 if url.endswith("/r1") else 1], "SUCCESS")
        if fn is flow_module.register_snapshot:
            return flow_module.snapshot_identity(args[0])
        raise AssertionError(fn.__name__)

    monkeypatch.setattr(flow_module, "_dask_call", fake_dask)
    state = flow_module.collect_source_batch("clicair")
    assert len(state["captures"]) == 2
    assert state["error"] is None
    assert state["request_errors"] == [
        {"url": "https://example.test/r2", "error": "SourceUnavailableError: middle route unavailable"}
    ]


def test_prefect_flow_runs_jetsmart_as_independent_flight_source(monkeypatch):
    import ingestion.flow as flow_module
    from ingestion.models import SourceRunResult

    class Enabled:
        name = "jetsmart"

    class Future:
        def result(self):
            return SourceRunResult("jetsmart", "flights", "SUCCESS", 7)

    monkeypatch.setattr(flow_module, "get_enabled_adapters", lambda: [Enabled()])
    monkeypatch.setattr(flow_module, "collect_jetsmart_flights", object(), raising=False)

    def fake_submit_chain(collect_task, parse_task, normalize_task, persist_task):
        assert collect_task is flow_module.collect_jetsmart_flights
        return Future()

    monkeypatch.setattr(flow_module, "_submit_chain", fake_submit_chain)
    results = flow_module.travel_scraping_flow()
    assert [(r.source, r.status, r.items_found) for r in results] == [("jetsmart", "SUCCESS", 7)]


def test_batch_normalization_tracks_successfully_observed_empty_route(monkeypatch, tmp_path):
    import ingestion.flow as flow_module
    from ingestion.models import ScrapeRequest

    ref = seed_snapshot(tmp_path / "empty", 1)
    decision = flow_module.AcquisitionDecision(ref, "SUCCESS")

    class Adapter:
        name = "clicair"
        kind = "flights"
        def build_requests(self):
            return [ScrapeRequest(
                "clicair", "flights", ref.metadata.source_url, "table",
                {"origin": "BOG", "destination": "CLO", "route_key": "BOG-CLO"},
            )]

    state = {
        "adapter": "clicair",
        "run_id": 100,
        "captures": [decision],
        "parsed_captures": [(decision, [])],
        "request_errors": [],
        "error": None,
    }
    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "_dask_call", lambda fn, *args: [])
    monkeypatch.setattr(flow_module, "_finish_run", lambda *args, **kwargs: None)

    result = flow_module.normalize_source_batch(state)

    assert result["empty_routes"] == [("BOG", "CLO")]
    assert result["error"] is None
    assert result["rows"] == []


def test_partial_batch_refresh_deactivates_observed_empty_route_but_not_unseen_route(monkeypatch, tmp_path):
    import ingestion.flow as flow_module

    ref = seed_snapshot(tmp_path / "ok", 1)
    row = {
        "id": "flight-1", "airline": "CLIC", "origin": "BOG", "destination": "EOH",
        "travel_date": "2026-11-01", "departure_at": None, "arrival_at": None,
        "price": 100000.0, "currency": "COP", "source": "clicair",
        "source_url": ref.metadata.source_url, "snapshot_id": "snap-1",
        "scraped_at": ref.metadata.captured_at, "active": True,
    }
    statements = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params=None): statements.append((" ".join(sql.split()), params))

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def cursor(self): return Cursor()

    monkeypatch.setattr(flow_module, "get_adapter", lambda name: type("A", (), {"name": "clicair", "kind": "flights"})())
    monkeypatch.setattr(flow_module, "register_snapshot", lambda snapshot: "snap-1")
    monkeypatch.setattr(flow_module, "_connect", lambda: Connection())

    flow_module.persist_catalog_batch(
        "clicair",
        [(ref, [row])],
        preserve_unseen_routes=True,
        empty_routes=[("BOG", "CLO")],
    )

    updates = [params for sql, params in statements if sql.startswith("UPDATE flights SET active=FALSE")]
    assert ("clicair", "BOG", "EOH") in updates
    assert ("clicair", "BOG", "CLO") in updates
    assert ("clicair", "EOH", "CTG") not in updates


def test_blocked_source_without_snapshot_preserves_policy_denial(tmp_path):
    def blocked(*args, **kwargs):
        raise SourceBlockedError("robots.txt disallows route")
    with pytest.raises(SourceBlockedError, match="robots.txt"):
        acquire_snapshot(request(), tmp_path, collector=blocked, now=NOW, cache_minutes=30, stale_hours=24)


def test_all_policy_blocked_batch_is_non_retryable_and_prefect_collect_does_not_raise(monkeypatch):
    import ingestion.flow as flow_module
    from ingestion.models import ScrapeRequest

    class Adapter:
        name = "jetsmart"; kind = "flights"
        def build_requests(self):
            return [
                ScrapeRequest("jetsmart", "flights", f"https://jetsmart.com/r{i}", "table", {"origin":"BOG","destination":"SMR"}, ("jetsmart.com",), "http")
                for i in range(3)
            ]
    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "_begin_run", lambda name: 1)
    monkeypatch.setattr(flow_module, "_finish_run", lambda *a, **k: None)
    monkeypatch.setattr(flow_module, "_dask_call", lambda fn, *args: (_ for _ in ()).throw(SourceBlockedError("robots denied")) if fn is flow_module.acquire_snapshot else None)
    state = flow_module._prefect_collect("jetsmart")
    assert state["non_retryable"] is True
    assert state["error"] == "ROBOTS_DISALLOWED"
    assert len(state["request_errors"]) == 3


def test_batch_route_acquisition_never_exceeds_two_concurrent_requests(monkeypatch):
    import threading, time
    import ingestion.flow as flow_module
    from ingestion.models import ScrapeRequest, SnapshotMetadata, SnapshotRef
    from pathlib import Path

    class Adapter:
        name = "jetsmart"; kind = "flights"
        def build_requests(self):
            return [ScrapeRequest("jetsmart","flights",f"https://jetsmart.com/r{i}","table",{"origin":"BOG","destination":"SMR"},("jetsmart.com",),"http") for i in range(4)]
    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "_begin_run", lambda name: 1)
    monkeypatch.setattr(flow_module, "_finish_run", lambda *a, **k: None)
    lock = threading.Lock(); active = 0; peak = 0
    def fake_dask(fn, *args):
        nonlocal active, peak
        if fn is flow_module.acquire_snapshot:
            with lock:
                active += 1; peak = max(peak, active)
            time.sleep(0.03)
            req=args[0]
            meta=SnapshotMetadata(req.source, req.kind, req.url, req.url.rsplit('/',1)[-1], NOW.isoformat(), 200, "SUCCESS")
            ref=SnapshotRef(Path('/tmp/x.html'), Path('/tmp/x.json'), meta)
            with lock: active -= 1
            return flow_module.AcquisitionDecision(ref,"SUCCESS")
        return "ok"
    monkeypatch.setattr(flow_module, "_dask_call", fake_dask)
    state=flow_module.collect_source_batch("jetsmart")
    assert len(state["captures"]) == 4
    assert peak == 2
