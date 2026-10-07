from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from ingestion.models import ScrapeRequest, SnapshotMetadata, SnapshotRef
from ingestion.snapshots.metadata import read_metadata, write_metadata


def snapshot_key(request: ScrapeRequest) -> str:
    payload = {
        "source": request.source,
        "kind": request.kind,
        "url": request.url,
        "query": request.query,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "unknown"


def _root(root: str | Path) -> Path:
    return Path(root)


def save_snapshot(html: str, metadata: SnapshotMetadata, root: str | Path) -> SnapshotRef:
    target = _root(root) / _safe(metadata.kind) / _safe(metadata.source) / metadata.query_hash
    target.mkdir(parents=True, exist_ok=True)
    captured = datetime.fromisoformat(metadata.captured_at)
    stamp = captured.strftime("%Y%m%dT%H%M%S%fZ")
    html_path = target / f"{stamp}.html"
    meta_path = target / f"{stamp}.json"
    data = html.encode("utf-8")
    metadata.html_sha256 = hashlib.sha256(data).hexdigest()
    html_path.write_bytes(data)
    write_metadata(meta_path, metadata)
    return SnapshotRef(html_path=html_path, metadata_path=meta_path, metadata=metadata)


def latest_snapshot(source: str, kind: str, query_hash: str, root: str | Path) -> SnapshotRef | None:
    target = _root(root) / _safe(kind) / _safe(source) / query_hash
    if not target.exists():
        return None
    candidates = sorted(target.glob("*.json"), reverse=True)
    for meta_path in candidates:
        html_path = meta_path.with_suffix(".html")
        if not html_path.exists():
            continue
        metadata = read_metadata(meta_path)
        if metadata.source == source and metadata.kind == kind and metadata.query_hash == query_hash:
            return SnapshotRef(html_path=html_path, metadata_path=meta_path, metadata=metadata)
    return None
