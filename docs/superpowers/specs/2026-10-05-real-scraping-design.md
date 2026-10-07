# WanderSync: migración a ingesta 100% basada en scraping real

**Fecha:** 2026-10-05  
**Estado:** Diseño aprobado en conversación; pendiente de revisión formal del documento antes de implementación.  
**Base:** `WanderSync_Travel_Solutions_DASK_MODULE_FIXED.zip`

## 1. Objetivo

Reemplazar por completo la fuente mock actual de WanderSync por un pipeline de adquisición basado en **scraping real de páginas públicas externas**, preservando la arquitectura que ya funciona: Docker Compose, PostgreSQL, Redis, microservicios, GraphQL, SAGA, Dask, Prefect, frontend y controles de seguridad.

El resultado final debe cumplir estas reglas:

1. Ningún dato turístico visible al usuario se genera artificialmente.
2. Vuelos, hoteles y vehículos se originan en HTML real obtenido de fuentes públicas externas.
3. Playwright se usa para renderizar páginas cuando sea necesario y guardar el DOM final.
4. El HTML capturado se guarda como snapshot y se procesa offline.
5. Dask ejecuta trabajo distribuido real sobre adquisición/procesamiento/normalización/persistencia, manteniendo la adquisición externa con baja concurrencia.
6. Prefect orquesta el pipeline, registra estados y aplica retries/backoff.
7. PostgreSQL conserva datos normalizados y trazabilidad de su procedencia.
8. GraphQL y el frontend consultan exclusivamente PostgreSQL/microservicios; una búsqueda del usuario nunca dispara directamente un navegador externo.
9. Si una fuente es bloqueada o falla, WanderSync reutiliza únicamente snapshots reales previos dentro de la política de antigüedad. Nunca genera un fallback mock.
10. No se implementan técnicas de evasión anti-bot: sin rotación de proxies para eludir bloqueos, sin CAPTCHA solving, sin fingerprint spoofing, sin parcheo de `navigator.webdriver` y sin automatización de login privado.

## 2. Alcance y componentes conservados

### Se conservan funcionalmente

- `backend/gateway/`
- `backend/flight_service/`
- `backend/hotel_service/`
- `backend/car_service/`
- `backend/order_service/`
- `backend/common/`
- `frontend/`
- Redis y sesiones server-side
- Argon2id
- Rate limiting
- SAGA orquestada y compensaciones
- PostgreSQL como persistencia principal
- Prefect Server/UI
- Dask Scheduler + 2 Workers
- Adminer

### Se sustituyen o amplían

- `backend/provider_service/`: se elimina del flujo de producción y de Docker Compose.
- `ingestion/flow.py`: deja de consumir JSON mock y pasa a orquestar captura, snapshots, parseo, normalización y persistencia.
- `ingestion/runner.py`: conserva la ejecución recurrente, pero usa la política nueva de scraping/caché.
- `ingestion/Dockerfile`: incorpora Playwright/Chromium y dependencias de parseo.
- `ingestion/requirements.txt`: incorpora Playwright, BeautifulSoup/lxml y utilidades necesarias.
- `infra/postgres/init.sql`: amplía el esquema para trazabilidad, snapshots/runs y catálogo scrapeado.
- Servicios de catálogo: dejan de depender de inventario artificial y consultan ofertas scrapeadas activas.
- SAGA: reserva y compensa **holds internos** vinculados a ofertas scrapeadas; no simula decrementos de inventario externo que la fuente no publica.

## 3. Arquitectura objetivo

```text
                          INTERNET
                              │
               ┌──────────────┼──────────────┐
               │              │              │
          Fuente vuelos   Fuente hoteles  Fuente autos
               │              │              │
               └──────────────┼──────────────┘
                              ▼
                    Source Adapter Registry
                              │
                              ▼
                     Cache / Snapshot Policy
                      ┌───────┴────────┐
                      │                │
                 snapshot válido   necesita captura
                      │                │
                      │                ▼
                      │       Dask acquisition task
                      │                │
                      │          Playwright/Chromium
                      │                │
                      │          DOM renderizado
                      │                │
                      │          snapshot HTML
                      └───────┬────────┘
                              ▼
                         Dask workers
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
               parse        clean       normalize
                 └────────────┼────────────┘
                              ▼
                           UPSERT
                              │
                              ▼
                         PostgreSQL
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
       Flight Service    Hotel Service     Car Service
             └────────────────┼────────────────┘
                              ▼
                       GraphQL Gateway
                              │
                              ▼
                           Frontend

                 Prefect orquesta todo el pipeline
```

