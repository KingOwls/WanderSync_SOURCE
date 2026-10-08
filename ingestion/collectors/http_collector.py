from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx

from ingestion.collectors.base import SourceBlockedError, SourceUnavailableError
from ingestion.collectors.playwright_collector import _validate_resolved_host, _validate_url
from ingestion.models import CaptureResult, ScrapeRequest, SnapshotMetadata
from ingestion.policies.pacing import mark_source_run, pacing_delay, source_lock, shared_pacing_delay, mark_shared_source_run
from ingestion.policies.retry import backoff_seconds, retry_after_seconds, should_retry_status
from ingestion.policies.robots import USER_AGENT, robots_allowed
from ingestion.snapshots.manager import save_snapshot


def collect_http(request: ScrapeRequest, snapshot_root: str | Path, timeout_seconds: int = 45) -> CaptureResult:
    allowed = set(request.allowed_hosts)
    if not allowed:
        raise SourceBlockedError("Adapter did not provide an allowlist")
    _validate_url(request.url, allowed)
    _validate_resolved_host(request.url)
    if not robots_allowed(request.url):
        raise SourceBlockedError("robots.txt disallows this path for the WanderSync academic bot")

    min_interval = int(os.getenv("SCRAPE_MIN_INTERVAL_SECONDS", "90"))
    max_interval = int(os.getenv("SCRAPE_MAX_INTERVAL_SECONDS", "180"))
    retry_limit = int(os.getenv("SCRAPE_RETRY_LIMIT", "2"))

    with source_lock(request.source, snapshot_root):
        delay = max(pacing_delay(request.source, min_interval, max_interval), shared_pacing_delay(request.source, snapshot_root, min_interval, max_interval))
        if delay:
            time.sleep(delay)
        mark_shared_source_run(request.source, snapshot_root)
        last_error: Exception | None = None
        for attempt in range(1, retry_limit + 2):
            try:
                next_url = request.url
                for redirect in range(6):
                    _validate_url(next_url, allowed)
                    _validate_resolved_host(next_url)
                    if not robots_allowed(next_url):
                        raise SourceBlockedError("robots.txt disallows redirected path")
                    response = httpx.get(
                        next_url,
                    timeout=timeout_seconds,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                        follow_redirects=False,
                    )
                    if response.status_code not in {301,302,303,307,308}:
                        break
                    location = response.headers.get("location")
                    if not location or redirect == 5:
                        raise SourceUnavailableError("Invalid or excessive redirects")
                    next_url = urljoin(next_url, location)
                final_url = str(response.url)
                _validate_url(final_url, allowed)
                _validate_resolved_host(final_url)
                if not robots_allowed(final_url):
                    raise SourceBlockedError("robots.txt disallows the redirected path for the WanderSync academic bot")

                status = response.status_code
                if status == 403:
                    raise SourceBlockedError("Source returned HTTP 403")
                if status >= 400:
                    if should_retry_status(status) and attempt <= retry_limit:
                        retry_after = retry_after_seconds(response.headers)
                        time.sleep(retry_after if retry_after is not None else backoff_seconds(attempt))
                        continue
                    raise SourceUnavailableError(f"Source returned HTTP {status}")

                html = response.text
                if not html.strip():
                    raise SourceUnavailableError("Source returned an empty HTML document")
                metadata = SnapshotMetadata.from_request(
                    request, datetime.now(timezone.utc), status, "SUCCESS"
                )
                metadata.source_url = final_url
                ref = save_snapshot(html, metadata, snapshot_root)
                mark_source_run(request.source)
                return CaptureResult(snapshot=ref)
            except SourceBlockedError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt > retry_limit:
                    break
                time.sleep(backoff_seconds(attempt))
        raise SourceUnavailableError(f"Source acquisition failed after bounded retries: {last_error}")
