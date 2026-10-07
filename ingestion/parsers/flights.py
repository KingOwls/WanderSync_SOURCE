from __future__ import annotations

import re
import unicodedata
from bs4 import BeautifulSoup

from ingestion.models import SnapshotMetadata

SOURCE_AIRLINES = {
    "clicair": "CLIC",
    "satena": "SATENA",
    "jetsmart": "JetSMART",
    "wingo": "Wingo",
}

ROUTE_RE = re.compile(
    r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]{2,50})\s*\(([A-Z]{3})\)\s*a\s*"
    r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]{2,50})\s*\(([A-Z]{3})\)\s*"
    r"(\d{2}/\d{2}/\d{4}).{0,80}?Desde\s*(COP|USD)\s*([\d.,]+)",
    re.I | re.S,
)

AIRPORT_RE = re.compile(r"(.+?)\s*\(([A-Z]{3})\)\s*$", re.I)
HEADER_ALIASES = {
    "origin": {"desde"},
    "destination": {"hasta", "a", "hacia"},
    "trip_type": {"tipo de vuelo", "tipo de tarifa"},
    "travel_date": {"fecha", "fechas"},
    "price": {"precio"},
}


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower().strip()


def is_one_way_trip_type(value: str | None) -> bool:
    return _fold(value or "").startswith("solo ida")


def _airport(value: str) -> tuple[str, str] | None:
    match = AIRPORT_RE.match(" ".join(value.split()))
    if not match:
        return None
    return match.group(1).strip(), match.group(2).upper()


def _resolve_indexes(headers: list[str]) -> dict[str, int] | None:
    indexes: dict[str, int] = {}
    required = {"origin", "destination", "travel_date", "price"}
    for field, aliases in HEADER_ALIASES.items():
        for idx, header in enumerate(headers):
            if header in aliases:
                indexes[field] = idx
                break
    return indexes if required.issubset(indexes) else None


def _concrete_price(value: str) -> bool:
    return "COP" in value.upper() and bool(re.search(r"\d", value))


def _extract_offer_tables(soup: BeautifulSoup, airline: str) -> list[dict]:
    rows: list[dict] = []
    for table in soup.find_all("table"):
        header_cells = table.find_all("th")
        headers = [_fold(" ".join(cell.stripped_strings)) for cell in header_cells]
        indexes = _resolve_indexes(headers)
        if not indexes:
            continue
        max_index = max(indexes.values())
        for tr in table.find_all("tr"):
            cells = [" ".join(td.stripped_strings).strip() for td in tr.find_all("td")]
            if not cells or max_index >= len(cells):
                continue
            origin = _airport(cells[indexes["origin"]])
            destination = _airport(cells[indexes["destination"]])
            travel_date = cells[indexes["travel_date"]].strip()
            price_text = cells[indexes["price"]].strip()
            if not origin or not destination or not travel_date or not _concrete_price(price_text):
                continue
            origin_name, origin_code = origin
            destination_name, destination_code = destination
            trip_type = cells[indexes["trip_type"]] if "trip_type" in indexes and indexes["trip_type"] < len(cells) else None
            rows.append(
                {
                    "airline": airline,
                    "origin_name": origin_name,
                    "origin": origin_code,
                    "destination_name": destination_name,
                    "destination": destination_code,
                    "trip_type": trip_type,
                    "travel_date": travel_date,
                    "price_text": price_text,
                    "departure_at": None,
                    "arrival_at": None,
                }
            )
    return rows


def _extract_legacy_wingo(text: str) -> list[dict]:
    rows: list[dict] = []
    for match in ROUTE_RE.finditer(text):
        origin_name, origin, destination_name, destination, travel_date, currency, amount = match.groups()
        rows.append(
            {
                "airline": "Wingo",
                "origin_name": " ".join(origin_name.split()),
                "origin": origin.upper(),
                "destination_name": " ".join(destination_name.split()),
                "destination": destination.upper(),
                "trip_type": None,
                "travel_date": travel_date,
                "price_text": f"{currency.upper()}{amount}",
                "departure_at": None,
                "arrival_at": None,
            }
        )
    return rows


def parse_flights(html: str, metadata: SnapshotMetadata) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    airline = SOURCE_AIRLINES.get(metadata.source, metadata.source.upper())
    rows = _extract_offer_tables(soup, airline)
    if not rows:
        for tr in soup.find_all("tr"):
            rows.extend(_extract_legacy_wingo(" ".join(tr.stripped_strings)))
        if not rows:
            rows = _extract_legacy_wingo(" ".join(soup.stripped_strings))

    seen = set()
    unique = []
    for row in rows:
        key = (
            metadata.source,
            row["airline"], row["origin"], row["destination"], row["travel_date"],
            row["price_text"], row.get("trip_type"),
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique
