# Database migration hotfix

## Symptom

When upgrading an existing WanderSync PostgreSQL volume from the previous catalog schema, `db-bootstrap` could fail with:

```text
ERROR: column "travel_date" does not exist
CREATE INDEX IF NOT EXISTS idx_flights_route ON flights(origin, destination, travel_date);
```

The same ordering problem also applied to the new `active` column used by hotel and car indexes.

## Root cause

`CREATE TABLE IF NOT EXISTS` does not modify an existing table. The bootstrap SQL tried to create indexes that referenced new columns before the idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migration had added those columns to an old persistent volume.

## Fix

Catalog indexes are now created only after all legacy `ALTER TABLE` statements have added their referenced columns:

- `flights.travel_date`
- `hotels.active`
- `cars.active`

The bootstrap remains idempotent and preserves the PostgreSQL volume and user accounts. Legacy generated catalog rows are removed by the existing migration as designed.

## Recovery

After replacing the project files, do **not** delete the PostgreSQL volume. Run:

```bash
docker compose up -d --build
```

Or rerun only bootstrap first:

```bash
docker compose run --rm db-bootstrap
```

Then verify:

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c "SELECT column_name FROM information_schema.columns WHERE table_name='flights' ORDER BY ordinal_position;"
```

`travel_date`, `source`, `source_url`, `snapshot_id`, `scraped_at`, and `active` should be present.
