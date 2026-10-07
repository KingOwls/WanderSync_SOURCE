from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import re
import unicodedata

CITY_CODES = {
    "BOGOTA": "BOG",
    "BOGOTÁ": "BOG",
    "MEDELLIN": "MDE",
    "MEDELLÍN": "MDE",
    "CALI": "CLO",
    "CARTAGENA": "CTG",
    "BUCARAMANGA": "BGA",
    "BARRANQUILLA": "BAQ",
    "SANTA MARTA": "SMR",
}


def clean(value):
    return " ".join(value.split()).strip() if isinstance(value, str) else value


def city_code(value: str | None) -> str | None:
    if not value:
        return None
    value = clean(value).upper()
    if len(value) == 3 and value.isalpha():
        return value
    return CITY_CODES.get(value)


def parse_cop_price(value: str | None) -> int | None:
    if not value:
        return None
    upper = value.upper()
    if "COP" not in upper:
        return None
    numeric = re.sub(r"[^0-9,\.]", "", upper)
    if not numeric:
        return None
    # COP public pages use dot/comma as thousands separators in our enabled sources.
    digits = re.sub(r"[^0-9]", "", numeric)
    return int(digits) if digits else None


def iso_date(value: str | None) -> str | None:
    if not value:
        return None
    value = clean(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass

    match = re.fullmatch(r"([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3})\s+(\d{1,2}),\s*(\d{4})", value)
    if match:
        month_raw, day, year = match.groups()
        month_key = unicodedata.normalize("NFKD", month_raw).encode("ascii", "ignore").decode().upper()
        months = {
            "ENE": 1, "JAN": 1, "FEB": 2, "MAR": 3, "ABR": 4, "APR": 4,
            "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "AUG": 8, "SEP": 9,
            "OCT": 10, "NOV": 11, "DIC": 12, "DEC": 12,
        }
        month = months.get(month_key)
        if month:
            try:
                return datetime(int(year), month, int(day)).date().isoformat()
            except ValueError:
                return None
    text_match = re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3}\s+(\d{1,2})\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3})\s+(\d{4})", value)
    if text_match:
        day, month_raw, year = text_match.groups()
        month_key = unicodedata.normalize("NFKD", month_raw).encode("ascii", "ignore").decode().upper()
        months = {
            "ENE": 1, "JAN": 1, "FEB": 2, "MAR": 3, "ABR": 4, "APR": 4,
            "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "AUG": 8, "SEP": 9,
            "OCT": 10, "NOV": 11, "DIC": 12, "DEC": 12,
        }
        month = months.get(month_key)
        if month:
            try:
                return datetime(int(year), month, int(day)).date().isoformat()
            except ValueError:
                return None
    return None


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(clean(str(p)).lower() for p in parts if p is not None)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"
