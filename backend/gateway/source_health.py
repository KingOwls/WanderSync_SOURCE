from __future__ import annotations

ACTIVE_FLIGHT_SOURCES = ("clicair", "satena", "jetsmart", "wingo")
AVAILABLE_STATUSES = {"SUCCESS", "CACHED", "STALE_FALLBACK"}


def build_source_health_summary(rows: list[dict]) -> dict:
    latest = {str(row.get("source")): row for row in rows if row.get("source") in ACTIVE_FLIGHT_SOURCES}
    sources = []
    for source in ACTIVE_FLIGHT_SOURCES:
        row = latest.get(source) or {}
        status = str(row.get("status") or "NOT_RUN")
        sources.append({
            "source": source,
            "status": status,
            "available": status in AVAILABLE_STATUSES,
            "items_found": int(row.get("items_found") or 0),
            "finished_at": str(row["finished_at"]) if row.get("finished_at") is not None else None,
        })
    return {
        "active_count": sum(1 for item in sources if item["available"]),
        "total_count": len(ACTIVE_FLIGHT_SOURCES),
        "sources": sources,
    }