## 4. Selección de fuentes reales

El sistema debe habilitar al menos **una fuente pública real por categoría**:

- vuelos;
- hoteles;
- vehículos.

La selección concreta se implementará mediante adaptadores separados y debe cumplir todos estos criterios antes de habilitarse:

1. URL pública accesible sin autenticación.
2. Contenido turístico visible en HTML/DOM renderizado.
3. No requiere CAPTCHA para el flujo normal de consulta elegido.
4. La página puede consultarse a baja frecuencia sin técnicas de evasión.
5. La estructura permite extraer como mínimo los campos obligatorios del modelo correspondiente.
6. Las tres fuentes elegidas deben permitir construir al menos un caso común de demostración, por ejemplo `BOG -> MDE` + hotel en Medellín + auto en Medellín.
7. El adaptador registra URL, timestamp y snapshot para demostrar procedencia.

Las URLs y selectores no se reciben desde el usuario final. Se definen en el registro interno de fuentes y/o variables de entorno controladas por el operador, evitando SSRF.

## 5. Estructura nueva de ingesta

```text
ingestion/
├── flow.py
├── runner.py
├── requirements.txt
├── Dockerfile
│
├── collectors/
│   ├── __init__.py
│   ├── base.py
│   └── playwright_collector.py
│
├── sources/
│   ├── __init__.py
│   ├── registry.py
│   ├── flights_<source>.py
│   ├── hotels_<source>.py
│   └── cars_<source>.py
│
├── parsers/
│   ├── __init__.py
│   ├── flights.py
│   ├── hotels.py
│   └── cars.py
│
├── snapshots/
│   ├── __init__.py
│   ├── manager.py
│   └── metadata.py
│
├── policies/
│   ├── __init__.py
│   ├── cache.py
│   ├── pacing.py
│   ├── robots.py
│   └── retry.py
│
└── normalization/
    ├── __init__.py
    ├── flights.py
    ├── hotels.py
    └── cars.py
```

Cada módulo tiene una responsabilidad única.

## 6. Contrato de un Source Adapter

Cada adaptador debe exponer una interfaz equivalente a:

```python
class SourceAdapter:
    name: str
    kind: str
    allowed_hosts: set[str]

    def build_requests(self) -> list[ScrapeRequest]: ...
    def ready_selector(self, request: ScrapeRequest) -> str: ...
    def parse(self, html: str, metadata: SnapshotMetadata) -> list[dict]: ...
```

Un `ScrapeRequest` contiene solo datos controlados por el sistema:

- URL;
- fuente;
- categoría;
- ciudad/origen/destino/fecha cuando corresponda;
- selector de preparación;
- query hash.

Nunca acepta una URL arbitraria enviada desde GraphQL o el frontend.

## 7. Browser Collector

`playwright_collector.py` será responsable únicamente de capturar HTML.

Flujo:

1. validar host contra allowlist;
2. comprobar política `robots.txt` de la fuente;
3. aplicar pacing y semáforo por fuente;
4. abrir Chromium headless;
5. `page.goto(..., wait_until="domcontentloaded")`;
6. esperar un selector definido por el adapter;
7. comprobar respuesta HTTP y detectar 403/429;
8. obtener `page.content()`;
9. guardar snapshot + metadata;
10. cerrar contexto/browser.

No parsea precios ni modelos de negocio.

## 8. Snapshots y caché

### Volumen Docker

```text
scrape_snapshots:/data/snapshots
```

Compartido por:

- `ingestion-runner`;
- `dask-worker-1`;
- `dask-worker-2`.

### Estructura

```text
/data/snapshots/
├── flights/<source>/<query_hash>/<timestamp>.html
├── flights/<source>/<query_hash>/<timestamp>.json
├── hotels/<source>/<query_hash>/<timestamp>.html
└── cars/<source>/<query_hash>/<timestamp>.html
```

### Metadata mínima

