from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedLocation:
    city_code: str
    flight_airports: tuple[str, ...]
    service_city: str


_LOCATIONS = {
    "BOG": ResolvedLocation("BOG", ("BOG",), "BOG"),
    "MDE": ResolvedLocation("MDE", ("MDE", "EOH"), "MDE"),
    "CLO": ResolvedLocation("CLO", ("CLO",), "CLO"),
    "CTG": ResolvedLocation("CTG", ("CTG",), "CTG"),
    "SMR": ResolvedLocation("SMR", ("SMR",), "SMR"),
}

_AIRPORT_TO_CITY = {
    airport: location.city_code
    for location in _LOCATIONS.values()
    for airport in location.flight_airports
}


def city_code_for_airport(code: str) -> str | None:
    return _AIRPORT_TO_CITY.get(code.strip().upper())


def resolve_location(code: str) -> ResolvedLocation:
    normalized = code.strip().upper()
    return _LOCATIONS.get(normalized, ResolvedLocation(normalized, (normalized,), normalized))

from datetime import date


@dataclass(frozen=True)
class AvailabilityCombination:
    departure_date: str
    return_date: str
    nights: int
    lowest_outbound_price: float
    lowest_return_price: float
    lowest_flight_total: float


@dataclass(frozen=True)
class AvailabilityResult:
    outbound_dates: tuple[str, ...]
    return_dates: tuple[str, ...]
    outbound_offer_count: int
    return_offer_count: int
    combinations: tuple[AvailabilityCombination, ...]


def _valid_price_rows(rows: list[dict]) -> list[dict]:
    return [
        row for row in rows
        if row.get("travel_date") and row.get("price") is not None and row.get("currency", "COP") == "COP"
    ]


def build_availability(
    outbound_rows: list[dict],
    return_rows: list[dict],
    outbound_limit: int = 8,
    return_limit: int = 8,
    recommendation_limit: int = 12,
) -> AvailabilityResult:
    outbound_limit = min(max(int(outbound_limit), 1), 366)
    return_limit = min(max(int(return_limit), 1), 366)
    recommendation_limit = min(max(int(recommendation_limit), 1), 12)
    outbound_valid = _valid_price_rows(outbound_rows)
    return_valid = _valid_price_rows(return_rows)
    if not outbound_valid:
        return AvailabilityResult((), (), 0, len(return_valid), ())

    outbound_dates = tuple(sorted({str(row["travel_date"]) for row in outbound_valid})[:outbound_limit])
    return_dates = tuple(sorted({str(row["travel_date"]) for row in return_valid})[:return_limit])

    outbound_min = {
        day: min(float(row["price"]) for row in outbound_valid if str(row["travel_date"]) == day)
        for day in outbound_dates
    }
    return_min = {
        day: min(float(row["price"]) for row in return_valid if str(row["travel_date"]) == day)
        for day in return_dates
    }
    combinations: list[AvailabilityCombination] = []
    for outbound_day in outbound_dates:
        departure = date.fromisoformat(outbound_day)
        for return_day in return_dates:
            returning = date.fromisoformat(return_day)
            nights = (returning - departure).days
            if not 1 <= nights <= 14:
                continue
            outbound_price = outbound_min[outbound_day]
            return_price = return_min[return_day]
            combinations.append(AvailabilityCombination(
                departure_date=outbound_day,
                return_date=return_day,
                nights=nights,
                lowest_outbound_price=outbound_price,
                lowest_return_price=return_price,
                lowest_flight_total=round(outbound_price + return_price, 2),
            ))
    combinations.sort(key=lambda item: (item.lowest_flight_total, item.departure_date, item.return_date))
    return AvailabilityResult(
        outbound_dates=outbound_dates,
        return_dates=return_dates,
        outbound_offer_count=len(outbound_valid),
        return_offer_count=len(return_valid),
        combinations=tuple(combinations[:recommendation_limit]),
    )

@dataclass(frozen=True)
class RoundTripPackageCandidate:
    outbound: dict
    return_flight: dict
    hotel: dict
    car: dict
    nights: int
    flight_total: float
    total: float


def build_roundtrip_packages(
    outbound_rows: list[dict],
    return_rows: list[dict],
    hotel_rows: list[dict],
    car_rows: list[dict],
    nights: int,
    limit: int = 12,
) -> list[RoundTripPackageCandidate]:
    if not 1 <= int(nights) <= 14:
        return []
    outbound = [r for r in outbound_rows if r.get("price") is not None and r.get("currency", "COP") == "COP"]
    returning = [r for r in return_rows if r.get("price") is not None and r.get("currency", "COP") == "COP"]
    hotels = [r for r in hotel_rows if r.get("nightly_price") is not None and r.get("currency", "COP") == "COP"]
    cars = [r for r in car_rows if r.get("daily_price") is not None and r.get("currency", "COP") == "COP"]
    if not outbound or not returning or not hotels or not cars:
        return []
    import heapq
    # Only the cheapest `limit` per component can contribute to top `limit` packages.
    keep = min(max(int(limit), 1), 12)
    outbound = sorted(outbound, key=lambda r: float(r["price"]))[:keep]
    returning = sorted(returning, key=lambda r: float(r["price"]))[:keep]
    hotels = sorted(hotels, key=lambda r: float(r["nightly_price"]))[:keep]
    cars = sorted(cars, key=lambda r: float(r["daily_price"]))[:keep]
    candidates: list[RoundTripPackageCandidate] = []
    for out in outbound:
        for back in returning:
            for hotel in hotels:
                for car in cars:
                    flight_total = round(float(out["price"]) + float(back["price"]), 2)
                    total = round(
                        flight_total
                        + float(hotel["nightly_price"]) * nights
                        + float(car["daily_price"]) * nights,
                        2,
                    )
                    candidates.append(RoundTripPackageCandidate(
                        outbound=out,
                        return_flight=back,
                        hotel=hotel,
                        car=car,
                        nights=nights,
                        flight_total=flight_total,
                        total=total,
                    ))
    candidates.sort(key=lambda item: item.total)
    return candidates[:min(max(int(limit), 1), 12)]


