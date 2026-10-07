from pathlib import Path

import socket


def test_public_dns_readiness_uses_enabled_sources_not_hardcoded_wingo(monkeypatch):
    import ingestion.runner as runner

    class Adapter:
        allowed_hosts = {"clicair.co"}

    monkeypatch.setattr(runner, "get_enabled_adapters", lambda: [Adapter()], raising=False)
    calls = []

    def fake_getaddrinfo(host, port):
        calls.append(host)
        if "wingo" in host:
            raise AssertionError("Wingo must not be hardcoded")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port))]

    monkeypatch.setattr(runner.socket, "getaddrinfo", fake_getaddrinfo)
    assert runner._internet_dns_ready() is True
    assert calls == ["clicair.co"]


def test_env_example_declares_four_active_flight_sources_and_coverage_limits():
    text = Path(".env.example").read_text()
    assert "SCRAPE_ENABLED_SOURCES=clicair,satena,jetsmart,wingo,ghl_porton_medellin,alkilautos_national_medellin" in text
    assert "TARGET_OFFERS_PER_DIRECTION=10" in text
    assert "MAX_ROUTE_CONCURRENCY_PER_SOURCE=2" in text
    assert "SCRAPE_ENABLED_SOURCES=clicair,satena,latam" not in text
