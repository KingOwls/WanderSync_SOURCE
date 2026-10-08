import os
import asyncio
import hashlib
import json
from common.journey import validate_journey
import uuid
from decimal import Decimal
import httpx
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from common.config import FLIGHT_SERVICE_URL, HOTEL_SERVICE_URL, CAR_SERVICE_URL, ALLOW_FAILURE_INJECTION
from common.db import get_conn, fetch_all, fetch_one
from common.reservation import CompensationStep, reverse_compensation_order

app = FastAPI(title="WanderSync Order & Billing Service", version="1.0.0")

class CheckoutRequest(BaseModel):
    user_id: int
    outbound_flight_id: str
    return_flight_id: str
    hotel_id: str
    car_id: str
    nights: int = Field(ge=1, le=14)
    quoted_total: float | None = Field(default=None, gt=0)
    simulate_failure: str | None = None
    idempotency_key: str = Field(min_length=8, max_length=128)

SERVICE_URLS = {
    "flight": FLIGHT_SERVICE_URL,
    "hotel": HOTEL_SERVICE_URL,
    "car": CAR_SERVICE_URL,
}


def _authoritative_total(outbound_flight_id: str, return_flight_id: str, hotel_id: str, car_id: str, nights: int) -> Decimal:
    """Never trust a client-supplied checkout amount; derive it from current active scraped catalog prices."""
    outbound_flight = fetch_one("SELECT price FROM flights WHERE id=%s AND active=TRUE AND currency='COP'", (outbound_flight_id,))
    return_flight = fetch_one("SELECT price FROM flights WHERE id=%s AND active=TRUE AND currency='COP'", (return_flight_id,))
    hotel = fetch_one("SELECT nightly_price FROM hotels WHERE id=%s AND active=TRUE AND currency='COP'", (hotel_id,))
    car = fetch_one("SELECT daily_price FROM cars WHERE id=%s AND active=TRUE AND currency='COP'", (car_id,))
    if not outbound_flight or not return_flight or not hotel or not car:
        raise HTTPException(status_code=404, detail="One or more selected scraped offers are no longer active")
    return (
        Decimal(str(outbound_flight["price"]))
        + Decimal(str(return_flight["price"]))
        + Decimal(str(hotel["nightly_price"])) * nights
        + Decimal(str(car["daily_price"])) * nights
    ).quantize(Decimal("0.01"))


def _log_event(order_id: str, step: str, action: str, status: str, detail: str | None = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO saga_events(order_id, step, action, status, detail) VALUES(%s,%s,%s,%s,%s)",
                (order_id, step, action, status, detail),
            )


