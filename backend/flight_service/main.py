import uuid
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from common.config import ALLOW_FAILURE_INJECTION
from common.db import get_conn, fetch_all, fetch_one

app = FastAPI(title="WanderSync Flight Service", version="2.0.0")

class ReservationRequest(BaseModel):
    item_id: str
    order_id: str
    force_fail: bool = False

@app.get("/health")
def health(response: Response):
    try:
        fetch_one("SELECT 1 AS ok")
        return {"status": "ok", "service": "flights", "database": True, "catalog": "real-scraped"}
    except Exception as exc:
        response.status_code = 503
        return {"status": "degraded", "service": "flights", "database": False, "detail": str(exc)}

def _parse_codes(value: str | None) -> list[str]:
    if not value:
        return []
    codes = [part.strip().upper() for part in value.split(",") if part.strip()]
    return codes[:20]


@app.get("/flights")
def list_flights(
    origin: str | None = None,
    destination: str | None = None,
    origins: str | None = None,
    destinations: str | None = None,
    travel_date: str | None = None,
    limit: int = 50,
):
    clauses = ["active=TRUE"]
    params: list[object] = []
    origin_codes = _parse_codes(origins) or ([origin.strip().upper()] if origin else [])
    destination_codes = _parse_codes(destinations) or ([destination.strip().upper()] if destination else [])
    if origin_codes:
        clauses.append("origin = ANY(%s)")
        params.append(origin_codes)
    if destination_codes:
        clauses.append("destination = ANY(%s)")
        params.append(destination_codes)
    if travel_date:
        clauses.append("travel_date=%s")
        params.append(travel_date)
    params.append(min(max(limit, 1), 100))
    sql = f"""SELECT id, airline, origin, destination, travel_date::text AS travel_date,
                     departure_at, arrival_at, price::float AS price, currency,
                     source, source_url, snapshot_id, scraped_at
              FROM flights
              WHERE {' AND '.join(clauses)}
              ORDER BY travel_date ASC, price ASC LIMIT %s"""
    return fetch_all(sql, tuple(params))

@app.get("/routes")
def list_routes():
    sql = """SELECT origin, destination,
                    COUNT(*)::int AS offer_count,
                    ARRAY_AGG(DISTINCT source ORDER BY source) AS sources,
                    MIN(travel_date)::text AS first_date,
                    MAX(travel_date)::text AS last_date,
                    MIN(price)::float AS lowest_price
             FROM flights
             WHERE active=TRUE
             GROUP BY origin, destination
             ORDER BY origin, destination"""
    return fetch_all(sql)


@app.post("/reservations")
def reserve(req: ReservationRequest):
    if req.force_fail and ALLOW_FAILURE_INJECTION:
        raise HTTPException(status_code=503, detail="Simulated local flight-hold failure")
    reservation_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM flights WHERE id=%s AND active=TRUE FOR UPDATE", (req.item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Active scraped flight offer not found")
            cur.execute(
                "INSERT INTO flight_reservations(id, order_id, flight_id, status) VALUES(%s,%s,%s,'HELD')",
                (reservation_id, req.order_id, req.item_id),
            )
    return {"reservation_id": reservation_id, "status": "HELD", "scope": "WANDERSYNC_LOCAL_HOLD"}

@app.delete("/reservations/{reservation_id}")
def cancel(reservation_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT flight_id, status FROM flight_reservations WHERE id=%s FOR UPDATE", (reservation_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Reservation not found")
            if row["status"] == "CANCELLED":
                return {"reservation_id": reservation_id, "status": "CANCELLED"}
            cur.execute("UPDATE flight_reservations SET status='CANCELLED' WHERE id=%s", (reservation_id,))
    return {"reservation_id": reservation_id, "status": "CANCELLED"}