```json
{
  "source": "source_name",
  "kind": "flights",
  "source_url": "https://...",
  "query_hash": "...",
  "captured_at": "2026-10-05T21:00:00Z",
  "http_status": 200,
  "status": "SUCCESS"
}
```

### Política inicial

```env
SCRAPE_CACHE_MINUTES=30
SCRAPE_STALE_MAX_HOURS=24
SCRAPE_MIN_INTERVAL_SECONDS=90
SCRAPE_MAX_INTERVAL_SECONDS=180
SCRAPE_MAX_CONCURRENCY_PER_SOURCE=1
SCRAPE_NAVIGATION_TIMEOUT_SECONDS=45
SCRAPE_RETRY_LIMIT=2
```

- Snapshot <= 30 min: `CACHED`, no navegación.
- Snapshot > 30 min: intentar captura nueva.
- Captura falla y existe snapshot real <= 24 h: usarlo como `STALE_FALLBACK`.
- Sin snapshot real aceptable: `SOURCE_UNAVAILABLE`.
- Nunca producir datos sintéticos.

## 9. Uso de Dask

Dask debe seguir siendo funcionalmente demostrable, no decorativo.

### Adquisición

La captura real se ejecutará como tarea Dask, pero protegida por concurrencia máxima 1 por fuente. No se crean decenas de navegadores en paralelo.

### Procesamiento

Después de tener un snapshot, Dask puede distribuir:

```text
snapshot
   │
   ├── parse partition A
   ├── parse partition B
   ├── normalize partition A
   ├── normalize partition B
   └── persist partitions
```

Los Workers deben usar exactamente la misma imagen y módulos Python que scheduler/runner para evitar diferencias de serialización como el fallo previo `ModuleNotFoundError: flow`.

## 10. Prefect

El flow final debe exponer tareas visibles con nombres claros:

```text
WanderSync real scraping ingestion
├── collect flights
├── parse flights
├── normalize flights
├── persist flights
├── collect hotels
├── parse hotels
├── normalize hotels
├── persist hotels
├── collect cars
├── parse cars
├── normalize cars
└── persist cars
```

Prefect conserva:

- retries;
- retry delay/backoff;
- estado del flow;
- logs;
- observabilidad de errores;
- periodicidad.

Una falla en una fuente debe registrarse sin sustituirla por datos mock.

## 11. Modelo de datos scrapeado

### Flights

Campos principales:

```text
id                 TEXT PK (hash estable de fuente + identidad de oferta)
source             TEXT NOT NULL
source_url         TEXT NOT NULL
airline            TEXT
origin             TEXT NOT NULL
destination        TEXT NOT NULL
travel_date        DATE
departure_at       TIMESTAMPTZ NULL
arrival_at         TIMESTAMPTZ NULL
price              NUMERIC NULL
currency           TEXT NOT NULL
source_available   BOOLEAN NULL
snapshot_id        BIGINT NULL
scraped_at         TIMESTAMPTZ NOT NULL
last_seen_at       TIMESTAMPTZ NOT NULL
active             BOOLEAN NOT NULL DEFAULT TRUE
```

No se inventa hora de salida/llegada si la fuente no la publica.

### Hotels

```text
id
source
source_url
name
city
nightly_price
currency
rating NULL
source_available NULL
snapshot_id
scraped_at
last_seen_at
active
```

No se inventa rating si la fuente no lo publica.

### Cars

```text
id
source
source_url
provider
model
city
daily_price
currency
category NULL
source_available NULL
snapshot_id
scraped_at
last_seen_at
active
```

### Trazabilidad

Se añaden tablas:

```text
scrape_runs
scrape_snapshots
```

`scrape_runs`:

```text
id
source
kind
query_hash
source_url
started_at
finished_at
status
snapshot_id
items_found
http_status
error_message
```

`scrape_snapshots`:

```text
id
source
kind
query_hash
source_url
captured_at
path
sha256
http_status
status
```

## 12. Migración desde el catálogo mock

Para garantizar **cero contaminación mock**:

1. crear tablas/columnas nuevas de forma idempotente;
2. eliminar del Docker Compose `provider-service` y `PROVIDER_URL`;
3. limpiar los registros de catálogo generados por el provider anterior;
4. limpiar reservas/órdenes de demo vinculadas a ese catálogo si existen;
5. conservar usuarios y configuración de seguridad;
6. ejecutar una ingesta real antes de habilitar la demo final.

