from pathlib import Path
import sys

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import types

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    psycopg.connect = lambda *args, **kwargs: None
    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows


def test_routes_endpoint_aggregates_only_active_airport_pairs(monkeypatch):
    import backend.flight_service.main as service

    captured = {}
    expected = [{
        "origin": "EOH", "destination": "CLO", "offer_count": 3,
        "sources": ["clicair", "satena"], "first_date": "2026-10-10",
        "last_date": "2026-11-01", "lowest_price": 155000.0,
    }]

    def fake_fetch_all(sql, params=()):
        captured["sql"] = " ".join(sql.lower().split())
        captured["params"] = params
        return expected

    monkeypatch.setattr(service, "fetch_all", fake_fetch_all)
    rows = service.list_routes()
    sql = captured["sql"]
    assert "from flights" in sql
    assert "active=true" in sql
    assert "travel_date >=" in sql
    assert "48 hours" in sql
    assert "group by origin, destination" in sql
    assert "count(*)" in sql
    assert "array_agg(distinct source" in sql
    assert "min(travel_date)" in sql
    assert "max(travel_date)" in sql
    assert "min(price)" in sql
    assert rows == expected
