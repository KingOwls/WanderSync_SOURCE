# WanderSync - Persistencia PostgreSQL para catálogo scrapeado

## Problema resuelto

La inicialización de la imagen oficial de PostgreSQL solo ejecuta `/docker-entrypoint-initdb.d` sobre un volumen vacío. WanderSync conserva `db-bootstrap`, que aplica `infra/postgres/init.sql` de forma idempotente en cada despliegue para que un volumen existente reciba el esquema actual.

## Esquema actual

Además de usuarios, órdenes y SAGA, se almacenan:

- `flights`, `hotels`, `cars`: ofertas observadas en fuentes públicas;
- `scrape_snapshots`: procedencia del HTML capturado;
- `scrape_runs`: historial de adquisición/procesamiento.

No existe un número fijo esperado de vuelos, hoteles o vehículos. El conteo depende del contenido real publicado por CLIC, SATENA, GHL y Alkilautos en el instante de la captura.

## Evidencia

```bash
./scripts/db_check.sh
```

```sql
SELECT source, COUNT(*) FROM flights WHERE active GROUP BY source;
SELECT source, COUNT(*) FROM hotels WHERE active GROUP BY source;
SELECT source, COUNT(*) FROM cars WHERE active GROUP BY source;
SELECT source,kind,status,items_found,snapshot_id
FROM scrape_runs ORDER BY id DESC LIMIT 20;
```

Cada oferta demostrada debe poder rastrearse mediante `snapshot_id` a un registro de `scrape_snapshots` y a un archivo real del volumen `/data/snapshots`.

## Reinicio de desarrollo

Si un volumen muy antiguo necesita descartarse:

```bash
docker compose down -v
cp .env.example .env
docker compose up --build
```

**Advertencia:** `down -v` destruye datos locales.
