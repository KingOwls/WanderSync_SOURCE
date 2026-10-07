from __future__ import annotations

from ingestion.models import ScrapeRequest, SnapshotMetadata
from ingestion.normalization.flights import normalize_flight
from ingestion.parsers.latam_flights import parse_latam_flights
from ingestion.sources.flight_routes import routes_for_source


class LatamFlightsAdapter:
    name = "latam"
    kind = "flights"
    attribution = "LATAM public Colombia destination offer pages"
    allowed_hosts = {"www.latamairlines.com", "latamairlines.com"}
    _routes = routes_for_source(name)
    url = _routes[0].url

    def build_requests(self) -> list[ScrapeRequest]:
        allowed = tuple(sorted(self.allowed_hosts))
        return [
            ScrapeRequest(
                self.name,
                self.kind,
                route.url,
                "body",
                {"origin": route.origin, "destination": route.destination, "route_key": route.route_key},
                allowed,
                route.acquisition_mode,
            )
            for route in self._routes
        ]

    def ready_selector(self, request: ScrapeRequest) -> str:
        return request.ready_selector

    def parse(self, html: str, metadata: SnapshotMetadata) -> list[dict]:
        return parse_latam_flights(html, metadata)

    def normalize(self, row: dict, metadata: SnapshotMetadata, snapshot_id: str) -> dict | None:
        return normalize_flight(
            row,
            source=self.name,
            source_url=metadata.source_url,
            snapshot_id=snapshot_id,
            scraped_at=metadata.captured_at,
        )
