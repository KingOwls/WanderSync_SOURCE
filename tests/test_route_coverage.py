from copy import deepcopy

from backend.gateway.route_coverage import (
    TARGET_OFFERS_PER_DIRECTION,
    build_direction_coverage,
    select_direction_offers,
    supported_city_pairs,
)


def _row(i, source="clicair", origin="BOG", destination="EOH", day=None, price=None, trip_type="Solo ida"):
    return {
        "id": f"f{i}", "source": source, "origin": origin, "destination": destination,
        "travel_date": day or f"2026-10-{i:02d}", "price": price if price is not None else 100000 + i,
        "currency": "COP", "trip_type": trip_type, "active": True,
    }


def test_select_direction_offers_caps_at_ten_without_mutating_input():
    rows = [_row(i, source=("clicair","satena","jetsmart","wingo")[i % 4]) for i in range(1, 15)]
    original = deepcopy(rows)
    selected = select_direction_offers(rows, origin="BOG", destination="MDE")
    assert TARGET_OFFERS_PER_DIRECTION == 10
    assert len(selected) == 10
    assert rows == original
    assert [r["travel_date"] for r in selected] == sorted(r["travel_date"] for r in selected)


def test_dedup_keeps_different_source_or_price_on_same_date():
    a = _row(1, source="clicair", day="2026-10-18", price=190000)
    duplicate = dict(a)
    b = _row(2, source="satena", day="2026-10-18", price=190000)
    c = _row(3, source="clicair", day="2026-10-18", price=195000)
    selected = select_direction_offers([a, duplicate, b, c], origin="BOG", destination="MDE")
    assert len(selected) == 3


def test_medellin_airports_consolidate_and_twenty_pairs_are_searchable():
    eoh = _row(1, origin="BOG", destination="EOH")
    mde = _row(2, origin="BOG", destination="MDE")
    selected = select_direction_offers([eoh, mde], origin="BOG", destination="MDE")
    assert {r["destination"] for r in selected} == {"EOH", "MDE"}
    pairs = supported_city_pairs()
    assert len(pairs) == 20
    assert ("BOG", "SMR") in pairs
    assert all(a != b for a, b in pairs)


def test_direction_coverage_statuses_are_truthful():
    healthy = {s: "SUCCESS" for s in ("clicair", "satena", "jetsmart", "wingo")}
    expected = tuple(healthy)
    full = build_direction_coverage([_row(i) for i in range(1, 12)], origin="BOG", destination="MDE", source_health=healthy, expected_sources=expected)
    assert (full.status, full.raw_count, full.visible_count) == ("AVAILABLE", 11, 10)
    partial = build_direction_coverage([_row(1)], origin="BOG", destination="MDE", source_health=healthy, expected_sources=expected)
    assert partial.status == "PARTIAL"
    none = build_direction_coverage([], origin="BOG", destination="SMR", source_health=healthy, expected_sources=expected)
    assert none.status == "NO_OFFERS"
    broken_health = dict(healthy); broken_health["wingo"] = "SOURCE_UNAVAILABLE"
    unavailable = build_direction_coverage([], origin="BOG", destination="SMR", source_health=broken_health, expected_sources=expected)
    assert unavailable.status == "SOURCE_UNAVAILABLE"
    assert unavailable.offers == ()
