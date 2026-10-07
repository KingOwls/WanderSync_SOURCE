from __future__ import annotations

from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import httpx

from ingestion.collectors.base import SourceBlockedError, SourceUnavailableError

USER_AGENT = "WanderSync-AcademicBot/1.0 (educational low-frequency scraper)"


def robots_allowed(url: str, *, timeout: float = 10.0) -> bool:
    parsed = urlparse(url)
    robots_url = urljoin(f"{parsed.scheme}://{parsed.netloc}", "/robots.txt")
    try:
        response = httpx.get(robots_url, timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise SourceUnavailableError(f"robots.txt unavailable for {parsed.hostname}: {exc}") from exc
    if response.status_code == 404:
        return True
    if response.status_code >= 500:
        raise SourceUnavailableError(f"robots.txt returned HTTP {response.status_code}")
    if response.status_code >= 400:
        return False
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)
