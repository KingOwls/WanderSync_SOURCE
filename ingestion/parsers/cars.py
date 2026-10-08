from __future__ import annotations

import re
import unicodedata
from bs4 import BeautifulSoup, Tag

from ingestion.models import SnapshotMetadata

PRICE_RE = re.compile(r"(?:COP\s*)?\$\s*([\d][\d.,]*)", re.I)


def _city(text: str) -> str | None:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    if "santa marta" in folded:
        return "Santa Marta"
    if "medellin" in folded:
        return "Medellín"
    if "bogota" in folded:
        return "Bogotá"
    if "cali" in folded:
        return "Cali"
    if "cartagena" in folded:
        return "Cartagena"
    return None


def _provider_from_title(title: str) -> str | None:
    m = re.match(
        r"\s*(?:Carros\s+de\s+)?(.+?)\s+en\s+(Medell[ií]n|Bogot[aá]|Cali|Cartagena|Santa Marta)\b",
        title,
        re.I,
    )
    return m.group(1).strip() if m else None


def parse_cars(html: str, metadata: SnapshotMetadata) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = " ".join(h1.stripped_strings) if h1 else ""
    page_provider = _provider_from_title(title)
    city = _city(title or " ".join(soup.stripped_strings))
    headings = soup.find_all("h3")
    rows: list[dict] = []

    for heading in headings:
        category = " ".join(heading.stripped_strings).strip()
        if not category:
            continue
        strings: list[str] = []
        image_alts: list[str] = []
        for node in heading.next_elements:
            if node is heading:
                continue
            if isinstance(node, Tag) and node.name == "h3":
                break
            if isinstance(node, Tag) and node.name == "img":
                alt = (node.get("alt") or "").strip()
                if alt:
                    image_alts.append(alt)
            elif isinstance(node, str):
                txt = " ".join(node.split())
                if txt:
                    strings.append(txt)
        block_text = " ".join(strings)
        if "precio por día" not in block_text.lower() and "precio por dia" not in block_text.lower():
            continue
        price_m = PRICE_RE.search(block_text)
        if not price_m:
            continue
        candidates = [a for a in image_alts if len(a) > 2 and not a.lower().startswith(("logo", "icon", "estrella"))]
        model = candidates[0] if candidates else None
        provider = candidates[1] if len(candidates) > 1 else page_provider
        if page_provider:
            provider = page_provider
        rows.append(
            {
                "provider": provider,
                "model": model,
                "city": city,
                "category": category,
                "price_text": f"COP ${price_m.group(1)}",
            }
        )
    return rows
