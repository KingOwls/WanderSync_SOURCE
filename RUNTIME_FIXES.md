# Correcciones y diagnóstico de ejecución

## CLI moderna de Dask

Use `dask scheduler` y `dask worker`; no los ejecutables heredados. El Compose actual ya contiene la forma correcta.

## Dashboard Dask y Bokeh

`ingestion/requirements.txt` declara `bokeh>=3.1,<4`. Si `:8787/status` pide Bokeh, reconstruya la imagen:

```bash
docker compose build --no-cache dask-scheduler dask-worker-1 dask-worker-2 ingestion-runner
docker compose up -d --force-recreate dask-scheduler dask-worker-1 dask-worker-2 ingestion-runner
```

## `ModuleNotFoundError: flow`

Todos los procesos de ingesta deben compartir la misma imagen y `PYTHONPATH=/app`. Compruebe:

```bash
docker compose exec dask-scheduler python -c "import ingestion.flow as flow; print(flow.__file__)"
docker compose exec dask-worker-1 python -c "import ingestion.flow as flow; print(flow.__file__)"
```

Ambos deben resolver `/app/ingestion/flow.py`.

## Fuente `SOURCE_UNAVAILABLE`

Revise:

```bash
docker compose logs --tail=200 ingestion-runner dask-worker-1 dask-worker-2
```

Y PostgreSQL:

```sql
SELECT source,kind,status,error_message,snapshot_id
FROM scrape_runs ORDER BY id DESC LIMIT 20;
```

Causas válidas: robots no permitido, 403/429 persistente, CAPTCHA/challenge, DNS/red, timeout o cambio del selector/HTML. No intente superar esas protecciones. Corrija el adaptador si cambió el DOM o espere/restaure conectividad.

## Snapshot compartido

```bash
docker compose exec ingestion-runner find /data/snapshots -type f | sort | tail -40
```

Si runner ve archivos y un worker no, revise el montaje `scrape_snapshots:/data/snapshots` en Compose.

## PostgreSQL

`db-bootstrap` aplica el esquema de forma idempotente. Compruebe:

```bash
./scripts/db_check.sh
```

Para una migración académica limpia, solo si puede perder datos locales:

```bash
docker compose down -v
docker compose up --build
```
