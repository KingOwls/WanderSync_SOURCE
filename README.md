# WanderSync Travel Solutions

WanderSync es una plataforma académica de empaquetamiento turístico dinámico para el **Parcial Práctico del Segundo Corte de Patrones Arquitectónicos Avanzados**. Integra scraping web real de información turística pública, procesamiento distribuido con Dask, orquestación con Prefect, PostgreSQL, microservicios FastAPI, Gateway GraphQL, SAGA y un frontend React.

## Qué cambió en esta versión

Los datos turísticos **no se generan localmente**. La capa de ingesta navega fuentes públicas reales con Playwright, captura el HTML renderizado, conserva un snapshot trazable, lo parsea offline y persiste únicamente los campos observados en la fuente. No existe fallback a datos turísticos sintéticos.

Fuentes configuradas inicialmente:

| Categoría | Fuente | URL pública base |
|---|---|---|
| Vuelos | CLIC | `https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin` |
| Vuelos | SATENA | `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-medellin` |
| Hoteles | GHL Portón Medellín | `https://www.ghlhoteles.com/es/hoteles/colombia/medellin/ghl-porton-medellin/` |
| Vehículos | Alkilautos / National Medellín | `https://alkilautos.com/alquiler-carros-medellin/ciudad/national/` |

Las fuentes externas pueden cambiar su HTML, disponibilidad o reglas de acceso. WanderSync respeta `robots.txt`, limita la adquisición a una navegación simultánea por fuente, usa caché y snapshots, y **no intenta superar CAPTCHAs, 403, 429 persistentes ni otros controles anti-bot**.

## Arquitectura resumida

```text
Fuentes web públicas
        │
        ▼
Playwright Collector
        │
        ▼
HTML renderizado ──► Snapshot + metadata
        │
        ▼
Prefect ──► Dask Scheduler ──► 2 Workers
        │                         │
        └──────── parse / normalize / persist
                                  │
                                  ▼
                             PostgreSQL
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
                 Flights        Hotels         Cars
                    └─────────────┼─────────────┘
                                  ▼
                           GraphQL Gateway
                                  │
                                  ▼
                                React

Reserva local: React → GraphQL → Order Service → SAGA → local holds
```

## Componentes

- **Frontend:** React + Vite servido por Nginx.
- **Gateway:** FastAPI + Strawberry GraphQL. El navegador solo consume `/graphql`.
- **Microservicios:** Flight, Hotel, Car y Order/Billing.
- **SAGA:** orquesta holds locales y compensaciones en orden inverso.
- **PostgreSQL:** catálogo scrapeado, procedencia, usuarios, holds, órdenes, billing y `saga_events`.
- **Redis:** sesiones server-side y rate limiting.
- **Playwright:** adquisición controlada de HTML renderizado.
- **BeautifulSoup:** parsing offline de snapshots.
- **Dask:** ejecución distribuida de adquisición/procesamiento/persistencia.
- **Prefect:** orquestación, retries y observabilidad.
- **Adminer:** inspección visual de PostgreSQL.

> **Límite funcional deliberado:** WanderSync **no realiza reservas en los proveedores externos**. La demostración transaccional usa un **WanderSync Local Hold** asociado a una oferta scrapeada activa. Esto demuestra SAGA sin afirmar disponibilidad ni modificar inventario del sitio externo.

## Inicio rápido

Requiere Docker Engine/Desktop con Docker Compose y acceso a Internet para la primera adquisición real.

```bash
cp .env.example .env
docker compose up --build
```

PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Interfaces:

| Interfaz | URL |
|---|---|
| Frontend | http://localhost:8080 |
| GraphQL / GraphiQL | http://localhost:8000/graphql |
| Prefect UI | http://localhost:4200 |
| Dask Dashboard | http://localhost:8787/status |
| Adminer | http://localhost:8081 |

La primera ejecución puede tardar porque la imagen de ingesta incluye Chromium y las fuentes externas deben ser visitadas de forma controlada.

## Ingesta real manual

```bash
docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python runner.py
```

Flujo esperado en Prefect: `WanderSync real scraping ingestion`, con etapas visibles `collect`, `parse`, `normalize` y `persist` para vuelos, hoteles y vehículos.

