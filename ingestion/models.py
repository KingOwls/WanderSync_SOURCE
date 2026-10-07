from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScrapeRequest:
    source: str
    kind: str
    url: str
    ready_selector: str
    query: dict[str, Any] = field(default_factory=dict)
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)
    transport: str = "browser"


@dataclass
class SnapshotMetadata:
    source: str
    kind: str
    source_url: str
    query_hash: str
    captured_at: str
    http_status: int | None
    status: str
    html_sha256: str | None = None
    error_message: str | None = None

    @classmethod
    def from_request(
        cls,
        request: ScrapeRequest,
        captured_at: datetime,
        http_status: int | None,
        status: str,
        *,
        error_message: str | None = None,
    ) -> "SnapshotMetadata":
        from ingestion.snapshots.manager import snapshot_key

        return cls(
            source=request.source,
            kind=request.kind,
            source_url=request.url,
            query_hash=snapshot_key(request),
            captured_at=captured_at.isoformat(),
            http_status=http_status,
            status=status,
            error_message=error_message,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SnapshotRef:
    html_path: Path
    metadata_path: Path
    metadata: SnapshotMetadata


@dataclass(frozen=True)
class CaptureResult:
    snapshot: SnapshotRef
    from_cache: bool = False
    stale_fallback: bool = False


@dataclass(frozen=True)
class SourceRunResult:
    source: str
    kind: str
    status: str
    items_found: int
    snapshot_path: str | None = None
    error_message: str | None = None
