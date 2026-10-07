import asyncio
import json
from datetime import date
from typing import Optional

import httpx
import redis.asyncio as redis_async
import strawberry
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from graphql import GraphQLError
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from common.config import (
    CAR_SERVICE_URL,
    COOKIE_NAME,
    COOKIE_SECURE,
    FLIGHT_SERVICE_URL,
    FRONTEND_ORIGIN,
    HOTEL_SERVICE_URL,
    ORDER_SERVICE_URL,
    REDIS_URL,
)
from common.db import fetch_all, fetch_one, get_conn
from common.security import (
    enforce_rate_limit,
    hash_password,
    new_session_id,
    session_payload,
    verify_password,
)
from gateway.flight_connections import build_suggested_connections
from gateway.route_coverage import build_direction_coverage, select_direction_offers, supported_city_pairs
from gateway.source_health import ACTIVE_FLIGHT_SOURCES, build_source_health_summary
from gateway.travel_logic import (
    TOURIST_CITY_NAMES,
    build_availability,
    build_roundtrip_packages,
    build_travel_network,
    city_code_for_airport,
    resolve_location,
)

redis_client = redis_async.from_url(REDIS_URL, decode_responses=True)


@strawberry.type
class User:
    id: int
    email: str
    full_name: str


@strawberry.type
class Flight:
    id: str
    airline: str
    origin: str
    destination: str
    travel_date: str
    departure_at: Optional[str]
    arrival_at: Optional[str]
    price: float
    currency: str
    source: str
    source_url: str
    snapshot_id: str
    scraped_at: str


@strawberry.type
class Hotel:
    id: str
    name: str
    room_type: Optional[str]
    city: str
    nightly_price: float
    currency: str
    rating: Optional[float]
    source: str
    source_url: str
    snapshot_id: str
    scraped_at: str


@strawberry.type
class Car:
    id: str
    provider: str
    model: str
    city: str
    daily_price: float
    currency: str
    category: Optional[str]
    source: str
    source_url: str
    snapshot_id: str
    scraped_at: str


@strawberry.type
class DateCombination:
    departure_date: str
    return_date: str
    nights: int
    lowest_outbound_price: float
    lowest_return_price: float
    lowest_flight_total: float


@strawberry.type
class TravelAvailability:
    origin: str
    destination: str
    airport_codes: list[str]
    outbound_dates: list[str]
    return_dates: list[str]
    outbound_offer_count: int
    return_offer_count: int
    combinations: list[DateCombination]


@strawberry.type
class TravelCity:
    code: str
    name: str
    airports: list[str]


@strawberry.type
class TravelRoute:
    origin: str
    destination: str
    offer_count: int
    sources: list[str]
    outbound_available: bool
    round_trip_available: bool
    package_available: bool
    first_date: Optional[str]
    last_date: Optional[str]
    lowest_price: Optional[float]
    coverage_status: str
    visible_offer_count: int
    raw_offer_count: int
    sources_checked: int
    sources_available: int


@strawberry.type
class TravelNetwork:
    cities: list[TravelCity]
    routes: list[TravelRoute]


@strawberry.type
class FlightDateOption:
    travel_date: str
    direct_offer_count: int
    connection_candidate_count: int


@strawberry.type
class FlightAvailabilityResult:
    origin: str
    destination: str
    dates: list[FlightDateOption]


@strawberry.type
class SuggestedConnection:
    via: str
    stops: int
    total_price: float
    currency: str
    legs: list[Flight]
    warning: str


@strawberry.type
class FlightSearchResult:
    origin: str
    destination: str
    travel_date: str
    status: str
    available_count: int
    sources_checked: int
    sources_available: int
    direct_offers: list[Flight]
    connections: list[SuggestedConnection]


@strawberry.type
class SourceHealthItem:
    source: str
    status: str
    available: bool
    items_found: int
    finished_at: Optional[str]


@strawberry.type
class SourceHealthSummary:
    active_count: int
    total_count: int
    sources: list[SourceHealthItem]


@strawberry.type
class TravelPackage:
    id: str
    outbound_flight: Flight
    return_flight: Flight
    hotel: Hotel
    car: Car
    nights: int
    flight_total: float
    total: float


