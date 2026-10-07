# Persistencia PostgreSQL y trazabilidad del scraping

## Tablas principales

### Catálogo real

- `flights`: aerolínea, origen, destino, fecha observada, precio/moneda y procedencia.
- `hotels`: hotel, tipo de habitación, ciudad, tarifa/rating cuando la fuente lo publica y procedencia.
- `cars`: proveedor, modelo, ciudad, tarifa/categoría cuando la fuente lo publica y procedencia.

No se inventan cantidades `available_*`. Si una fuente no publica un dato, se conserva como `NULL` cuando el esquema lo permite.

### Procedencia

`scrape_snapshots` conserva:

```text
id, source, kind, source_url, query_hash,
captured_at, http_status, status,
snapshot_path, html_sha256
```

`scrape_runs` conserva:

```text
id, source, kind, query_hash, source_url,
started_at, finished_at, status,
snapshot_id, items_found, http_status, error_message
```

Cada fila de catálogo incluye `source`, `source_url`, `snapshot_id`, `scraped_at` y `active`. La cadena de evidencia es:

```text
fila de catálogo → snapshot_id → scrape_snapshots → snapshot_path → HTML real
```

## Reservas locales

`flight_reservations`, `hotel_reservations` y `car_reservations` son holds internos de WanderSync. No representan ni modifican inventario de CLIC, SATENA, GHL, Alkilautos ni ningún otro proveedor externo.

`orders`, `saga_events` y `billing_events` demuestran la transacción distribuida y sus compensaciones.

## Bootstrap idempotente

`db-bootstrap` ejecuta `infra/postgres/init.sql` en cada despliegue. El script crea tablas faltantes y migra catálogos de versiones antiguas. Los registros turísticos anteriores sin procedencia verificable se eliminan durante la migración para impedir que datos sintéticos heredados se mezclen con datos scrapeados.

## Comprobación

```bash
./scripts/db_check.sh
```

PowerShell:

```powershell
./scripts/db_check.ps1
```

Conteo y fuentes:

```sql
SELECT source, COUNT(*) FROM flights WHERE active GROUP BY source;
SELECT source, COUNT(*) FROM hotels  WHERE active GROUP BY source;
SELECT source, COUNT(*) FROM cars    WHERE active GROUP BY source;
SELECT id,source,kind,status,items_found,snapshot_id
FROM scrape_runs ORDER BY id DESC LIMIT 20;
```

## Adminer

Abra `http://localhost:8081`:

- Sistema: PostgreSQL
- Servidor: `postgres`
- Usuario/base/contraseña: valores de `.env`

## Reinicio de desarrollo

Solo si es aceptable borrar datos locales:

```bash
docker compose down -v
docker compose up --build
```

`-v` elimina los volúmenes. No se necesita para una ejecución normal.