Para una instalación académica limpia, el camino recomendado será recrear el volumen PostgreSQL una sola vez después de introducir el nuevo esquema. El proyecto deberá documentar claramente que `docker compose down -v` elimina los datos de desarrollo.

## 13. SAGA sin inventario falso

El modelo actual decrementa `available_seats`, `available_rooms` y `available_units`. Eso no puede representar inventario real si la fuente externa no publica cantidades exactas.

El diseño nuevo separa:

```text
CATÁLOGO SCRAPEADO
    oferta real observada

ESTADO TRANSACCIONAL WANDERSYNC
    local hold / local reservation
```

### Happy path

```text
crear order
  ↓
crear flight hold interno
  ↓
crear hotel hold interno
  ↓
crear car hold interno
  ↓
billing event
  ↓
CONFIRMED
```

### Compensación

```text
car hold falla
  ↓
cancel hotel hold
  ↓
cancel flight hold
  ↓
order CANCELLED
```

Los endpoints de reserva verifican que la oferta scrapeada existe y está activa, pero no afirman haber reservado realmente con la aerolínea/hotel/rentadora externa.

La documentación y UI deben llamar a esto **reserva demostrativa/local del paquete WanderSync**, no reserva confirmada por el proveedor externo.

## 14. Servicios y GraphQL

### Flight Service

- consulta ofertas `active = true`;
- filtra por origen/destino;
- si hay `travel_date`, puede filtrar por rango/fecha cuando la fuente lo soporte;
- crea/cancela holds internos para SAGA.

### Hotel Service

- consulta hoteles reales scrapeados por ciudad;
- crea/cancela holds internos.

### Car Service

- consulta autos reales scrapeados por ciudad;
- crea/cancela holds internos.

### GraphQL

Se mantiene como única entrada del frontend.

`travelPackages` sigue combinando vuelo + hotel + auto. Ajustes:

- acepta campos nullable de fuente;
- solo combina datos activos/frescos;
- usa precios únicamente cuando existen;
- una búsqueda sin las tres categorías devuelve lista vacía, no valores inventados;
- el frontend podrá mostrar `Fuente` y `Actualizado` para evidenciar procedencia.

## 15. Frontend

El frontend conserva su flujo principal y añade evidencia de scraping:

- fuente del vuelo/hotel/auto;
- fecha/hora de última captura;
- indicador `Datos obtenidos de fuente pública`;
- mensaje claro cuando una categoría no está temporalmente disponible;
- no inicia scraping al pulsar Buscar.

La búsqueda consulta únicamente el catálogo persistido.

## 16. Seguridad específica del scraper

Además de Argon2id, sesiones, rate limiting y supply-chain audit existentes:

1. allowlist fija de hosts por adapter;
2. no URLs arbitrarias desde frontend/GraphQL;
3. respeto a `robots.txt` configurado en la política de fuente;
4. navegación únicamente HTTP/HTTPS;
5. no autenticación privada;
6. límites de tiempo y tamaño;
7. concurrencia por fuente = 1;
8. 403/429 persistentes detienen la fuente;
9. snapshots no se exponen directamente por Nginx;
10. logs no guardan cookies/secretos;
11. navegador aislado dentro del contenedor de ingesta;
12. dependencias Playwright/BeautifulSoup incluidas en `pip-audit`.

## 17. Docker Compose

### Se elimina

```text
provider-service
PROVIDER_URL
```

### Se añade

```text
scrape_snapshots volume
variables SCRAPE_*
```

Los cuatro contenedores basados en `./ingestion` usan la misma imagen:

- dask-scheduler;
- dask-worker-1;
- dask-worker-2;
- ingestion-runner.

El Dockerfile instala Chromium una sola vez en la imagen para mantener entornos consistentes.

## 18. Comportamiento ante errores

