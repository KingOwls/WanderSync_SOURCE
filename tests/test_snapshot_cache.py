from datetime import datetime, timedelta, timezone
import hashlib
import json

from ingestion.models import ScrapeRequest, SnapshotMetadata
from ingestion.policies.cache import classify_snapshot_age
from ingestion.snapshots.manager import latest_snapshot, save_snapshot, snapshot_key


def _request(**query):
    return ScrapeRequest(
        source="wingo",
        kind="flights",
        url="https://www.wingo.com/es/vuelos-nacionales",
        ready_selector="body",
        query=query or {"market": "CO"},
    )


def test_snapshot_key_is_deterministic_across_query_order():
    a = _request(origin="BOG", destination="MDE")
    b = _request(destination="MDE", origin="BOG")
    assert snapshot_key(a) == snapshot_key(b)
    assert len(snapshot_key(a)) == 64


def test_save_snapshot_writes_html_and_metadata_with_sha256(tmp_path):
    req = _request(origin="BOG", destination="MDE")
    captured = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc)
    metadata = SnapshotMetadata.from_request(req, captured_at=captured, http_status=200, status="SUCCESS")
    ref = save_snapshot("<html>real public page</html>", metadata, tmp_path)

    assert ref.html_path.exists()
    assert ref.metadata_path.exists()
    payload = json.loads(ref.metadata_path.read_text(encoding="utf-8"))
    assert payload["html_sha256"] == hashlib.sha256(b"<html>real public page</html>").hexdigest()
    assert payload["source"] == "wingo"
    assert payload["query_hash"] == snapshot_key(req)


def test_latest_snapshot_only_matches_source_kind_and_query(tmp_path):
    captured = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc)
    req = _request(origin="BOG", destination="MDE")
    ref = save_snapshot("<html>one</html>", SnapshotMetadata.from_request(req, captured, 200, "SUCCESS"), tmp_path)
    other = _request(origin="BOG", destination="CTG")
    save_snapshot("<html>two</html>", SnapshotMetadata.from_request(other, captured, 200, "SUCCESS"), tmp_path)

    found = latest_snapshot("wingo", "flights", snapshot_key(req), tmp_path)
    assert found is not None
    assert found.html_path == ref.html_path
    assert latest_snapshot("wingo", "hotels", snapshot_key(req), tmp_path) is None


def test_cache_age_boundaries():
    now = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)
    assert classify_snapshot_age(now - timedelta(minutes=30), now, 30, 24) == "FRESH"
    assert classify_snapshot_age(now - timedelta(minutes=31), now, 30, 24) == "STALE"
    assert classify_snapshot_age(now - timedelta(hours=24), now, 30, 24) == "STALE"
    assert classify_snapshot_age(now - timedelta(hours=24, seconds=1), now, 30, 24) == "EXPIRED"
