from backend.gateway.source_health import ACTIVE_FLIGHT_SOURCES, build_source_health_summary


def test_source_health_uses_exact_four_productive_sources_and_sanitizes_errors():
    rows = [
        {"source":"clicair","status":"SUCCESS","items_found":47,"finished_at":"2026-10-07T01:00:00","error_message":"secret"},
        {"source":"satena","status":"CACHED","items_found":30,"finished_at":"2026-10-07T01:00:00"},
        {"source":"jetsmart","status":"STALE_FALLBACK","items_found":4,"finished_at":"2026-10-07T01:00:00"},
        {"source":"latam","status":"SUCCESS","items_found":99,"finished_at":"2026-10-07T01:00:00"},
    ]
    result=build_source_health_summary(rows)
    assert ACTIVE_FLIGHT_SOURCES == ("clicair","satena","jetsmart","wingo")
    assert result["total_count"]==4
    assert result["active_count"]==3
    by={x["source"]:x for x in result["sources"]}
    assert by["wingo"]["status"]=="NOT_RUN" and by["wingo"]["available"] is False
    assert "error_message" not in by["clicair"]
    assert "latam" not in by
