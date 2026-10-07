# WanderSync - Flight HTTP Collection Hotfix

## Problema observado en ejecución real

CLIC y SATENA alcanzaban a renderizar una tabla (`ready_selector=table`) dentro de Chromium, pero el detector global de challenge encontraba cadenas de protección dentro del DOM/scripts y clasificaba ambas páginas como `SourceBlockedError`. Esto impedía guardar snapshots aun cuando el contenido comercial público estaba disponible.

## Decisión

Las páginas públicas de CLIC y SATENA ya entregan en el HTML inicial una tabla con `Desde`, `Hasta`, `Tipo de vuelo`, `Fecha` y `Precio`. Para esas dos fuentes se usa adquisición HTTP directa y respetuosa, manteniendo:

- consulta de `robots.txt`;
- `User-Agent` académico;
- allowlist de hosts y validación de redirects;
- validación DNS/IP pública;
- pacing por fuente;
- retries acotados para errores transitorios;
- caché y stale fallback únicamente a snapshots reales;
- snapshot HTML + metadata + SHA-256;
- parser offline y normalización posterior con Dask.

GHL y Alkilautos siguen usando Playwright porque su adquisición dinámica ya fue validada en ejecución real.

## Matriz de adquisición

| Fuente | Tipo | Transporte |
| --- | --- | --- |
| CLIC | flights | HTTP |
| SATENA | flights | HTTP |
| GHL Portón Medellín | hotels | Playwright |
| Alkilautos National Medellín | cars | Playwright |
| Wingo | flights experimental | Playwright, desactivado por defecto |

## Comprobación en Docker

```bash
docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python -m ingestion.runner
```

Después:

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c "SELECT id,source,kind,status,items_found,error_message FROM scrape_runs ORDER BY id DESC LIMIT 30;"
```

Y para comprobar snapshots:

```bash
docker compose exec ingestion-runner find /data/snapshots -type f | sort
```

El resultado esperado para las fuentes de vuelos es que aparezcan snapshots bajo `flights/clicair/` y `flights/satena/`. Si un servidor responde 403/429 o robots.txt no permite la ruta, WanderSync no intenta evadir la protección y registra la fuente como no disponible.
