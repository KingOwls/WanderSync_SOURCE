from __future__ import annotations

import re
import unicodedata
from bs4 import BeautifulSoup, Tag

from ingestion.models import SnapshotMetadata

PRICE_RE = re.compile(r"([\d][\d.,]*)\s*COP", re.I)


def _clean_hotel_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+en\s+Medell[ií]n\s*$", "", value, flags=re.I)
    return value.strip()


def _city_from_page(text: str) -> str | None:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    for city in ("Medellin", "Bogota", "Cali", "Cartagena", "Santa Marta"):
        if city.lower() in folded:
            return city.replace("Medellin", "Medellín").replace("Bogota", "Bogotá")
    return None


def parse_hotels(html: str, metadata: SnapshotMetadata) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    page_title = " ".join(h1.stripped_strings) if h1 else ""
    hotel_name = _clean_hotel_name(page_title)
    city = _city_from_page(page_title or " ".join(soup.stripped_strings))
    rows: list[dict] = []

    for marker in soup.find_all(string=lambda s: bool(s and s.strip().lower() == "desde")):
        tag = marker.parent if isinstance(marker.parent, Tag) else None
        if tag is None:
            continue
        price_parts: list[str] = []
        for node in tag.next_elements:
            if node is tag:
                continue
            if isinstance(node, Tag) and node.name in {"h2", "h3", "h4"}:
                break
            if isinstance(node, str):
                text = " ".join(node.split())
                if text:
                    price_parts.append(text)
            if len(price_parts) >= 12:
                break
        price_match = PRICE_RE.search(" ".join(price_parts))
        if not price_match:
            continue
        price_text = f"{price_match.group(1)} COP"
        heading = tag.find_previous(["h2", "h3", "h4"])
        if not heading:
            continue
        room_type = " ".join(heading.stripped_strings).strip()
        if not room_type or room_type.lower().startswith("habitaciones"):
            continue
        rows.append(
            {
                "name": hotel_name or None,
                "room_type": room_type,
                "city": city,
                "price_text": price_text,
                "rating": None,
            }
        )
    return rows
