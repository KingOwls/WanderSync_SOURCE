from __future__ import annotations

import os

from ingestion.sources.cars_public import NationalMedellinCarsAdapter
from ingestion.sources.flights_clic import ClicAirFlightsAdapter
from ingestion.sources.flights_satena import SatenaFlightsAdapter
from ingestion.sources.flights_jetsmart import JetSmartFlightsAdapter
from ingestion.sources.flights_latam import LatamFlightsAdapter
from ingestion.sources.flights_wingo import WingoFlightsAdapter
from ingestion.sources.hotels_public import GHLPortonMedellinAdapter

_ADAPTERS = {
    "clicair": ClicAirFlightsAdapter(),
    "satena": SatenaFlightsAdapter(),
    "latam": LatamFlightsAdapter(),
    "jetsmart": JetSmartFlightsAdapter(),
    "wingo": WingoFlightsAdapter(),
    "ghl_porton_medellin": GHLPortonMedellinAdapter(),
    "alkilautos_national_medellin": NationalMedellinCarsAdapter(),
}

_DEFAULT_ENABLED = (
    "clicair",
    "satena",
    "jetsmart",
    "wingo",
    "ghl_porton_medellin",
    "alkilautos_national_medellin",
)


def get_enabled_adapters():
    configured = os.getenv("SCRAPE_ENABLED_SOURCES", ",".join(_DEFAULT_ENABLED)).split(",")
    names = [name.strip() for name in configured if name.strip()]
    return [_ADAPTERS[name] for name in names if name in _ADAPTERS]


def get_adapter(name: str):
    if name not in _ADAPTERS:
        raise KeyError(f"Unknown scraping source adapter: {name}")
    return _ADAPTERS[name]
