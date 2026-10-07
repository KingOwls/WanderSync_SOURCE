from __future__ import annotations

from datetime import datetime
import re
import unicodedata
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ingestion.models import SnapshotMetadata

_CITY_CODES = {
    "bogota": "BOG",
    "medellin": "MDE",
    "cali": "CLO",
    "cartagena": "CTG",
    "santa-marta": "SMR",
}
_DATE_RE = re.compile(r"\b(\d{2}/\d{2}/(?:\d{2}|\d{4}))\b")
_PRICE_RE = re.compile(r"\bCOP\s*\$?\s*([0-9][0-9.,]*)\b", re.I)


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()


def _iso_date(raw: str) -> str | None:
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _route_from_url(url: str) -> tuple[str, str] | None:
    slug = urlparse(url).path.lower().rstrip("/").split("/")[-1]
    marker = "vuelos-desde-"
    if marker not in slug or "-a-" not in slug:
        return None
    payload = slug.split(marker, 1)[1]
    origin_slug, destination_slug = payload.split("-a-", 1)
    origin = _CITY_CODES.get(origin_slug)
    destination = _CITY_CODES.get(destination_slug)
    return (origin, destination) if origin and destination else None


def _route_from_heading(soup: BeautifulSoup) -> tuple[str, str] | None:
    text = _fold(" ".join((soup.find("h1") or soup).stripped_strings))
    names = {
        "bogota": "BOG",
        "medellin": "MDE",
        "cali": "CLO",
        "cartagena": "CTG",
        "santa marta": "SMR",
    }
    match = re.search(r"vuelos\s+a\s+(.+?)\s+desde\s+(.+?)(?:\s{2,}|$)", text)
    if match:
        destination_name, origin_name = (part.strip() for part in match.groups())
        if origin_name in names and destination_name in names:
            return names[origin_name], names[destination_name]
    # Headings often have no separator at the end; match known city names explicitly.
    for destination_name, destination in names.items():
        for origin_name, origin in names.items():
            if f"vuelos a {destination_name} desde {origin_name}" in text:
                return origin, destination
    return None


def parse_latam_flights(html: str, metadata: SnapshotMetadata) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    route = _route_from_url(metadata.source_url) or _route_from_heading(soup)
    if not route:
        return []
    origin, destination = route
    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()
    candidates = soup.find_all(["article", "section", "li", "div"])
    if not candidates:
        candidates = [soup]
    for node in candidates:
        text = " ".join(node.stripped_strings)
        folded = _fold(text)
        if "solo ida" not in folded:
            continue
        date_match = _DATE_RE.search(text)
        price_match = _PRICE_RE.search(text)
        if not date_match or not price_match:
            continue
        travel_date = _iso_date(date_match.group(1))
        if not travel_date:
            continue
        price_text = f"COP {price_match.group(1)}"
        key = (travel_date, price_text)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "airline": "LATAM",
            "origin": origin,
            "destination": destination,
            "trip_type": "Solo ida",
            "travel_date": travel_date,
            "price_text": price_text,
            "departure_at": None,
            "arrival_at": None,
        })
    rows.sort(key=lambda row: (row["travel_date"], row["price_text"]))
    return rows
