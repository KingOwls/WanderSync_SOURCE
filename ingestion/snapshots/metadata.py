from __future__ import annotations

import json
from pathlib import Path

from ingestion.models import SnapshotMetadata


def write_metadata(path: Path, metadata: SnapshotMetadata) -> None:
    path.write_text(json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def read_metadata(path: Path) -> SnapshotMetadata:
    return SnapshotMetadata(**json.loads(path.read_text(encoding="utf-8")))
