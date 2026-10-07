from __future__ import annotations

from typing import Protocol

from ingestion.models import ScrapeRequest, SnapshotMetadata


class SourceAdapter(Protocol):
    name: str
    kind: str
    attribution: str
    allowed_hosts: set[str]

    def build_requests(self) -> list[ScrapeRequest]: ...
    def ready_selector(self, request: ScrapeRequest) -> str: ...
    def parse(self, html: str, metadata: SnapshotMetadata) -> list[dict]: ...
    def normalize(self, row: dict, metadata: SnapshotMetadata, snapshot_id: str) -> dict | None: ...