Para revisar la trazabilidad:

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c \
"SELECT source,kind,status,items_found,snapshot_id,finished_at FROM scrape_runs ORDER BY id DESC LIMIT 15;"
```

Y los snapshots reales:

```bash
docker compose exec ingestion-runner find /data/snapshots -type f -maxdepth 5 | sort | tail -30
```

## Política de adquisición

Valores por defecto en `.env.example`:

```env
SCRAPE_CACHE_MINUTES=30
SCRAPE_STALE_MAX_HOURS=24
SCRAPE_MIN_INTERVAL_SECONDS=90
SCRAPE_MAX_INTERVAL_SECONDS=180
SCRAPE_MAX_CONCURRENCY_PER_SOURCE=1
SCRAPE_NAVIGATION_TIMEOUT_SECONDS=45
SCRAPE_RETRY_LIMIT=2
```

Si existe un snapshot real de menos de 30 minutos, se reutiliza. Si la fuente falla y existe un snapshot real de hasta 24 horas, puede utilizarse como `STALE_FALLBACK`. Si no existe snapshot aceptable, la fuente queda `SOURCE_UNAVAILABLE`; nunca se inventan ofertas.

## Demostración SAGA

1. Espere una ingesta real exitosa.
2. Registre un usuario e inicie sesión.
3. Seleccione una combinación que el frontend obtenga del catálogo real.
4. Pulse **Reservar** para el happy path.
5. Consulte `saga_events`: Flight → Hotel → Car → Billing debe terminar en `CONFIRMED`.
6. Use **Demo falla auto** para provocar una falla académica controlada.
7. Verifique compensaciones inversas y orden `CANCELLED`.

El estado SAGA es interno. No se envían operaciones de reserva a CLIC, SATENA, GHL ni Alkilautos.

## Seguridad

- Contraseñas con Argon2id.
- SID preautenticado eliminado y rotado tras login para mitigar Session Fixation.
- Cookies `HttpOnly`, `SameSite=Lax`, `Secure` configurable.
- Rate limiting en registro/login/checkout/payment mediante Redis.
- URLs de scraping restringidas a allowlists por adaptador.
- Rechazo de localhost, IP privada/reservada y resolución DNS no pública para reducir SSRF.
- `robots.txt` consultado antes de navegar.
- CAPTCHA/challenge detectado implica detención, no bypass.
- Auditoría reproducible de dependencias Python y npm.

Auditoría:

```bash
python -m pip install pip-audit
./security/audit.sh
```

PowerShell:

```powershell
python -m pip install pip-audit
./security/audit.ps1
```

## Verificación

Pruebas estáticas/unitarias:

```bash
pytest -q
python scripts/verify_project.py
```

Con Docker ya levantado:

```bash
python scripts/demo_validation.py
```

La matriz completa está en `REAL_SCRAPING_ACCEPTANCE.md`. Distingue resultados que pueden validarse estáticamente de evidencia que **debe** obtenerse en un host Docker con Internet.

## Estructura principal

```text
WanderSync_HARDENED/
├── backend/
│   ├── gateway/
│   ├── flight_service/
│   ├── hotel_service/
│   ├── car_service/
│   ├── order_service/
│   └── common/
├── ingestion/
│   ├── collectors/
│   ├── sources/
│   ├── parsers/
│   ├── normalization/
│   ├── snapshots/
│   ├── policies/
│   ├── flow.py
│   └── runner.py
├── frontend/
├── infra/postgres/init.sql
├── docs/
├── security/
├── scripts/
├── REAL_SCRAPING_ACCEPTANCE.md
└── docker-compose.yml
```

## Diagnóstico rápido

Si Dask muestra `No module named flow`, reconstruya los cuatro contenedores de ingesta. Todos usan el mismo contexto `./ingestion` y `PYTHONPATH=/app`:

```bash
docker compose build --no-cache dask-scheduler dask-worker-1 dask-worker-2 ingestion-runner
docker compose up -d --force-recreate dask-scheduler dask-worker-1 dask-worker-2 ingestion-runner
```

Si una fuente aparece como `SOURCE_UNAVAILABLE`, revise primero `scrape_runs`, logs del runner/workers y `robots.txt`. No aumente concurrencia ni implemente bypasses. Un cambio del HTML debe corregirse actualizando el adaptador/parser y sus pruebas.

Si cambió el esquema y el volumen académico puede descartarse:

```bash
docker compose down -v
docker compose up --build
```

`down -v` elimina datos y debe usarse únicamente cuando esa pérdida sea aceptable.

## Scraping runtime hotfix

Para la demostración de scraping consulta `SCRAPING_FLIGHT_SOURCES.md`. CLIC y SATENA son las fuentes de vuelos habilitadas por defecto; Wingo se conserva como adaptador experimental desactivado por sus challenges. `SCRAPING_RUNTIME_HOTFIX.md` conserva el historial del diagnóstico anterior.

## Ida y vuelta flexible

WanderSync ahora scrapea CLIC y SATENA en `BOG → EOH` y `EOH → BOG`. La consulta `travelAvailability` ofrece hasta 8 fechas reales de salida y 8 de regreso, con recomendaciones de 1–14 noches. Medellín permanece como `MDE` en la interfaz y el Gateway resuelve `[MDE, EOH]` al consultar vuelos. Los paquetes incluyen `outboundFlight`, `returnFlight`, hotel y auto; el checkout SAGA sostiene ambos vuelos con WanderSync Local Hold y **no realiza reservas en los proveedores externos**.
