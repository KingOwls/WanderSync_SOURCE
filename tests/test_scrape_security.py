from datetime import timedelta
import threading
import time

import pytest

from ingestion.models import ScrapeRequest
from ingestion.collectors.base import SourceBlockedError, SourceUnavailableError
from ingestion.collectors.playwright_collector import _looks_like_challenge, validate_request_url
from ingestion.policies.pacing import source_lock
from ingestion.policies.retry import retry_after_seconds, should_retry_status


def req(url: str, allowed=("www.wingo.com",)):
    return ScrapeRequest(
        source="wingo",
        kind="flights",
        url=url,
        ready_selector="body",
        allowed_hosts=tuple(allowed),
    )


def test_validate_request_url_accepts_only_allowlisted_public_http_https():
    validate_request_url(req("https://www.wingo.com/es/vuelos"), {"www.wingo.com"})
    validate_request_url(req("http://www.wingo.com/es/vuelos"), {"www.wingo.com"})

    for bad in (
        "file:///etc/passwd",
        "ftp://www.wingo.com/file",
        "http://localhost/admin",
        "http://127.0.0.1/admin",
        "http://10.0.0.1/private",
        "https://example.org/not-allowed",
    ):
        with pytest.raises(SourceBlockedError):
            validate_request_url(req(bad), {"www.wingo.com"})


def test_retry_after_parses_seconds_and_http_date():
    assert retry_after_seconds({"Retry-After": "12"}) == 12
    assert retry_after_seconds({}) is None
    assert retry_after_seconds({"Retry-After": "not-a-date"}) is None


def test_status_retry_policy_never_retries_persistent_blocks():
    assert should_retry_status(500) is True
    assert should_retry_status(502) is True
    assert should_retry_status(429) is True
    assert should_retry_status(403) is False
    assert should_retry_status(401) is False


def test_source_lock_serializes_same_source(tmp_path):
    entered = []
    first_inside = threading.Event()
    release_first = threading.Event()

    def first():
        with source_lock("wingo", tmp_path):
            entered.append("first")
            first_inside.set()
            release_first.wait(timeout=2)

    def second():
        first_inside.wait(timeout=2)
        with source_lock("wingo", tmp_path):
            entered.append("second")

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start(); t2.start()
    first_inside.wait(timeout=2)
    time.sleep(0.05)
    assert entered == ["first"]
    release_first.set()
    t1.join(timeout=2); t2.join(timeout=2)
    assert entered == ["first", "second"]


def test_collector_rejects_redirect_to_non_allowlisted_host(tmp_path, monkeypatch):
    import contextlib
    import sys
    import types
    import ingestion.collectors.playwright_collector as collector

    class FakeResponse:
        status = 200
        headers = {}

    class FakeLocator:
        @property
        def first(self):
            return self
        def wait_for(self, **kwargs):
            return None

    class FakePage:
        url = "https://evil.example/redirected"
        def goto(self, *args, **kwargs):
            return FakeResponse()
        def locator(self, selector):
            return FakeLocator()
        def content(self):
            return "<html><body>real content</body></html>"

    class FakeContext:
        def new_page(self): return FakePage()
        def close(self): return None

    class FakeBrowser:
        def new_context(self, **kwargs): return FakeContext()
        def close(self): return None

    class FakeChromium:
        def launch(self, **kwargs): return FakeBrowser()

    class FakePW:
        chromium = FakeChromium()

    @contextlib.contextmanager
    def fake_sync_playwright():
        yield FakePW()

    fake_module = types.SimpleNamespace(TimeoutError=TimeoutError, sync_playwright=fake_sync_playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_module)
    monkeypatch.setattr(collector, "robots_allowed", lambda url: True)
    monkeypatch.setattr(collector, "_validate_resolved_host", lambda url: None)
    monkeypatch.setattr(collector, "pacing_delay", lambda *args: 0)

    with pytest.raises(SourceBlockedError, match="allowlisted"):
        collector.collect_html(req("https://www.wingo.com/es/vuelos"), tmp_path, timeout_seconds=1)


def test_challenge_detector_ignores_embedded_captcha_scripts_on_real_content():
    html = """<html><head><script src='https://www.google.com/recaptcha/api.js'></script></head>
    <body><h1>Carros de National en Medellín, Colombia</h1>
    <p>Precio por día por 30 días:</p><strong>USD $63,06 día</strong></body></html>"""
    assert _looks_like_challenge(html) is False


def test_challenge_detector_blocks_actual_human_verification_pages():
    html = "<html><title>Just a moment...</title><body>Verify you are human to continue</body></html>"
    assert _looks_like_challenge(html) is True