| Situación | Comportamiento |
|---|---|
| HTTP 200 + selector encontrado | snapshot + parse + persist |
| Snapshot válido | usar caché, sin navegación |
| HTTP 429 | respetar `Retry-After` si existe, retry limitado |
| HTTP 403 | marcar fuente bloqueada; no intentar evasión |
| CAPTCHA/challenge detectado | `BLOCKED`; no resolver automáticamente |
| Timeout | retry Prefect limitado |
| Cambio HTML / selector ausente | `PARSER_ERROR` o `SOURCE_CHANGED`, conservar snapshot |
| Fuente falla + snapshot <= 24 h | `STALE_FALLBACK` usando snapshot real |
| Fuente falla + sin snapshot aceptable | `SOURCE_UNAVAILABLE` |
| Parser produce 0 filas inesperadamente | no borrar catálogo previo automáticamente; registrar alerta |
| PostgreSQL falla | tarea Prefect falla y reintenta; snapshot permanece para reprocesar |

## 19. Observabilidad y demostración

### Prefect UI

Debe permitir mostrar un flow `Completed` con tareas de captura, parseo, normalización y persistencia.

### Dask Dashboard

Debe mostrar los 2 workers y tareas reales del pipeline.

### Adminer/PostgreSQL

Se demostrarán:

```sql
SELECT source, COUNT(*) FROM flights GROUP BY source;
SELECT source, COUNT(*) FROM hotels GROUP BY source;
SELECT source, COUNT(*) FROM cars GROUP BY source;
SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 20;
```

Cada registro de catálogo debe poder rastrearse hasta `source_url` y snapshot.

## 20. Pruebas de aceptación

La migración se considera completa únicamente si pasan todas estas pruebas:

1. `docker compose config` sin errores.
2. Todos los servicios críticos levantan; `provider-service` no existe en Compose.
3. Dask registra 2 workers.
4. Prefect registra el flow real de scraping.
5. Se captura al menos un snapshot HTML real por categoría.
6. Los snapshots contienen HTML de las fuentes externas, no JSON mock.
7. `scrape_runs` registra SUCCESS/CACHED/STALE_FALLBACK según corresponda.
8. PostgreSQL contiene >0 vuelos, >0 hoteles y >0 autos obtenidos por scraping real.
9. Todos esos registros tienen `source`, `source_url`, `scraped_at` y `snapshot_id` o trazabilidad equivalente.
10. No existen filas con `source = mock`, `provider-service` ni IDs generados por el proveedor anterior.
11. Segunda ejecución dentro de 30 min reutiliza caché sin nueva navegación externa.
12. Simular fuente caída demuestra uso de snapshot real previo, no datos sintéticos.
13. GraphQL devuelve datos provenientes del catálogo scrapeado.
14. Existe al menos un caso común de demostración con vuelo + hotel + auto para el mismo destino.
15. Frontend muestra al menos un paquete construido exclusivamente con datos scrapeados.
16. SAGA happy path crea holds internos y orden CONFIRMED.
17. SAGA con fallo simulado ejecuta compensaciones y deja orden CANCELLED.
18. Rate limiting, Argon2id y Session Fixation continúan pasando.
19. `pip-audit` y `npm audit` se ejecutan y guardan evidencia.
20. El script de verificación estática comprueba ausencia de fallback mock y presencia de módulos de scraping/snapshots.

## 21. Evidencia de que los datos no son mock

La demo debe poder tomar un registro y recorrer esta cadena:

```text
Frontend
  ↓
GraphQL object
  ↓
PostgreSQL row
  ↓
source_url + snapshot_id
  ↓
scrape_snapshots.path
  ↓
archivo .html capturado
  ↓
contenido visible de la página pública real
```

Ese recorrido es la prueba principal de procedencia.

## 22. Fuera de alcance

No se implementará:

- bypass de CAPTCHA;
- stealth plugins destinados a ocultar automatización;
- rotación de IPs/proxies para evadir rate limits;
- scraping autenticado de cuentas personales;
- checkout/pago real en sitios externos;
- reserva real contra proveedores externos;
- extracción de información no pública;
- scraping disparado directamente por cada usuario.

## 23. Criterio de éxito final

WanderSync será aceptado como migrado cuando pueda demostrarse en vivo:

```text
página pública real
      ↓
Playwright
      ↓
snapshot HTML
      ↓
Dask parse/normalize
      ↓
Prefect SUCCESS
      ↓
PostgreSQL con trazabilidad
      ↓
GraphQL
      ↓
Frontend
      ↓
SAGA local sobre ofertas reales scrapeadas
```

sin que ningún dato turístico utilizado en la demostración provenga del antiguo provider mock.