@strawberry.type
class Booking:
    id: str
    user_id: int
    flight_id: Optional[str]
    outbound_flight_id: str
    return_flight_id: Optional[str]
    hotel_id: str
    car_id: str
    total: float
    status: str
    payment_status: str
    failure_reason: Optional[str]
    created_at: str


@strawberry.type
class SagaEvent:
    id: int
    order_id: str
    step: str
    action: str
    status: str
    detail: Optional[str]
    created_at: str


@strawberry.type
class SessionInfo:
    authenticated: bool
    session_prefix: str
    created_at: Optional[str]
    rotated_at: Optional[str]
    user_email: Optional[str]


@strawberry.type
class SecurityStatus:
    password_hashing: str
    session_fixation_protection: str
    cookie_policy: str
    login_rate_limit: str
    checkout_rate_limit: str
    payment_rate_limit: str
    dependency_audit: str


@strawberry.type
class DatabaseStatus:
    connected: bool
    database: str
    db_user: str
    users: int
    flights: int
    hotels: int
    cars: int
    orders: int


def _client_ip(request: Request) -> str:
    # The Gateway is directly exposed in this Compose stack. Do not trust arbitrary
    # X-Forwarded-For values from clients, otherwise the login rate limit can be bypassed.
    return request.client.host if request.client else "unknown"


def _set_session_cookie(response: Response, sid: str):
    response.set_cookie(
        COOKIE_NAME,
        sid,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60 * 8,
        path="/",
    )


async def _read_session(request: Request):
    sid = request.cookies.get(COOKIE_NAME)
    if not sid:
        return None, None
    raw = await redis_client.get(f"session:{sid}")
    if not raw:
        return sid, None
    return sid, json.loads(raw)


async def _ensure_anonymous_session(request: Request, response: Response):
    sid, session = await _read_session(request)
    if session:
        return sid, session
    sid = new_session_id()
    raw = session_payload(authenticated=False)
    await redis_client.setex(f"session:{sid}", 60 * 60 * 8, raw)
    _set_session_cookie(response, sid)
    return sid, json.loads(raw)


async def _require_user(info: Info) -> dict:
    _, session = await _read_session(info.context["request"])
    if not session or not session.get("authenticated"):
        raise GraphQLError("Authentication required", extensions={"code": "UNAUTHENTICATED"})
    return session


def _nullable_str(value) -> Optional[str]:
    return None if value is None else str(value)


def _to_flight(row: dict) -> Flight:
    return Flight(
        id=row["id"], airline=row["airline"], origin=row["origin"], destination=row["destination"],
        travel_date=str(row["travel_date"]), departure_at=_nullable_str(row.get("departure_at")),
        arrival_at=_nullable_str(row.get("arrival_at")), price=float(row["price"]), currency=row.get("currency", "COP"),
        source=row["source"], source_url=row["source_url"], snapshot_id=row["snapshot_id"], scraped_at=str(row["scraped_at"]),
    )


def _to_hotel(row: dict) -> Hotel:
    return Hotel(
        id=row["id"], name=row["name"], room_type=row.get("room_type"), city=row["city"],
        nightly_price=float(row["nightly_price"]), currency=row.get("currency", "COP"),
        rating=float(row["rating"]) if row.get("rating") is not None else None,
        source=row["source"], source_url=row["source_url"], snapshot_id=row["snapshot_id"], scraped_at=str(row["scraped_at"]),
    )


def _to_car(row: dict) -> Car:
    return Car(
        id=row["id"], provider=row["provider"], model=row["model"], city=row["city"],
        daily_price=float(row["daily_price"]), currency=row.get("currency", "COP"), category=row.get("category"),
        source=row["source"], source_url=row["source_url"], snapshot_id=row["snapshot_id"], scraped_at=str(row["scraped_at"]),
    )


def _to_booking(row: dict) -> Booking:
    outbound_flight_id = row.get("outbound_flight_id") or row.get("flight_id")
    return Booking(
        id=str(row["id"]), user_id=int(row["user_id"]), flight_id=row.get("flight_id"),
        outbound_flight_id=outbound_flight_id, return_flight_id=row.get("return_flight_id"), hotel_id=row["hotel_id"],
        car_id=row["car_id"], total=float(row["total"]), status=row["status"], payment_status=row["payment_status"],
        failure_reason=row.get("failure_reason"), created_at=str(row["created_at"]),
    )


