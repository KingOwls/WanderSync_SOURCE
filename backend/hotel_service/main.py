import uuid
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from common.config import ALLOW_FAILURE_INJECTION
from common.db import get_conn, fetch_all, fetch_one

app = FastAPI(title="WanderSync Hotel Service", version="2.0.0")

class ReservationRequest(BaseModel):
    item_id: str
    order_id: str
    force_fail: bool = False

@app.get("/health")
def health(response: Response):
    try:
        fetch_one("SELECT 1 AS ok")
        return {"status": "ok", "service": "hotels", "database": True, "catalog": "real-scraped"}
    except Exception as exc:
        response.status_code = 503
        return {"status": "degraded", "service": "hotels", "database": False, "detail": str(exc)}

@app.get("/hotels")
def list_hotels(city: str, limit: int = 50):
    return fetch_all(
        """SELECT id, name, room_type, city, nightly_price::float AS nightly_price,
                  currency, rating::float AS rating, source, source_url, snapshot_id, scraped_at
           FROM hotels WHERE city=%s AND active=TRUE AND scraped_at >= NOW() - INTERVAL '48 hours'
           ORDER BY nightly_price ASC LIMIT %s""",
        (city.upper(), min(max(limit, 1), 100)),
    )

@app.post("/reservations")
def reserve(req: ReservationRequest):
    if req.force_fail and ALLOW_FAILURE_INJECTION:
        raise HTTPException(status_code=503, detail="Simulated local hotel-hold failure")
    reservation_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            order = cur.execute("SELECT status FROM orders WHERE id=%s FOR UPDATE", (req.order_id,)).fetchone()
            if not order or order["status"] != "PROCESSING":
                raise HTTPException(409, "Order is not processing")
            cur.execute("SELECT id FROM hotels WHERE id=%s AND active=TRUE AND scraped_at >= NOW() - INTERVAL '48 hours' FOR UPDATE", (req.item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Active scraped hotel offer not found")
            existing = cur.execute("SELECT id::text AS id FROM hotel_reservations WHERE order_id=%s AND hotel_id=%s AND status='HELD'", (req.order_id, req.item_id)).fetchone()
            if existing:
                return {"reservation_id": existing["id"], "status": "HELD", "scope": "WANDERSYNC_LOCAL_HOLD"}
            cur.execute(
                "INSERT INTO hotel_reservations(id, order_id, hotel_id, status) VALUES(%s,%s,%s,'HELD')",
                (reservation_id, req.order_id, req.item_id),
            )
    return {"reservation_id": reservation_id, "status": "HELD", "scope": "WANDERSYNC_LOCAL_HOLD"}

@app.delete("/reservations/{reservation_id}")
def cancel(reservation_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT hotel_id, status FROM hotel_reservations WHERE id=%s FOR UPDATE", (reservation_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Reservation not found")
            if row["status"] == "CANCELLED":
                return {"reservation_id": reservation_id, "status": "CANCELLED"}
            cur.execute("UPDATE hotel_reservations SET status='CANCELLED' WHERE id=%s", (reservation_id,))
    return {"reservation_id": reservation_id, "status": "CANCELLED"}