TOURIST_CITY_NAMES = {
    "BOG": "Bogotá",
    "MDE": "Medellín",
    "CLO": "Cali",
    "CTG": "Cartagena",
    "SMR": "Santa Marta",
}
_TOURIST_CITY_ORDER = tuple(TOURIST_CITY_NAMES)


@dataclass(frozen=True)
class NetworkRouteSummary:
    origin: str
    destination: str
    offer_count: int
    sources: tuple[str, ...]
    outbound_available: bool
    round_trip_available: bool
    package_available: bool
    first_date: str | None
    last_date: str | None
    lowest_price: float | None
    coverage_status: str
    visible_offer_count: int
    raw_offer_count: int
    sources_checked: int
    sources_available: int


@dataclass(frozen=True)
class NetworkResult:
    cities: tuple[str, ...]
    routes: tuple[NetworkRouteSummary, ...]


def build_travel_network(
    route_rows: list[dict],
    service_flags: dict[str, tuple[bool, bool]],
    source_health: dict[str, str] | None = None,
    expected_sources: tuple[str, ...] = ("clicair", "satena", "jetsmart", "wingo"),
) -> NetworkResult:
    aggregated: dict[tuple[str, str], dict] = {}
    for row in route_rows:
        origin = city_code_for_airport(str(row.get("origin", "")))
        destination = city_code_for_airport(str(row.get("destination", "")))
        if not origin or not destination or origin == destination:
            continue
        key = (origin, destination)
        item = aggregated.setdefault(key, {"offer_count": 0, "sources": set(), "first_date": None, "last_date": None, "lowest_price": None})
        item["offer_count"] += int(row.get("offer_count") or 0)
        sources = row.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        item["sources"].update(str(source) for source in sources if source)
        first_date = str(row["first_date"]) if row.get("first_date") else None
        last_date = str(row["last_date"]) if row.get("last_date") else None
        price = float(row["lowest_price"]) if row.get("lowest_price") is not None else None
        if first_date and (item["first_date"] is None or first_date < item["first_date"]): item["first_date"] = first_date
        if last_date and (item["last_date"] is None or last_date > item["last_date"]): item["last_date"] = last_date
        if price is not None and (item["lowest_price"] is None or price < item["lowest_price"]): item["lowest_price"] = price

    health = source_health or {source: "SUCCESS" for source in expected_sources}
    healthy_statuses = {"SUCCESS", "CACHED", "STALE_FALLBACK"}
    checked = sum(1 for source in expected_sources if health.get(source) not in (None, "NOT_RUN"))
    available_sources = sum(1 for source in expected_sources if health.get(source) in healthy_statuses)
    route_summaries: list[NetworkRouteSummary] = []
    for origin in _TOURIST_CITY_ORDER:
        for destination in _TOURIST_CITY_ORDER:
            if origin == destination:
                continue
            item = aggregated.get((origin, destination), {"offer_count":0,"sources":set(),"first_date":None,"last_date":None,"lowest_price":None})
            raw = int(item["offer_count"])
            opposite = int(aggregated.get((destination, origin), {}).get("offer_count", 0))
            round_trip = raw > 0 and opposite > 0
            has_hotel, has_car = service_flags.get(destination, (False, False))
            if raw >= 10:
                coverage_status = "AVAILABLE"
            elif raw > 0:
                coverage_status = "PARTIAL"
            elif expected_sources and available_sources == len(expected_sources):
                coverage_status = "NO_OFFERS"
            else:
                coverage_status = "SOURCE_UNAVAILABLE"
            route_summaries.append(NetworkRouteSummary(
                origin=origin, destination=destination, offer_count=min(raw, 10), sources=tuple(sorted(item["sources"])),
                outbound_available=raw > 0, round_trip_available=round_trip, package_available=bool(round_trip and has_hotel and has_car),
                first_date=item["first_date"], last_date=item["last_date"], lowest_price=item["lowest_price"],
                coverage_status=coverage_status, visible_offer_count=min(raw,10), raw_offer_count=raw,
                sources_checked=checked, sources_available=available_sources,
            ))
    return NetworkResult(cities=_TOURIST_CITY_ORDER, routes=tuple(route_summaries))

