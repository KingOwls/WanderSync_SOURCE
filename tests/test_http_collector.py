from ingestion.models import ScrapeRequest


def request(url="https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin"):
    return ScrapeRequest(
        source="clicair",
        kind="flights",
        url=url,
        ready_selector="table",
        allowed_hosts=("clicair.co", "www.clicair.co"),
        transport="http",
    )


def test_http_collector_accepts_public_table_even_when_script_contains_block_words(tmp_path, monkeypatch):
    import ingestion.collectors.http_collector as collector

    html = """<html><head><script>const msg='access denied';</script></head><body>
    <table><tr><th>Desde</th><th>Hasta</th><th>Tipo de vuelo</th><th>Fecha</th><th>Precio</th></tr>
    <tr><td>Bogotá (BOG)</td><td>Medellín (EOH)</td><td>Solo ida</td><td>Oct 18, 2026</td><td>COP 196,250</td></tr>
    </table></body></html>"""

    class Response:
        status_code = 200
        text = html
        headers = {}
        url = "https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin"

    monkeypatch.setattr(collector, "robots_allowed", lambda url: True)
    monkeypatch.setattr(collector, "_validate_resolved_host", lambda url: None)
    monkeypatch.setattr(collector, "pacing_delay", lambda *args: 0)
    monkeypatch.setattr(collector.httpx, "get", lambda *args, **kwargs: Response())

    result = collector.collect_http(request(), tmp_path, timeout_seconds=1)
    assert result.snapshot.html_path.exists()
    assert "Bogotá (BOG)" in result.snapshot.html_path.read_text(encoding="utf-8")
    assert result.snapshot.metadata.http_status == 200


def test_http_collector_rejects_redirect_to_non_allowlisted_host(tmp_path, monkeypatch):
    import pytest
    import ingestion.collectors.http_collector as collector
    from ingestion.collectors.base import SourceBlockedError

    class Response:
        status_code = 200
        text = "<html><table></table></html>"
        headers = {}
        url = "https://evil.example/redirected"

    monkeypatch.setattr(collector, "robots_allowed", lambda url: True)
    monkeypatch.setattr(collector, "_validate_resolved_host", lambda url: None)
    monkeypatch.setattr(collector, "pacing_delay", lambda *args: 0)
    monkeypatch.setattr(collector.httpx, "get", lambda *args, **kwargs: Response())

    with pytest.raises(SourceBlockedError, match="allowlisted"):
        collector.collect_http(request(), tmp_path, timeout_seconds=1)


def test_http_collector_robots_denial_does_not_call_network_or_sleep(tmp_path, monkeypatch):
    import pytest
    import ingestion.collectors.http_collector as collector
    from ingestion.collectors.base import SourceBlockedError

    calls = {"get": 0, "sleep": 0}
    monkeypatch.setattr(collector, "_validate_resolved_host", lambda url: None)
    monkeypatch.setattr(collector, "robots_allowed", lambda url: False)
    monkeypatch.setattr(collector.httpx, "get", lambda *a, **k: calls.__setitem__("get", calls["get"] + 1))
    monkeypatch.setattr(collector.time, "sleep", lambda *_: calls.__setitem__("sleep", calls["sleep"] + 1))
    with pytest.raises(SourceBlockedError, match="robots.txt"):
        collector.collect_http(request(), tmp_path, timeout_seconds=1)
    assert calls == {"get": 0, "sleep": 0}
