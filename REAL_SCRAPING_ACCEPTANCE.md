# WanderSync Real Scraping - Matriz de Aceptación

Este documento contiene **20 criterios** de aceptación. `STATIC PASS` significa validado sin Docker contra código/pruebas. `TO VERIFY ON DOCKER HOST` significa que requiere contenedores, Chromium, red externa o UI y no debe marcarse como aprobado hasta ejecutarlo en el equipo de presentación.

| # | Criterio | Evidencia/comando | Resultado de generación |
|---:|---|---|---|
| 1 | No existe servicio runtime generador de ofertas | `python scripts/verify_project.py` | STATIC PASS |
| 2 | Compose no usa `PROVIDER_URL` | verificador estático | STATIC PASS |
| 3 | Playwright y Chromium forman parte de la imagen de ingesta | Dockerfile + requirements | STATIC PASS |
| 4 | Existen adaptadores CLIC/SATENA/GHL/Alkilautos y Wingo experimental | `ingestion/sources/` | STATIC PASS |
| 5 | URLs externas están allowlisted | tests de seguridad | STATIC PASS |
| 6 | localhost/IP privada/DNS no global se rechazan | `pytest tests/test_scrape_security.py` | STATIC PASS |
| 7 | Se consulta robots y no se bypassa CAPTCHA | collector + tests | STATIC PASS |
| 8 | Cache real 30 min y stale real máximo 24 h | `pytest tests/test_scrape_flow.py` | STATIC PASS |
| 9 | Parser vacío no borra el catálogo previo | `pytest tests/test_scrape_flow.py` | STATIC PASS |
| 10 | Catálogo guarda procedencia | esquema + tests persistencia | STATIC PASS |
| 11 | SAGA no muta inventario externo | `pytest tests/test_local_holds.py` | STATIC PASS |
| 12 | Dos workers Dask aparecen registrados | dashboard / Client scheduler_info | TO VERIFY ON DOCKER HOST |
| 13 | Prefect muestra collect/parse/normalize/persist | Prefect UI | TO VERIFY ON DOCKER HOST |
| 14 | CLIC produce al menos un snapshot HTML real | `/data/snapshots/flights/clicair/...` | TO VERIFY ON DOCKER HOST |
| 15 | SATENA produce al menos un snapshot HTML real | `/data/snapshots/flights/satena/...` | TO VERIFY ON DOCKER HOST |
| 16 | GHL produce al menos un snapshot HTML real | `/data/snapshots/hotels/...` | TO VERIFY ON DOCKER HOST |
| 17 | Alkilautos produce al menos un snapshot HTML real | `/data/snapshots/cars/...` | TO VERIFY ON DOCKER HOST |
| 17 | Segunda ejecución inmediata usa `CACHED` sin nueva captura | `scrape_runs` + timestamps de snapshot | TO VERIFY ON DOCKER HOST |
| 18 | GraphQL devuelve oferta con source/sourceUrl/snapshotId/scrapedAt | GraphiQL / `demo_validation.py` | TO VERIFY ON DOCKER HOST |
| 19 | Happy path SAGA y falla compensada funcionan sobre ofertas scrapeadas | frontend + `saga_events` | TO VERIFY ON DOCKER HOST |
| 20 | Auditorías backend/ingestion/frontend se generan | `./security/audit.sh` o `.ps1` | TO VERIFY ON DOCKER HOST |

## Secuencia runtime recomendada

```bash
docker compose config
docker compose up --build -d
docker compose ps
docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python runner.py
python scripts/demo_validation.py
./security/audit.sh
```

## Dask

```bash
docker compose exec ingestion-runner python -c "from dask.distributed import Client; c=Client('tcp://dask-scheduler:8786'); print(list(c.scheduler_info()['workers'])); c.close()"
```

Debe devolver exactamente dos workers.

## Procedencia SQL

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c \
"SELECT id,source,kind,status,items_found,snapshot_id,error_message FROM scrape_runs ORDER BY id DESC LIMIT 20;"
```

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c \
"SELECT id,source,source_url,snapshot_id,scraped_at FROM flights WHERE active LIMIT 10;"
```

## Snapshots

```bash
docker compose exec ingestion-runner find /data/snapshots -type f | sort
```

Para cada categoría presentada debe existir `.html` y metadata `.json` provenientes de una navegación real.

## Estado esperado ante bloqueo

Un 403/429 persistente, CAPTCHA, challenge o cambio del DOM nunca debe producir un dato artificial. El resultado permitido es `STALE_FALLBACK` sobre un snapshot real <=24 h o `SOURCE_UNAVAILABLE`.

## Alcance de SAGA

La reserva demostrada es un **WanderSync Local Hold**. WanderSync **no realiza reservas en los proveedores externos** ni modifica inventario de CLIC, SATENA, GHL o Alkilautos.

## Limitaciones del entorno de generación

Durante la generación de este paquete no hubo Docker CLI/daemon, por lo que los criterios marcados `TO VERIFY ON DOCKER HOST` permanecen deliberadamente pendientes. Además, el intento local de `npm install` no pudo resolver `registry.npmjs.org` (`EAI_AGAIN`), por lo que el build Vite no se presenta como ejecutado aquí; el Dockerfile/frontend lo construirá en un host con conectividad. `pip-audit` tampoco estaba instalado en el entorno de generación y la auditoría formal se deja al script reproducible incluido.
