from __future__ import annotations

from ingestion.models import ScrapeRequest, SnapshotMetadata
from ingestion.normalization.hotels import normalize_hotel
from ingestion.parsers.hotels import parse_hotels


class GHLPortonMedellinAdapter:
    name = "ghl_porton_medellin"
    kind = "hotels"
    attribution = "GHL Portón Medellín public room offers"
    allowed_hosts = {"www.ghlhoteles.com", "ghlhoteles.com"}
    url = "https://www.ghlhoteles.com/es/hoteles/colombia/medellin/ghl-porton-medellin/"

    def build_requests(self) -> list[ScrapeRequest]:
        return [ScrapeRequest(self.name, self.kind, self.url, "text=COP", {"city": "MDE"}, tuple(sorted(self.allowed_hosts)))]

    def ready_selector(self, request: ScrapeRequest) -> str:
        return request.ready_selector

    def parse(self, html: str, metadata: SnapshotMetadata) -> list[dict]:
        return parse_hotels(html, metadata)

    def normalize(self, row: dict, metadata: SnapshotMetadata, snapshot_id: str) -> dict | None:
        return normalize_hotel(row, source=self.name, source_url=metadata.source_url, snapshot_id=snapshot_id, scraped_at=metadata.captured_at)
