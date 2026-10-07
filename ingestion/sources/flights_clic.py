from __future__ import annotations

from ingestion.models import ScrapeRequest, SnapshotMetadata
from ingestion.normalization.flights import normalize_flight
from ingestion.parsers.flights import is_one_way_trip_type, parse_flights
from ingestion.sources.flight_routes import routes_for_source


class ClicAirFlightsAdapter:
    name = "clicair"
    kind = "flights"
    attribution = "CLIC public Colombia fare tables"
    allowed_hosts = {"clicair.co", "www.clicair.co"}
    _routes = routes_for_source(name)
    url = _routes[0].url
    return_url = _routes[1].url

    def build_requests(self) -> list[ScrapeRequest]:
        allowed = tuple(sorted(self.allowed_hosts))
        return [
            ScrapeRequest(
                self.name,
                self.kind,
                route.url,
                "table",
                {"origin": route.origin, "destination": route.destination, "route_key": route.route_key},
                allowed,
                route.acquisition_mode,
            )
            for route in self._routes
        ]

    def ready_selector(self, request: ScrapeRequest) -> str:
        return request.ready_selector

    def parse(self, html: str, metadata: SnapshotMetadata) -> list[dict]:
        rows = parse_flights(html, metadata)
        return [row for row in rows if is_one_way_trip_type(row.get("trip_type"))]

    def normalize(self, row: dict, metadata: SnapshotMetadata, snapshot_id: str) -> dict | None:
        return normalize_flight(
            row,
            source=self.name,
            source_url=metadata.source_url,
            snapshot_id=snapshot_id,
            scraped_at=metadata.captured_at,
        )