def _set_order(order_id: str, *, status: str, payment_status: str | None = None, failure_reason: str | None = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            if payment_status is None:
                cur.execute(
                    "UPDATE orders SET status=%s, failure_reason=%s, updated_at=NOW() WHERE id=%s",
                    (status, failure_reason, order_id),
                )
            else:
                cur.execute(
                    "UPDATE orders SET status=%s, payment_status=%s, failure_reason=%s, updated_at=NOW() WHERE id=%s",
                    (status, payment_status, failure_reason, order_id),
                )


async def _reserve(client: httpx.AsyncClient, service: str, item_id: str, order_id: str, force_fail: bool):
    url = SERVICE_URLS[service] + "/reservations"
    response = await client.post(url, json={"item_id": item_id, "order_id": order_id, "force_fail": force_fail})
    response.raise_for_status()
    return response.json()


async def _compensate(client: httpx.AsyncClient, order_id: str, confirmed: list[CompensationStep]):
    _set_order(order_id, status="COMPENSATING")
    known = {step.reservation_id for step in confirmed}
    confirmed = list(confirmed)
    for service in SERVICE_URLS:
        holds = fetch_all(f"SELECT id::text AS id FROM {service}_reservations WHERE order_id=%s AND status='HELD' ORDER BY created_at,id", (order_id,))
        for hold in holds:
            if hold["id"] not in known:
                confirmed.append(CompensationStep(service, hold["id"]))
                known.add(hold["id"])
    compensation_errors: list[str] = []
    for step in reverse_compensation_order(confirmed):
        event_step = step.event_step or step.service
        _log_event(order_id, event_step, "COMPENSATE", "STARTED", step.reservation_id)
        try:
            response = await client.delete(f"{SERVICE_URLS[step.service]}/reservations/{step.reservation_id}")
            response.raise_for_status()
            _log_event(order_id, event_step, "COMPENSATE", "SUCCEEDED", "Reservation cancelled")
        except Exception as exc:  # logged so the failed compensation is observable
            msg = f"{type(exc).__name__}: {exc}"
            compensation_errors.append(msg)
            _log_event(order_id, event_step, "COMPENSATE", "FAILED", msg)
    return compensation_errors


@app.get("/health")
def health(response: Response):
    try:
        fetch_one("SELECT 1 AS ok")
        return {"status": "ok", "service": "orders-billing", "database": True}
    except Exception as exc:
        response.status_code = 503
        return {"status": "degraded", "service": "orders-billing", "database": False, "detail": str(exc)}


@app.post("/checkout")
async def checkout(req: CheckoutRequest):
    allowed_failures = {None, "flight", "outbound_flight", "return_flight", "hotel", "car", "billing"}
    if req.simulate_failure not in allowed_failures:
        raise HTTPException(status_code=400, detail="simulate_failure must be outbound_flight, return_flight, hotel, car, billing or null")
    if req.simulate_failure and not ALLOW_FAILURE_INJECTION:
        raise HTTPException(status_code=403, detail="Failure injection is disabled")

    request_hash = hashlib.sha256(json.dumps(req.model_dump(exclude={"idempotency_key"}), sort_keys=True).encode()).hexdigest()
    existing = fetch_one("SELECT id::text,status,payment_status,failure_reason,request_hash FROM orders WHERE user_id=%s AND idempotency_key=%s", (req.user_id, req.idempotency_key))
    if existing:
        if existing["request_hash"] != request_hash:
            raise HTTPException(409, "Idempotency key was already used for another request")
        if existing["status"] == "PROCESSING":
            raise HTTPException(409, "Order is still processing; consult your bookings before retrying")
        return existing
    selected = []
    for table, item_id in (("flights", req.outbound_flight_id), ("flights", req.return_flight_id), ("hotels", req.hotel_id), ("cars", req.car_id)):
        row = fetch_one(f"SELECT * FROM {table} WHERE id=%s AND active=TRUE AND scraped_at >= NOW() - INTERVAL '48 hours'", (item_id,))
        if not row:
            raise HTTPException(409, "A selected offer has expired; refresh the catalog")
        selected.append(row)
    try:
        validate_journey(*selected, req.nights)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    authoritative_total = _authoritative_total(req.outbound_flight_id, req.return_flight_id, req.hotel_id, req.car_id, req.nights)
    if req.quoted_total is not None and abs(authoritative_total - Decimal(str(req.quoted_total))) > Decimal("0.01"):
        raise HTTPException(409, "Price changed; refresh the package and accept the current total")
    order_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO orders(id,user_id,flight_id,outbound_flight_id,return_flight_id,hotel_id,car_id,total,status,payment_status,idempotency_key,request_hash)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'PROCESSING','PENDING',%s,%s) ON CONFLICT (user_id,idempotency_key) WHERE idempotency_key IS NOT NULL DO NOTHING RETURNING id""",
                (order_id, req.user_id, req.outbound_flight_id, req.outbound_flight_id, req.return_flight_id, req.hotel_id, req.car_id, authoritative_total, req.idempotency_key, request_hash),
            )

            if cur.fetchone() is None:
                raise HTTPException(409, "Order already submitted; consult your bookings")

    confirmed: list[CompensationStep] = []
    timeout = httpx.Timeout(10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            steps = (
                ("outbound_flight", "flight", req.outbound_flight_id),
                ("return_flight", "flight", req.return_flight_id),
                ("hotel", "hotel", req.hotel_id),
                ("car", "car", req.car_id),
            )
            for event_step, service, item_id in steps:
                _log_event(order_id, event_step, "RESERVE", "STARTED", item_id)
                try:
                    force_fail = req.simulate_failure == event_step or (req.simulate_failure == "flight" and event_step == "outbound_flight")
                    data = await _reserve(client, service, item_id, order_id, force_fail)
                    reservation_id = data["reservation_id"]
                    confirmed.append(CompensationStep(service=service, reservation_id=reservation_id, event_step=event_step))
                    _log_event(order_id, event_step, "RESERVE", "SUCCEEDED", reservation_id)
                except Exception as exc:
                    _log_event(order_id, event_step, "RESERVE", "FAILED", str(exc))
                    errors = await _compensate(client, order_id, confirmed)
                    reason = f"{event_step} reservation failed"
                    if errors:
                        reason += f"; compensation errors={len(errors)}"
                    _set_order(order_id, status="COMPENSATION_PENDING" if errors else "CANCELLED", payment_status="NOT_CHARGED", failure_reason=reason)
                    return {"id": order_id, "status": "CANCELLED", "payment_status": "NOT_CHARGED", "failure_reason": reason}

            # Billing is intentionally part of the same SAGA so a failed charge compensates all reservations.
            _log_event(order_id, "billing", "CHARGE", "STARTED", f"amount={authoritative_total}")
            if req.simulate_failure == "billing":
                _log_event(order_id, "billing", "CHARGE", "FAILED", "Simulated billing failure")
                errors = await _compensate(client, order_id, confirmed)
                reason = "billing failed"
                if errors:
                    reason += f"; compensation errors={len(errors)}"
                _set_order(order_id, status="COMPENSATION_PENDING" if errors else "CANCELLED", payment_status="FAILED", failure_reason=reason)
                with get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO billing_events(order_id,amount,status) VALUES(%s,%s,'FAILED')",
                            (order_id, authoritative_total),
                        )
                return {"id": order_id, "status": "CANCELLED", "payment_status": "FAILED", "failure_reason": reason}

            provider_reference = f"PAY-{uuid.uuid4().hex[:12].upper()}"
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO billing_events(order_id,amount,status,provider_reference) VALUES(%s,%s,'PAID',%s)",
                        (order_id, authoritative_total, provider_reference),
                    )
            _log_event(order_id, "billing", "CHARGE", "SUCCEEDED", provider_reference)
            _set_order(order_id, status="CONFIRMED", payment_status="PAID", failure_reason=None)
            return {"id": order_id, "status": "CONFIRMED", "payment_status": "PAID", "failure_reason": None}
    except Exception as exc:
        # Defensive catch-all: if an unexpected failure occurs after any reservation, compensate before returning ERROR.
        try:
            async with httpx.AsyncClient(timeout=timeout) as recovery_client:
                await _compensate(recovery_client, order_id, confirmed)
        finally:
            _set_order(order_id, status="ERROR", payment_status="UNKNOWN", failure_reason=str(exc))
        raise


@app.get("/orders/{order_id}")
def order(order_id: str):
    row = fetch_one(
        """SELECT id::text AS id,user_id,flight_id,outbound_flight_id,return_flight_id,hotel_id,car_id,total::float AS total,
                  status,payment_status,failure_reason,created_at,updated_at
           FROM orders WHERE id=%s""",
        (order_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")
    return row


@app.get("/orders")
def orders(user_id: int):
    return fetch_all(
        """SELECT id::text AS id,user_id,flight_id,outbound_flight_id,return_flight_id,hotel_id,car_id,total::float AS total,
                  status,payment_status,failure_reason,created_at,updated_at
           FROM orders WHERE user_id=%s ORDER BY created_at DESC LIMIT 50""",
        (user_id,),
    )


@app.get("/orders/{order_id}/saga-events")
def saga_events(order_id: str):
    return fetch_all(
        """SELECT id, order_id::text AS order_id, step, action, status, detail, created_at
           FROM saga_events WHERE order_id=%s ORDER BY id ASC""",
        (order_id,),
    )


async def recover_pending_orders():
    rows = fetch_all("SELECT id::text AS id FROM orders WHERE status IN ('PROCESSING','ERROR','COMPENSATING','COMPENSATION_PENDING') AND updated_at < NOW() - INTERVAL '5 minutes'")
    async with httpx.AsyncClient(timeout=10) as client:
        for row in rows:
            order_id = row["id"]
            with get_conn() as conn:
                if not conn.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS locked", (order_id,)).fetchone()["locked"]:
                    continue
                steps = []
                for service in SERVICE_URLS:
                    holds = fetch_all(f"SELECT id::text AS id FROM {service}_reservations WHERE order_id=%s AND status='HELD' ORDER BY created_at,id", (order_id,))
                    steps.extend(CompensationStep(service, hold["id"]) for hold in holds)
                errors = await _compensate(client, order_id, steps)
                if not errors:
                    conn.execute("UPDATE billing_events SET status='REFUNDED' WHERE order_id=%s AND status='PAID'", (order_id,))
                    _set_order(order_id, status="CANCELLED", payment_status="NOT_CHARGED", failure_reason="Recovered interrupted local SAGA; any local charge was reversed")
                else:
                    _set_order(order_id, status="COMPENSATION_PENDING", payment_status="UNKNOWN", failure_reason="Recovery will retry failed compensations")

async def recovery_loop():
    while True:
        try:
            await recover_pending_orders()
        except Exception:
            import logging
            logging.exception("SAGA recovery failed; will retry")
        await asyncio.sleep(30)

@app.on_event("startup")
async def start_recovery():
    app.state.recovery_task = asyncio.create_task(recovery_loop())

@app.on_event("shutdown")
async def stop_recovery():
    app.state.recovery_task.cancel()
