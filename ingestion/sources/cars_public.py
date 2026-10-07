from __future__ import annotations

from ingestion.models import ScrapeRequest, SnapshotMetadata
from ingestion.normalization.cars import normalize_car
from ingestion.parsers.cars import parse_cars


class NationalMedellinCarsAdapter:
    name = "alkilautos_national_medellin"
    kind = "cars"
    attribution = "Alkilautos public National Medellín vehicle offers"
    allowed_hosts = {"alkilautos.com", "www.alkilautos.com"}
    url = "https://alkilautos.com/alquiler-carros-medellin/ciudad/national/"

    def build_requests(self) -> list[ScrapeRequest]:
        return [ScrapeRequest(self.name, self.kind, self.url, "text=Precio por día", {"city": "MDE", "provider": "National"}, tuple(sorted(self.allowed_hosts)))]

    def ready_selector(self, request: ScrapeRequest) -> str:
        return request.ready_selector

    def parse(self, html: str, metadata: SnapshotMetadata) -> list[dict]:
        return parse_cars(html, metadata)

    def normalize(self, row: dict, metadata: SnapshotMetadata, snapshot_id: str) -> dict | None:
        return normalize_car(row, source=self.name, source_url=metadata.source_url, snapshot_id=snapshot_id, scraped_at=metadata.captured_at)
