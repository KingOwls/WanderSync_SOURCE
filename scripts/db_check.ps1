$ErrorActionPreference = "Stop"
$User = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "wandersync" }
$Db = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "wandersync" }
docker compose exec -T postgres psql -U $User -d $Db -v ON_ERROR_STOP=1 -c "SELECT current_database() AS database, current_user AS db_user;"
docker compose exec -T postgres psql -U $User -d $Db -v ON_ERROR_STOP=1 -c "SELECT 'flights' AS kind, source, COUNT(*) FROM flights GROUP BY source UNION ALL SELECT 'hotels', source, COUNT(*) FROM hotels GROUP BY source UNION ALL SELECT 'cars', source, COUNT(*) FROM cars GROUP BY source ORDER BY kind, source;"
docker compose exec -T postgres psql -U $User -d $Db -v ON_ERROR_STOP=1 -c "SELECT id, source, kind, status, items_found, started_at, finished_at FROM scrape_runs ORDER BY id DESC LIMIT 10;"
docker compose exec -T postgres psql -U $User -d $Db -v ON_ERROR_STOP=1 -c "SELECT id, source, kind, captured_at, snapshot_path, html_sha256 FROM scrape_snapshots ORDER BY captured_at DESC LIMIT 10;"
