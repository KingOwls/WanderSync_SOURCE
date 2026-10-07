from pathlib import Path

SQL = (Path(__file__).parents[1] / "infra" / "postgres" / "init.sql").read_text(encoding="utf-8").lower()


def test_schema_has_scrape_observability_tables_and_provenance():
    assert "create table if not exists scrape_snapshots" in SQL
    assert "create table if not exists scrape_runs" in SQL
    for table in ("flights", "hotels", "cars"):
        block = SQL.split(f"create table if not exists {table}", 1)[1].split(");", 1)[0]
        for field in ("source", "source_url", "scraped_at", "snapshot_id", "active"):
            assert field in block


def test_catalog_definitions_remove_fake_external_inventory_columns():
    flight = SQL.split("create table if not exists flights", 1)[1].split(");", 1)[0]
    hotel = SQL.split("create table if not exists hotels", 1)[1].split(");", 1)[0]
    car = SQL.split("create table if not exists cars", 1)[1].split(");", 1)[0]
    assert "available_seats" not in flight
    assert "available_rooms" not in hotel
    assert "available_units" not in car
    # Migration is allowed to mention legacy names only to drop them.
    assert "drop column if exists available_seats" in SQL
    assert "drop column if exists available_rooms" in SQL
    assert "drop column if exists available_units" in SQL


def test_optional_source_fields_are_nullable_and_flight_has_travel_date():
    flight = SQL.split("create table if not exists flights", 1)[1].split(");", 1)[0]
    hotel = SQL.split("create table if not exists hotels", 1)[1].split(");", 1)[0]
    car = SQL.split("create table if not exists cars", 1)[1].split(");", 1)[0]
    assert "travel_date date not null" in flight
    assert "departure_at timestamptz" in flight and "departure_at timestamptz not null" not in flight
    assert "arrival_at timestamptz" in flight and "arrival_at timestamptz not null" not in flight
    assert "rating numeric(2,1)" in hotel and "rating numeric(2,1) not null" not in hotel
    assert "category text" in car and "category text not null" not in car


def test_legacy_catalog_cleanup_removes_events_for_any_legacy_offer_type():
    for table in ("billing_events", "saga_events"):
        statement = SQL.split(f"delete from {table}", 1)[1].split(";", 1)[0]
        assert "flight_id" in statement
        assert "hotel_id" in statement
        assert "car_id" in statement


def test_legacy_migration_adds_index_columns_before_creating_indexes():
    required_order = (
        ("alter table flights add column if not exists travel_date", "create index if not exists idx_flights_route"),
        ("alter table hotels add column if not exists active", "create index if not exists idx_hotels_city"),
        ("alter table cars add column if not exists active", "create index if not exists idx_cars_city"),
    )
    for migration, index in required_order:
        assert SQL.index(migration) < SQL.index(index), f"{migration} must run before {index}"


def test_flight_batch_persistence_deactivates_source_once(monkeypatch, tmp_path):
    import ingestion.flow as flow_module
    from ingestion.models import SnapshotMetadata, SnapshotRef
    from datetime import datetime, timezone

    class Adapter:
        name = "clicair"
        kind = "flights"
    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "register_snapshot", lambda ref: "SNAP-X")

    executed = []
    class Cursor:
        def execute(self, sql, params=None): executed.append((" ".join(sql.split()), params))
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Conn:
        def cursor(self): return Cursor()
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(flow_module, "_connect", lambda: Conn())

    now = datetime(2026, 10, 6, tzinfo=timezone.utc).isoformat()
    meta = SnapshotMetadata("clicair", "flights", "https://x", "q", now, 200, "SUCCESS")
    path = tmp_path / "x.html"; path.write_text("<html></html>")
    ref = SnapshotRef(path, tmp_path / "x.json", meta)
    base = dict(id="F1", airline="CLIC", origin="BOG", destination="EOH", travel_date="2026-10-10",
                departure_at=None, arrival_at=None, price=100000, currency="COP", source="clicair",
                source_url="https://x", snapshot_id="SNAP-X", scraped_at=now, active=True)
    row2 = dict(base, id="F2", origin="EOH", destination="BOG")

    result = flow_module.persist_catalog_batch("clicair", [(ref, [base]), (ref, [row2])])
    deactivations = [sql for sql, _ in executed if "UPDATE flights SET active=FALSE" in sql]
    inserts = [sql for sql, _ in executed if "INSERT INTO flights" in sql]
    assert len(deactivations) == 1
    assert len(inserts) == 2
    assert result["rows"] == 2


def test_partial_flight_batch_refresh_deactivates_only_successful_routes(monkeypatch, tmp_path):
    import ingestion.flow as flow_module
    from ingestion.models import SnapshotMetadata, SnapshotRef
    from datetime import datetime, timezone

    class Adapter:
        name = "clicair"
        kind = "flights"
    monkeypatch.setattr(flow_module, "get_adapter", lambda name: Adapter())
    monkeypatch.setattr(flow_module, "register_snapshot", lambda ref: "SNAP-X")
    executed = []
    class Cursor:
        def execute(self, sql, params=None): executed.append((" ".join(sql.split()), params))
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Conn:
        def cursor(self): return Cursor()
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(flow_module, "_connect", lambda: Conn())

    now = datetime(2026, 10, 6, tzinfo=timezone.utc).isoformat()
    meta = SnapshotMetadata("clicair", "flights", "https://x", "q", now, 200, "SUCCESS")
    path = tmp_path / "x.html"; path.write_text("<html></html>")
    ref = SnapshotRef(path, tmp_path / "x.json", meta)
    row = dict(id="F1", airline="CLIC", origin="BOG", destination="EOH", travel_date="2026-10-10",
               departure_at=None, arrival_at=None, price=100000, currency="COP", source="clicair",
               source_url="https://x", snapshot_id="SNAP-X", scraped_at=now, active=True)

    flow_module.persist_catalog_batch("clicair", [(ref, [row])], preserve_unseen_routes=True)
    updates = [(sql, params) for sql, params in executed if "UPDATE flights SET active=FALSE" in sql]
    assert len(updates) == 1
    assert "origin=%s AND destination=%s" in updates[0][0]
    assert updates[0][1] == ("clicair", "BOG", "EOH")