def _source_health_data() -> dict:
    rows = fetch_all(
        """SELECT DISTINCT ON (source) source,status,items_found,finished_at
           FROM scrape_runs WHERE source = ANY(%s)
           ORDER BY source,id DESC""",
        (list(ACTIVE_FLIGHT_SOURCES),),
    )
    return build_source_health_summary(rows)


def _health_map(summary: dict) -> dict[str, str]:
    return {item["source"]: item["status"] for item in summary["sources"]}


@strawberry.type
class Query:
    @strawberry.field
    async def session_info(self, info: Info) -> SessionInfo:
        sid, session = await _ensure_anonymous_session(info.context["request"], info.context["response"])
        return SessionInfo(
            authenticated=bool(session.get("authenticated")),
            session_prefix=f"{sid[:8]}…",
            created_at=session.get("created_at"),
            rotated_at=session.get("rotated_at"),
            user_email=session.get("email"),
        )

    @strawberry.field
    async def me(self, info: Info) -> Optional[User]:
        _, session = await _read_session(info.context["request"])
        if not session or not session.get("authenticated"):
            return None
        row = fetch_one("SELECT id,email,full_name FROM users WHERE id=%s", (session["user_id"],))
        return User(**row) if row else None

    @strawberry.field
    async def flight_offers(self, origin: str, destination: str, limit: int = 20, travel_date: Optional[str] = None) -> list[Flight]:
        origin_location = resolve_location(origin)
        destination_location = resolve_location(destination)
        async with httpx.AsyncClient(timeout=8.0) as client:
            params = {
                "origins": ",".join(origin_location.flight_airports),
                "destinations": ",".join(destination_location.flight_airports),
                "limit": min(max(limit, 1), 50),
            }
            if travel_date:
                params["travel_date"] = travel_date
            response = await client.get(f"{FLIGHT_SERVICE_URL}/flights", params=params)
            response.raise_for_status()
        return [_to_flight(row) for row in response.json() if row.get("price") is not None]

    @strawberry.field
    async def travel_network(self) -> TravelNetwork:
        health_summary = _source_health_data()
        health_map = _health_map(health_summary)
        async with httpx.AsyncClient(timeout=8.0) as client:
            route_response = await client.get(f"{FLIGHT_SERVICE_URL}/routes")
            route_response.raise_for_status()
            route_rows = route_response.json()

            async def service_flags(city: str) -> tuple[str, tuple[bool, bool]]:
                async def available(url: str, params: dict) -> bool:
                    try:
                        response = await client.get(url, params=params)
                        response.raise_for_status()
                        return bool(response.json())
                    except Exception:
                        return False
                hotel_ok, car_ok = await asyncio.gather(
                    available(f"{HOTEL_SERVICE_URL}/hotels", {"city": resolve_location(city).service_city, "limit": 1}),
                    available(f"{CAR_SERVICE_URL}/cars", {"city": resolve_location(city).service_city, "limit": 1}),
                )
                return city, (hotel_ok, car_ok)

            flag_pairs = await asyncio.gather(*(service_flags(code) for code in TOURIST_CITY_NAMES))

        network = build_travel_network(route_rows, dict(flag_pairs), health_map, ACTIVE_FLIGHT_SOURCES)
        return TravelNetwork(
            cities=[TravelCity(code=code, name=TOURIST_CITY_NAMES[code], airports=list(resolve_location(code).flight_airports)) for code in network.cities],
            routes=[TravelRoute(
                origin=route.origin, destination=route.destination, offer_count=route.offer_count, sources=list(route.sources),
                outbound_available=route.outbound_available, round_trip_available=route.round_trip_available, package_available=route.package_available,
                first_date=route.first_date, last_date=route.last_date, lowest_price=route.lowest_price,
                coverage_status=route.coverage_status, visible_offer_count=route.visible_offer_count, raw_offer_count=route.raw_offer_count,
                sources_checked=route.sources_checked, sources_available=route.sources_available,
            ) for route in network.routes],
        )

    @strawberry.field
    def source_health(self) -> SourceHealthSummary:
        summary = _source_health_data()
        return SourceHealthSummary(
            active_count=summary["active_count"], total_count=summary["total_count"],
            sources=[SourceHealthItem(**item) for item in summary["sources"]],
        )

    @strawberry.field
    async def flight_availability(self, origin: str, destination: str) -> FlightAvailabilityResult:
        origin_location = resolve_location(origin)
        destination_location = resolve_location(destination)
        if origin_location.city_code == destination_location.city_code:
            raise GraphQLError("Origin and destination must be different", extensions={"code": "BAD_USER_INPUT"})
        async with httpx.AsyncClient(timeout=8.0) as client:
            direct_r, outgoing_r, incoming_r = await asyncio.gather(
                client.get(f"{FLIGHT_SERVICE_URL}/flights", params={"origins": ",".join(origin_location.flight_airports), "destinations": ",".join(destination_location.flight_airports), "limit": 100}),
                client.get(f"{FLIGHT_SERVICE_URL}/flights", params={"origins": ",".join(origin_location.flight_airports), "limit": 100}),
                client.get(f"{FLIGHT_SERVICE_URL}/flights", params={"destinations": ",".join(destination_location.flight_airports), "limit": 100}),
            )
            for response in (direct_r, outgoing_r, incoming_r): response.raise_for_status()
        direct_rows, outgoing_rows, incoming_rows = direct_r.json(), outgoing_r.json(), incoming_r.json()
        dates = sorted({str(row.get("travel_date")) for row in direct_rows if row.get("travel_date")} | {str(row.get("travel_date")) for row in outgoing_rows if row.get("travel_date")} & {str(row.get("travel_date")) for row in incoming_rows if row.get("travel_date")})
        options: list[FlightDateOption] = []
        for day in dates:
            direct_count = len(select_direction_offers([r for r in direct_rows if str(r.get("travel_date")) == day], origin=origin_location.city_code, destination=destination_location.city_code, limit=10))
            connections = build_suggested_connections(outgoing_rows, incoming_rows, origin=origin_location.city_code, destination=destination_location.city_code, travel_date=day, limit=10)
            if direct_count or connections:
                options.append(FlightDateOption(travel_date=day, direct_offer_count=direct_count, connection_candidate_count=len(connections)))
            if len(options) >= 10: break
        return FlightAvailabilityResult(origin=origin_location.city_code, destination=destination_location.city_code, dates=options)

    @strawberry.field
    async def flight_search(self, origin: str, destination: str, travel_date: str, limit: int = 20) -> FlightSearchResult:
        origin_location = resolve_location(origin)
        destination_location = resolve_location(destination)
        if origin_location.city_code == destination_location.city_code:
            raise GraphQLError("Origin and destination must be different", extensions={"code": "BAD_USER_INPUT"})
        health_summary = _source_health_data()
        health_map = _health_map(health_summary)
        async with httpx.AsyncClient(timeout=8.0) as client:
            direct_r = await client.get(f"{FLIGHT_SERVICE_URL}/flights", params={
                "origins": ",".join(origin_location.flight_airports), "destinations": ",".join(destination_location.flight_airports),
                "travel_date": travel_date, "limit": 100,
            })
            direct_r.raise_for_status()
            direct_rows = direct_r.json()
            direct_offers = select_direction_offers(direct_rows, origin=origin_location.city_code, destination=destination_location.city_code, limit=10)
            coverage = build_direction_coverage(direct_rows, origin=origin_location.city_code, destination=destination_location.city_code, source_health=health_map, expected_sources=ACTIVE_FLIGHT_SOURCES, limit=10)
            if direct_offers:
                return FlightSearchResult(origin=origin_location.city_code, destination=destination_location.city_code, travel_date=travel_date, status=coverage.status, available_count=len(direct_offers), sources_checked=coverage.sources_checked, sources_available=coverage.sources_available, direct_offers=[_to_flight(row) for row in direct_offers], connections=[])
            outgoing_r, incoming_r = await asyncio.gather(
                client.get(f"{FLIGHT_SERVICE_URL}/flights", params={"origins": ",".join(origin_location.flight_airports), "travel_date": travel_date, "limit": 100}),
                client.get(f"{FLIGHT_SERVICE_URL}/flights", params={"destinations": ",".join(destination_location.flight_airports), "travel_date": travel_date, "limit": 100}),
            )
            outgoing_r.raise_for_status(); incoming_r.raise_for_status()
        candidates = build_suggested_connections(outgoing_r.json(), incoming_r.json(), origin=origin_location.city_code, destination=destination_location.city_code, travel_date=travel_date, limit=10)
        warning = "Verifica los horarios exactos con las aerolíneas."
        connections = [SuggestedConnection(via=item.via, stops=1, total_price=item.total_price, currency=item.currency, legs=[_to_flight(leg) for leg in item.legs], warning=warning) for item in candidates[:5]]
        return FlightSearchResult(origin=origin_location.city_code, destination=destination_location.city_code, travel_date=travel_date, status=coverage.status, available_count=len(connections), sources_checked=coverage.sources_checked, sources_available=coverage.sources_available, direct_offers=[], connections=connections)

    @strawberry.field
    async def travel_availability(
        self,
        origin: str,
        destination: str,
        outbound_limit: int = 8,
        return_limit: int = 8,
    ) -> TravelAvailability:
        origin_location = resolve_location(origin)
        destination_location = resolve_location(destination)
        if origin_location.city_code == destination_location.city_code:
            raise GraphQLError("Origin and destination must be different", extensions={"code": "BAD_USER_INPUT"})
        async with httpx.AsyncClient(timeout=8.0) as client:
            outbound_r, return_r = await asyncio.gather(
                client.get(
                    f"{FLIGHT_SERVICE_URL}/flights",
                    params={
                        "origins": ",".join(origin_location.flight_airports),
                        "destinations": ",".join(destination_location.flight_airports),
                        "limit": 100,
                    },
                ),
                client.get(
                    f"{FLIGHT_SERVICE_URL}/flights",
                    params={
                        "origins": ",".join(destination_location.flight_airports),
                        "destinations": ",".join(origin_location.flight_airports),
                        "limit": 100,
                    },
                ),
            )
            outbound_r.raise_for_status()
            return_r.raise_for_status()
        outbound_rows = outbound_r.json()
        return_rows = return_r.json()
        result = build_availability(outbound_rows, return_rows, outbound_limit, return_limit)
        airports = sorted({str(row.get("destination", "")).upper() for row in outbound_rows if row.get("destination")})
        return TravelAvailability(
            origin=origin_location.city_code,
            destination=destination_location.city_code,
            airport_codes=airports,
            outbound_dates=list(result.outbound_dates),
            return_dates=list(result.return_dates),
            outbound_offer_count=result.outbound_offer_count,
            return_offer_count=result.return_offer_count,
            combinations=[DateCombination(
                departure_date=item.departure_date,
                return_date=item.return_date,
                nights=item.nights,
                lowest_outbound_price=item.lowest_outbound_price,
                lowest_return_price=item.lowest_return_price,
                lowest_flight_total=item.lowest_flight_total,
            ) for item in result.combinations],
        )

    @strawberry.field
    async def travel_packages(
        self,
        origin: str,
        destination: str,
        start_date: str,
        end_date: str,
        limit: int = 8,
    ) -> list[TravelPackage]:
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
            nights = (end - start).days
        except ValueError as exc:
            raise GraphQLError("Dates must use YYYY-MM-DD", extensions={"code": "BAD_USER_INPUT"}) from exc
        if nights < 1 or nights > 14:
            raise GraphQLError("Trip duration must be between 1 and 14 nights", extensions={"code": "BAD_USER_INPUT"})
        origin_location = resolve_location(origin)
        destination_location = resolve_location(destination)
        if origin_location.city_code == destination_location.city_code:
            raise GraphQLError("Origin and destination must be different", extensions={"code": "BAD_USER_INPUT"})

        async with httpx.AsyncClient(timeout=8.0) as client:
            outbound_r, return_r, hotels_r, cars_r = await asyncio.gather(
                client.get(f"{FLIGHT_SERVICE_URL}/flights", params={
                    "origins": ",".join(origin_location.flight_airports),
                    "destinations": ",".join(destination_location.flight_airports),
                    "travel_date": start_date,
                    "limit": 100,
                }),
                client.get(f"{FLIGHT_SERVICE_URL}/flights", params={
                    "origins": ",".join(destination_location.flight_airports),
                    "destinations": ",".join(origin_location.flight_airports),
                    "travel_date": end_date,
                    "limit": 100,
                }),
                client.get(f"{HOTEL_SERVICE_URL}/hotels", params={"city": destination_location.service_city, "limit": 50}),
                client.get(f"{CAR_SERVICE_URL}/cars", params={"city": destination_location.service_city, "limit": 50}),
            )
            for response in (outbound_r, return_r, hotels_r, cars_r):
                response.raise_for_status()

        candidates = build_roundtrip_packages(
            outbound_r.json(), return_r.json(), hotels_r.json(), cars_r.json(), nights, min(max(limit, 1), 12)
        )
        packages: list[TravelPackage] = []
        for candidate in candidates:
            outbound = _to_flight(candidate.outbound)
            return_flight = _to_flight(candidate.return_flight)
            hotel = _to_hotel(candidate.hotel)
            car = _to_car(candidate.car)
            packages.append(TravelPackage(
                id=f"{outbound.id}:{return_flight.id}:{hotel.id}:{car.id}:{nights}",
                outbound_flight=outbound,
                return_flight=return_flight,
                hotel=hotel,
                car=car,
                nights=nights,
                flight_total=candidate.flight_total,
                total=candidate.total,
            ))
        return packages

    @strawberry.field
    async def my_bookings(self, info: Info) -> list[Booking]:
        session = await _require_user(info)
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{ORDER_SERVICE_URL}/orders", params={"user_id": session["user_id"]})
            response.raise_for_status()
            return [_to_booking(row) for row in response.json()]

    @strawberry.field
    async def saga_events(self, info: Info, order_id: str) -> list[SagaEvent]:
        session = await _require_user(info)
        # Verify ownership before exposing operational details.
        async with httpx.AsyncClient(timeout=8.0) as client:
            order_response = await client.get(f"{ORDER_SERVICE_URL}/orders/{order_id}")
            order_response.raise_for_status()
            if int(order_response.json()["user_id"]) != int(session["user_id"]):
                raise GraphQLError("Forbidden", extensions={"code": "FORBIDDEN"})
            response = await client.get(f"{ORDER_SERVICE_URL}/orders/{order_id}/saga-events")
            response.raise_for_status()
        return [SagaEvent(
            id=int(row["id"]), order_id=row["order_id"], step=row["step"], action=row["action"], status=row["status"],
            detail=row.get("detail"), created_at=str(row["created_at"])
        ) for row in response.json()]

    @strawberry.field
    def database_status(self) -> DatabaseStatus:
        row = fetch_one("SELECT current_database() AS database, current_user AS db_user")
        counts = {}
        for table in ("users", "flights", "hotels", "cars", "orders"):
            counts[table] = int(fetch_one(f"SELECT COUNT(*) AS count FROM {table}")["count"])
        return DatabaseStatus(
            connected=True,
            database=row["database"],
            db_user=row["db_user"],
            users=counts["users"],
            flights=counts["flights"],
            hotels=counts["hotels"],
            cars=counts["cars"],
            orders=counts["orders"],
        )

    @strawberry.field
    def security_status(self) -> SecurityStatus:
        return SecurityStatus(
            password_hashing="Argon2id (argon2-cffi PasswordHasher)",
            session_fixation_protection="Session ID invalidated and regenerated after successful login",
            cookie_policy=f"HttpOnly; SameSite=Lax; Secure={COOKIE_SECURE}",
            login_rate_limit="5 attempts / 60 seconds per IP + account",
            checkout_rate_limit="10 attempts / 60 seconds per authenticated user",
            payment_rate_limit="10 attempts / 60 seconds per authenticated user",
            dependency_audit="npm audit + pip-audit scripts under security/",
        )


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def register(self, info: Info, email: str, full_name: str, password: str) -> User:
        response: Response = info.context["response"]
        request: Request = info.context["request"]
        await enforce_rate_limit(redis_client, f"rl:register:{_client_ip(request)}", 5, 60, response)
        email = email.strip().lower()
        full_name = full_name.strip()
        if "@" not in email or not full_name or len(password) < 8:
            raise GraphQLError("Use a valid email, name and password of at least 8 characters", extensions={"code": "BAD_USER_INPUT"})
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO users(email,full_name,password_hash) VALUES(%s,%s,%s) RETURNING id,email,full_name",
                        (email, full_name, hash_password(password)),
                    )
                    row = cur.fetchone()
        except Exception as exc:
            if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                raise GraphQLError("Email is already registered", extensions={"code": "CONFLICT"}) from exc
            raise
        return User(**row)

    @strawberry.mutation
    async def login(self, info: Info, email: str, password: str) -> User:
        request: Request = info.context["request"]
        response: Response = info.context["response"]
        normalized_email = email.strip().lower()
        await enforce_rate_limit(
            redis_client,
            f"rl:login:{_client_ip(request)}:{normalized_email}",
            5,
            60,
            response,
        )
        row = fetch_one("SELECT id,email,full_name,password_hash FROM users WHERE email=%s", (normalized_email,))
        if not row or not verify_password(row["password_hash"], password):
            raise GraphQLError("Invalid credentials", extensions={"code": "INVALID_CREDENTIALS"})

        # Session Fixation mitigation: explicitly invalidate pre-authentication SID and rotate it.
        old_sid = request.cookies.get(COOKIE_NAME)
        if old_sid:
            await redis_client.delete(f"session:{old_sid}")
        new_sid = new_session_id()
        await redis_client.setex(
            f"session:{new_sid}",
            60 * 60 * 8,
            session_payload(authenticated=True, user_id=row["id"], email=row["email"]),
        )
        _set_session_cookie(response, new_sid)
        return User(id=row["id"], email=row["email"], full_name=row["full_name"])

    @strawberry.mutation
    async def logout(self, info: Info) -> bool:
        request: Request = info.context["request"]
        response: Response = info.context["response"]
        sid = request.cookies.get(COOKIE_NAME)
        if sid:
            await redis_client.delete(f"session:{sid}")
        new_sid = new_session_id()
        await redis_client.setex(f"session:{new_sid}", 60 * 60 * 8, session_payload(authenticated=False))
        _set_session_cookie(response, new_sid)
        return True

    @strawberry.mutation
    async def checkout_package(
        self,
        info: Info,
        outbound_flight_id: str,
        return_flight_id: str,
        hotel_id: str,
        car_id: str,
        nights: int,
        total: float,
        simulate_failure: Optional[str] = None,
    ) -> Booking:
        session = await _require_user(info)
        response: Response = info.context["response"]
        user_id = int(session["user_id"])
        # Separate logical policies for checkout and payment, both enforced before the SAGA starts.
        await enforce_rate_limit(redis_client, f"rl:checkout:user:{user_id}", 10, 60, response)
        await enforce_rate_limit(redis_client, f"rl:payment:user:{user_id}", 10, 60, response)
        async with httpx.AsyncClient(timeout=30.0) as client:
            checkout_response = await client.post(
                f"{ORDER_SERVICE_URL}/checkout",
                json={
                    "user_id": user_id,
                    "outbound_flight_id": outbound_flight_id,
                    "return_flight_id": return_flight_id,
                    "hotel_id": hotel_id,
                    "car_id": car_id,
                    "nights": nights,
                    # Sent for observability only; Order Service recomputes the authoritative total.
                    "quoted_total": total,
                    "simulate_failure": simulate_failure,
                },
            )
            checkout_response.raise_for_status()
            order_id = checkout_response.json()["id"]
            order_response = await client.get(f"{ORDER_SERVICE_URL}/orders/{order_id}")
            order_response.raise_for_status()
            return _to_booking(order_response.json())


async def get_context(request: Request, response: Response):
    return {"request": request, "response": response}


schema = strawberry.Schema(query=Query, mutation=Mutation)
graphql_app = GraphQLRouter(schema, context_getter=get_context, graphql_ide="graphiql")

app = FastAPI(title="WanderSync GraphQL Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.get("/health")
async def health(response: Response):
    try:
        redis_ok = bool(await redis_client.ping())
    except Exception:
        redis_ok = False
    try:
        db_row = fetch_one("SELECT current_database() AS database, current_user AS db_user")
        db_ok = bool(db_row)
    except Exception:
        db_row = None
        db_ok = False
    if not (redis_ok and db_ok):
        response.status_code = 503
    return {
        "status": "ok" if redis_ok and db_ok else "degraded",
        "service": "graphql-gateway",
        "redis": redis_ok,
        "database": db_ok,
        "database_name": db_row["database"] if db_row else None,
        "database_user": db_row["db_user"] if db_row else None,
    }

app.include_router(graphql_app, prefix="/graphql")
