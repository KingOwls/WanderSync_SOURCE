CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrape_snapshots (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    http_status INTEGER,
    status TEXT NOT NULL,
    snapshot_path TEXT NOT NULL,
    html_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source, kind, query_hash, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_scrape_snapshots_lookup
    ON scrape_snapshots(source, kind, query_hash, captured_at DESC);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    query_hash TEXT,
    source_url TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    snapshot_id TEXT REFERENCES scrape_snapshots(id),
    items_found INTEGER NOT NULL DEFAULT 0,
    http_status INTEGER,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_latest ON scrape_runs(source, kind, started_at DESC);

CREATE TABLE IF NOT EXISTS flights (
    id TEXT PRIMARY KEY,
    airline TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    travel_date DATE NOT NULL,
    departure_at TIMESTAMPTZ,
    arrival_at TIMESTAMPTZ,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    currency TEXT NOT NULL DEFAULT 'COP',
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hotels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    room_type TEXT,
    city TEXT NOT NULL,
    nightly_price NUMERIC(12,2) NOT NULL CHECK (nightly_price >= 0),
    currency TEXT NOT NULL DEFAULT 'COP',
    rating NUMERIC(2,1),
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cars (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    city TEXT NOT NULL,
    daily_price NUMERIC(12,2) NOT NULL CHECK (daily_price >= 0),
    currency TEXT NOT NULL DEFAULT 'COP',
    category TEXT,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Idempotent migration from the previous mock-catalog schema.
ALTER TABLE flights ADD COLUMN IF NOT EXISTS travel_date DATE;
ALTER TABLE flights ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'COP';
ALTER TABLE flights ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE flights ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE flights ADD COLUMN IF NOT EXISTS snapshot_id TEXT;
ALTER TABLE flights ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMPTZ;
ALTER TABLE flights ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE flights ALTER COLUMN departure_at DROP NOT NULL;
ALTER TABLE flights ALTER COLUMN arrival_at DROP NOT NULL;
ALTER TABLE flights DROP COLUMN IF EXISTS available_seats;

ALTER TABLE hotels ADD COLUMN IF NOT EXISTS room_type TEXT;
ALTER TABLE hotels ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'COP';
ALTER TABLE hotels ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE hotels ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE hotels ADD COLUMN IF NOT EXISTS snapshot_id TEXT;
ALTER TABLE hotels ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMPTZ;
ALTER TABLE hotels ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE hotels ALTER COLUMN rating DROP NOT NULL;
ALTER TABLE hotels DROP COLUMN IF EXISTS available_rooms;

ALTER TABLE cars ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'COP';
ALTER TABLE cars ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE cars ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE cars ADD COLUMN IF NOT EXISTS snapshot_id TEXT;
ALTER TABLE cars ADD COLUMN IF NOT EXISTS scraped_at TIMESTAMPTZ;
ALTER TABLE cars ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE cars ALTER COLUMN category DROP NOT NULL;
ALTER TABLE cars DROP COLUMN IF EXISTS available_units;


-- Create catalog indexes only after the legacy migration has added every referenced column.
-- This ordering is required when db-bootstrap runs against a persistent volume created by
-- an older WanderSync version where travel_date/active did not exist yet.
CREATE INDEX IF NOT EXISTS idx_flights_route ON flights(origin, destination, travel_date);
CREATE INDEX IF NOT EXISTS idx_hotels_city ON hotels(city, active);
CREATE INDEX IF NOT EXISTS idx_cars_city ON cars(city, active);

CREATE TABLE IF NOT EXISTS flight_reservations (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    flight_id TEXT NOT NULL REFERENCES flights(id),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS hotel_reservations (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    hotel_id TEXT NOT NULL REFERENCES hotels(id),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS car_reservations (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    car_id TEXT NOT NULL REFERENCES cars(id),
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    flight_id TEXT NOT NULL,
    outbound_flight_id TEXT,
    return_flight_id TEXT,
    hotel_id TEXT NOT NULL,
    car_id TEXT NOT NULL,
    total NUMERIC(12,2) NOT NULL,
    status TEXT NOT NULL,
    payment_status TEXT NOT NULL DEFAULT 'PENDING',
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS outbound_flight_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS return_flight_id TEXT;
UPDATE orders SET outbound_flight_id=flight_id WHERE outbound_flight_id IS NULL AND flight_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS saga_events (
    id BIGSERIAL PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_saga_order ON saga_events(order_id, id);

CREATE TABLE IF NOT EXISTS billing_events (
    id BIGSERIAL PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    amount NUMERIC(12,2) NOT NULL,
    status TEXT NOT NULL,
    provider_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Remove only legacy rows that predate provenance. Their local demo orders/holds cannot be trusted
-- once the catalog switches from generated inventory to real scraped offers. User accounts are preserved.
DELETE FROM billing_events WHERE order_id IN (
    SELECT id FROM orders
    WHERE COALESCE(outbound_flight_id, flight_id) IN (SELECT id FROM flights WHERE source IS NULL)
       OR return_flight_id IN (SELECT id FROM flights WHERE source IS NULL)
       OR hotel_id IN (SELECT id FROM hotels WHERE source IS NULL)
       OR car_id IN (SELECT id FROM cars WHERE source IS NULL)
);
DELETE FROM saga_events WHERE order_id IN (
    SELECT id FROM orders
    WHERE COALESCE(outbound_flight_id, flight_id) IN (SELECT id FROM flights WHERE source IS NULL)
       OR return_flight_id IN (SELECT id FROM flights WHERE source IS NULL)
       OR hotel_id IN (SELECT id FROM hotels WHERE source IS NULL)
       OR car_id IN (SELECT id FROM cars WHERE source IS NULL)
);
DELETE FROM flight_reservations WHERE flight_id IN (SELECT id FROM flights WHERE source IS NULL);
DELETE FROM hotel_reservations WHERE hotel_id IN (SELECT id FROM hotels WHERE source IS NULL);
DELETE FROM car_reservations WHERE car_id IN (SELECT id FROM cars WHERE source IS NULL);
DELETE FROM orders WHERE COALESCE(outbound_flight_id, flight_id) IN (SELECT id FROM flights WHERE source IS NULL)
   OR return_flight_id IN (SELECT id FROM flights WHERE source IS NULL)
   OR hotel_id IN (SELECT id FROM hotels WHERE source IS NULL)
   OR car_id IN (SELECT id FROM cars WHERE source IS NULL);
DELETE FROM flights WHERE source IS NULL;
DELETE FROM hotels WHERE source IS NULL;
DELETE FROM cars WHERE source IS NULL;

ALTER TABLE flights ALTER COLUMN travel_date SET NOT NULL;
ALTER TABLE flights ALTER COLUMN currency SET NOT NULL;
ALTER TABLE flights ALTER COLUMN source SET NOT NULL;
ALTER TABLE flights ALTER COLUMN source_url SET NOT NULL;
ALTER TABLE flights ALTER COLUMN snapshot_id SET NOT NULL;
ALTER TABLE flights ALTER COLUMN scraped_at SET NOT NULL;
ALTER TABLE hotels ALTER COLUMN currency SET NOT NULL;
ALTER TABLE hotels ALTER COLUMN source SET NOT NULL;
ALTER TABLE hotels ALTER COLUMN source_url SET NOT NULL;
ALTER TABLE hotels ALTER COLUMN snapshot_id SET NOT NULL;
ALTER TABLE hotels ALTER COLUMN scraped_at SET NOT NULL;
ALTER TABLE cars ALTER COLUMN currency SET NOT NULL;
ALTER TABLE cars ALTER COLUMN source SET NOT NULL;
ALTER TABLE cars ALTER COLUMN source_url SET NOT NULL;
ALTER TABLE cars ALTER COLUMN snapshot_id SET NOT NULL;
ALTER TABLE cars ALTER COLUMN scraped_at SET NOT NULL;
