from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import os
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

from ingestion.collectors.base import SourceBlockedError, SourceChangedError, SourceUnavailableError
from ingestion.models import CaptureResult, ScrapeRequest, SnapshotMetadata
from ingestion.policies.pacing import mark_source_run, pacing_delay, source_lock
from ingestion.policies.robots import USER_AGENT, robots_allowed
from ingestion.policies.retry import backoff_seconds, retry_after_seconds, should_retry_status
from ingestion.snapshots.manager import save_snapshot


def _validate_url(url: str, allowed_hosts: set[str]) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SourceBlockedError("Only HTTP(S) public sources are permitted")
    host = (parsed.hostname or "").lower().rstrip(".")
    normalized = {h.lower().rstrip(".") for h in allowed_hosts}
    if not host or host not in normalized:
        raise SourceBlockedError(f"Host is not allowlisted: {host or '<missing>'}")
    if host == "localhost" or host.endswith(".localhost"):
        raise SourceBlockedError("Localhost is not a scraping source")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise SourceBlockedError("Private, loopback, link-local, multicast and reserved IPs are rejected")


def validate_request_url(request: ScrapeRequest, allowed_hosts: set[str]) -> None:
    _validate_url(request.url, allowed_hosts)


def _validate_resolved_host(url: str) -> None:
    host = urlparse(url).hostname
    if not host:
        raise SourceBlockedError("Missing host")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise SourceUnavailableError(f"DNS resolution failed for {host}: {exc}") from exc
    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not ip.is_global:
            raise SourceBlockedError(f"Resolved address is not public: {ip}")


def _looks_like_challenge(html: str) -> bool:
    """Detect blocking challenge pages without flagging ordinary sites that merely load CAPTCHA scripts."""
    lower = html.lower()
    strong_signals = (
        "verify you are human",
        "cf-chl-",
        "challenge-platform",
        "access denied",
        "just a moment...",
        "checking your browser before accessing",
    )
    return any(signal in lower for signal in strong_signals)


def collect_html(request: ScrapeRequest, snapshot_root: str | Path, timeout_seconds: int = 45) -> CaptureResult:
    allowed = set(request.allowed_hosts)
    if not allowed:
        raise SourceBlockedError("Adapter did not provide an allowlist")
    validate_request_url(request, allowed)
    _validate_resolved_host(request.url)
    if not robots_allowed(request.url):
        raise SourceBlockedError("robots.txt disallows this path for the WanderSync academic bot")

    min_interval = int(os.getenv("SCRAPE_MIN_INTERVAL_SECONDS", "90"))
    max_interval = int(os.getenv("SCRAPE_MAX_INTERVAL_SECONDS", "180"))
    retry_limit = int(os.getenv("SCRAPE_RETRY_LIMIT", "2"))

    with source_lock(request.source, snapshot_root):
        delay = pacing_delay(request.source, min_interval, max_interval)
        if delay:
            time.sleep(delay)
        last_error: Exception | None = None
        for attempt in range(1, retry_limit + 2):
            try:
                from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
                from playwright.sync_api import sync_playwright

                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True)
                    context = browser.new_context(user_agent=USER_AGENT)
                    page = context.new_page()
                    response = page.goto(request.url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
                    _validate_url(page.url, allowed)
                    _validate_resolved_host(page.url)
                    if not robots_allowed(page.url):
                        raise SourceBlockedError("robots.txt disallows the redirected path for the WanderSync academic bot")
                    status = response.status if response else None
                    if status == 403:
                        raise SourceBlockedError("Source returned HTTP 403")
                    if status and status >= 400:
                        if should_retry_status(status) and attempt <= retry_limit:
                            retry_after = retry_after_seconds(response.headers)
                            context.close(); browser.close()
                            time.sleep(retry_after if retry_after is not None else backoff_seconds(attempt))
                            continue
                        raise SourceUnavailableError(f"Source returned HTTP {status}")
                    try:
                        page.locator(request.ready_selector).first.wait_for(state="attached", timeout=timeout_seconds * 1000)
                    except PlaywrightTimeoutError as exc:
                        raise SourceChangedError(f"Ready selector not found: {request.ready_selector}") from exc
                    html = page.content()
                    context.close(); browser.close()
                    if _looks_like_challenge(html):
                        raise SourceBlockedError("Challenge/CAPTCHA page detected; no bypass attempted")
                    metadata = SnapshotMetadata.from_request(
                        request, datetime.now(timezone.utc), status, "SUCCESS"
                    )
                    ref = save_snapshot(html, metadata, snapshot_root)
                    mark_source_run(request.source)
                    return CaptureResult(snapshot=ref)
            except (SourceBlockedError, SourceChangedError):
                raise
            except Exception as exc:
                last_error = exc
                if attempt > retry_limit:
                    break
                time.sleep(backoff_seconds(attempt))
        raise SourceUnavailableError(f"Source acquisition failed after bounded retries: {last_error}")
