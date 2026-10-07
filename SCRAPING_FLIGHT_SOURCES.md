# Fuentes de vuelos y evidencia de scraping

## Objetivo

La versión actual prioriza **evidencia demostrable de scraping real**. El pipeline de vuelos usa dos páginas públicas que exponen una tabla estructurada con los campos `Desde`, `Hasta`, `Tipo de vuelo`, `Fecha` y `Precio`.

## Fuentes activas

| Source | URL configurada | Ruta observada | Datos usados |
|---|---|---|---|
| `clicair` | `https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin` | BOG → EOH | origen, destino, tipo, fecha, precio COP |
| `satena` | `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-medellin` | BOG → EOH | origen, destino, tipo, fecha, precio COP |

Solo se persisten filas **Solo ida** porque el esquema actual de `flights` representa una oferta de un trayecto y no tiene un campo `trip_type`. Las filas de ida y vuelta siguen estando presentes en el snapshot HTML para estudio, pero no se mezclan con las ofertas persistidas.

`wingo` permanece registrado como adaptador experimental y puede habilitarse manualmente mediante `SCRAPE_ENABLED_SOURCES`, pero no está activo por defecto debido a challenges observados durante las pruebas reales.

## Ejecutar una captura

```bash
docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python -m ingestion.runner
```

## Ver ejecuciones

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c \
"SELECT id,source,kind,status,items_found,error_message FROM scrape_runs ORDER BY id DESC LIMIT 30;"
```

## Comparar CLIC y SATENA

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c \
"SELECT source,airline,origin,destination,COUNT(*) offers,MIN(price) min_price,ROUND(AVG(price),2) avg_price,MAX(price) max_price,MIN(travel_date) first_date,MAX(travel_date) last_date FROM flights WHERE active=TRUE GROUP BY source,airline,origin,destination ORDER BY source;"
```

## Trazabilidad hasta el HTML

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c \
"SELECT id,source,airline,travel_date,price,source_url,snapshot_id,scraped_at FROM flights WHERE active=TRUE ORDER BY source,travel_date LIMIT 30;"
```

```bash
docker compose exec ingestion-runner find /data/snapshots/flights -type f | sort
```

Cada oferta persistida apunta a `snapshot_id`; `scrape_snapshots` permite recuperar el `snapshot_path`, URL, fecha y hash SHA-256.

## Estudio reproducible

En el host del proyecto:

```bash
docker compose exec -T postgres psql -U wandersync -d wandersync < scripts/scraping_study.sql
```

El reporte compara estados de las fuentes, volumen de ofertas, rangos de precios, fechas observadas y snapshots recientes. Los resultados cambian según lo que las páginas públicas publiquen en el momento de la captura.

## Interpretación de estados

- `SUCCESS`: se creó un snapshot nuevo desde la página pública.
- `CACHED`: se reutilizó un snapshot real fresco.
- `STALE_FALLBACK`: la fuente falló, pero existía un snapshot real todavía aceptable.
- `SOURCE_UNAVAILABLE`: no se pudo adquirir la fuente y no había fallback real aceptable.
- `SOURCE_CHANGED` / `PARSER_ERROR`: el HTML ya no coincide con el contrato esperado.

WanderSync no intenta evadir CAPTCHA, 403, robots.txt u otras protecciones. El objetivo académico es capturar datos públicos de forma controlada y trazable.
