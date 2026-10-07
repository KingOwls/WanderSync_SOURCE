#!/usr/bin/env sh
set -eu
DC="${DC:-docker compose}"
$DC exec -T postgres psql -U "${POSTGRES_USER:-wandersync}" -d "${POSTGRES_DB:-wandersync}" -v ON_ERROR_STOP=1 <<'SQL'
SELECT current_database() AS database, current_user AS db_user;
SELECT 'flights' AS kind, source, COUNT(*) FROM flights GROUP BY source
UNION ALL SELECT 'hotels', source, COUNT(*) FROM hotels GROUP BY source
UNION ALL SELECT 'cars', source, COUNT(*) FROM cars GROUP BY source
ORDER BY kind, source;
SELECT id, source, kind, status, items_found, started_at, finished_at
FROM scrape_runs ORDER BY id DESC LIMIT 10;
SELECT id, source, kind, captured_at, snapshot_path, html_sha256
FROM scrape_snapshots ORDER BY captured_at DESC LIMIT 10;
BEGIN;
INSERT INTO scrape_runs(source,kind,status,items_found) VALUES('db-check','diagnostic','SUCCESS',0);
ROLLBACK;
SQL
