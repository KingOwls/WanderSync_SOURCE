# WanderSync - Scraping Runtime Hotfix

Fecha: 2026-10-05

Este hotfix parte de `REAL_SCRAPING_DB_HOTFIX` y corrige tres fallos observados durante la ejecución real de Prefect.

## 1. Wingo: selector de contenido listo

**Síntoma:** `SourceChangedError: Ready selector not found: text=Desde COP`.

La página pública separa visualmente `Desde` y el valor `COP...`, por lo que `text=Desde COP` no es una señal estable del DOM renderizado.

**Cambio:** el adaptador Wingo espera `text=Comprar`, presente en las ofertas renderizadas, antes de capturar el snapshot.

## 2. Alkilautos: falso positivo de CAPTCHA

**Síntoma:** `SourceBlockedError: Challenge/CAPTCHA page detected` aun cuando la página pública contiene ofertas y `Precio por día`.

**Causa:** el detector anterior consideraba bloqueada cualquier página cuyo HTML contuviera la palabra `captcha`, incluso cuando esa referencia provenía de scripts embebidos de seguridad/login.

**Cambio:** el collector ya no bloquea por la palabra `captcha` aislada. Solo clasifica como challenge señales fuertes como `verify you are human`, `cf-chl-`, `challenge-platform`, `access denied`, `just a moment...` o `checking your browser before accessing`.

Esto no implementa bypass. Si una challenge real impide que aparezca el selector de ofertas, la adquisición sigue fallando y no se fabrican datos.

## 3. Prefect: ejecución parcial sin `UnfinishedRun` fatal

**Síntoma:** una fuente fallida dejaba tareas downstream en `NotReady`; al consultar el future final, el Flow levantaba `UnfinishedRun` y terminaba en Failed aunque otra fuente hubiera completado correctamente.

**Cambio:** el Flow conserva las cadenas concurrentes, pero captura el error del future final por fuente y lo transforma en un `SourceRunResult(status="SOURCE_UNAVAILABLE")`. Cuando PostgreSQL está disponible, reutiliza el `error_message` raíz almacenado en `scrape_runs` para no ocultar el diagnóstico bajo un `UnfinishedRun` genérico.

El resultado esperado de una ejecución parcial es conceptualmente:

```text
wingo                        SOURCE_UNAVAILABLE o SUCCESS
GHL Portón Medellín          SUCCESS/CACHED
alkilautos_national_medellin SOURCE_UNAVAILABLE o SUCCESS

Flow de Prefect              COMPLETED con resultados por fuente
```

## Validación automatizada

```bash
python -m pytest -q
python scripts/verify_project.py
```

Resultado del paquete generado:

```text
53 passed
147/147 static checks PASS
```

## Validación runtime recomendada

Después de reconstruir los contenedores:

```bash
docker compose down
docker compose build --no-cache ingestion-runner dask-scheduler dask-worker-1 dask-worker-2
docker compose up -d
```

Forzar una corrida:

```bash
docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python runner.py
```

Revisar resultados:

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c "SELECT id,source,kind,status,items_found,error_message FROM scrape_runs ORDER BY id DESC LIMIT 30;"
```

Revisar snapshots:

```bash
docker compose exec ingestion-runner find /data/snapshots -type f | sort
```

Para confirmar catálogo activo:

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c "SELECT source,COUNT(*) FROM flights WHERE active=TRUE GROUP BY source;"
docker compose exec postgres psql -U wandersync -d wandersync -c "SELECT source,COUNT(*) FROM hotels WHERE active=TRUE GROUP BY source;"
docker compose exec postgres psql -U wandersync -d wandersync -c "SELECT source,COUNT(*) FROM cars WHERE active=TRUE GROUP BY source;"
```
