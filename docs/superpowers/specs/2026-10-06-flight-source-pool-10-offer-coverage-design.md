# WanderSync Flight Source Pool + 10-Offer Coverage + Suggested Connections Design

## Estado

Diseño arquitectónico aprobado conversacionalmente para reemplazar LATAM como fuente activa, ampliar la redundancia del catálogo de vuelos con JetSMART y Wingo por HTTP público, alcanzar un objetivo de hasta 10 ofertas reales por cada dirección entre las cinco ciudades y añadir conexiones sugeridas de máximo una escala sin alterar el SAGA de paquetes directos.

Fecha: 2026-10-06

## Objetivo

Mantener WanderSync funcional sobre Bogotá, Medellín, Cali, Cartagena y Santa Marta aunque una aerolínea externa no sea scrapeable, usando un pool de fuentes públicas redundantes y un grafo de rutas derivado exclusivamente de ofertas activas reales.

La experiencia final debe permitir:

1. explorar vuelos directos reales en las 20 direcciones posibles entre Bogotá, Medellín, Cali, Cartagena y Santa Marta;
2. exponer hasta 10 ofertas reales totales por dirección, sumando las fuentes productivas y sin rellenar faltantes;
3. distinguir cobertura completa, cobertura parcial, ausencia real de ofertas e imposibilidad de verificación;
4. sugerir conexiones de máximo una escala cuando no exista una opción directa para la fecha seleccionada;
5. seleccionar únicamente fechas realmente publicadas y persistidas;
6. seguir armando paquetes únicamente con vuelos directos de ida y regreso más hotel y auto;
7. tolerar una fuente caída o bloqueada sin convertir el fallo en un error global de la aplicación.

## Restricciones no negociables

- Cero fallback mock.
- No inventar rutas, fechas, precios, disponibilidad, horarios ni aeropuertos.
- Las cinco ciudades soportadas siempre forman 20 direcciones buscables. Una URL configurada no convierte una dirección en `AVAILABLE`; la disponibilidad directa se deriva exclusivamente de `flights.active = TRUE`.
- Máximo una escala en conexiones sugeridas.
- Una conexión sugerida no se presenta como conexión garantizada porque las páginas públicas no siempre ofrecen hora exacta de salida/llegada.
- Los paquetes y el SAGA continúan usando únicamente vuelos directos.
- Cache y `STALE_FALLBACK` solo pueden reutilizar snapshots reales previos.
- No CAPTCHA bypass, fingerprint spoofing, proxies rotativos ni evasión de `robots.txt`.
- Una ruta explícitamente desautorizada por `robots.txt` se omite y no se reintenta repetidamente en la misma ejecución.
- GHL y Alkilautos no se modifican en esta fase.
- El catálogo público de una dirección expone como máximo 10 ofertas reales totales entre todas las fuentes; nunca 10 por aerolínea.
- PostgreSQL puede conservar más de 10 filas reales activas para trazabilidad y estudio. El límite de 10 pertenece al read model y a la UX, no destruye evidencia.
- Si existen menos de 10 ofertas reales, se muestran únicamente las existentes.
- Cero resultados no implica automáticamente "agotado": la aplicación distingue `NO_OFFERS` de `SOURCE_UNAVAILABLE`.
- No se afirma "se vendieron" salvo que una fuente futura publique explícitamente ese estado; la copia de UX usa lenguaje probabilístico.
- La concurrencia de adquisición queda limitada a máximo 2 rutas simultáneas por fuente.
- Prefect server y cliente deben quedar fijados a la misma versión en la imagen final.

## Pool de fuentes de vuelo

### Activas por defecto

- `clicair`: HTTP público.
- `satena`: HTTP público.
- `jetsmart`: HTTP público.
- `wingo`: HTTP público.

### Desactivada

- `latam`: `DISABLED`, motivo operativo `ROBOTS_DISALLOWED` para las rutas evaluadas en esta fase.

LATAM se conserva documentada como fuente evaluada, pero no forma parte de `SCRAPE_ENABLED_SOURCES` ni genera retries de producción.

## Estrategia de adquisición

Las cuatro fuentes activas utilizan adquisición HTTP pública cuando el HTML inicial ya contiene las ofertas. No se usa Playwright para vuelos en esta fase.

Cada request mantiene:

- allowlist de hosts;
- verificación DNS/IP;
- `robots.txt`;
- pacing;
- timeout;
- retries solo ante fallos transitorios compatibles;
- snapshots HTML + metadata;
- cache reciente;
- stale fallback real cuando corresponda.

Si `robots.txt` desautoriza una ruta, el resultado se registra como `ROBOTS_DISALLOWED`/`SOURCE_UNAVAILABLE` sin repetir el mismo error varias veces.

## Parser tabular común

CLIC, SATENA, JetSMART y Wingo se normalizan mediante un parser de tablas con alias de encabezados.

Alias mínimos:

| Campo común | Encabezados aceptados |
| --- | --- |
| origen | `Desde` |
| destino | `Hasta`, `A`, `Hacia` |
| tipo | `Tipo de vuelo`, `Tipo de tarifa` |
| fecha | `Fecha`, `Fechas` |
| precio | `Precio` |

El parser debe:

- detectar una tabla por semántica de encabezados, no por posición fija;
- extraer IATA de textos tipo `Bogotá (BOG)`;
- aceptar fechas públicas soportadas actualmente por el normalizador;
- conservar `trip_type` cuando exista;
- persistir solo ofertas con fecha concreta y precio concreto;
- ignorar resúmenes mensuales sin fecha individual;
- deduplicar por fuente/aerolínea/origen/destino/fecha/precio/tipo.

El fallback regex histórico de Wingo puede conservarse únicamente para snapshots antiguos; el flujo nuevo prioriza tablas semánticas.

## Route Registry

`ingestion/sources/flight_routes.py` sigue siendo la única fuente de URLs productivas auditables.

`RouteSpec` conserva:

```python
@dataclass(frozen=True)
class RouteSpec:
    source: str
    origin: str
    destination: str
    url: str
    acquisition_mode: str = "http"
```

### Rutas CLIC/SATENA

Se conservan las rutas multi-ciudad ya implementadas y demostradas por el proyecto actual.

### JetSMART

El registry inicial incorpora únicamente páginas públicas verificadas para cubrir huecos útiles del grafo, con prioridad en Santa Marta y Cartagena. La semilla mínima incluye páginas verificables para familias como:

- `BOG → SMR` y `SMR → BOG`;
- `MDE → SMR`;
- `CLO → SMR`;
- `CTG → BOG`;
- `CTG → MDE`;
- `CTG → CLO`;
- `MDE → CTG`.

Una dirección inversa adicional solo se configura cuando existe una URL pública verificable independiente; nunca se infiere por simetría.

### Wingo

Wingo vuelve al registry únicamente con páginas públicas que no dependan de `/Flight/`, `/api/` ni parámetros de búsqueda bloqueados. La semilla mínima prioriza familias verificables como:

- `BOG → SMR`;
- `MDE → SMR`;
- `CTG → BOG`.

Se pueden añadir más rutas públicas verificadas durante implementación sin cambiar la arquitectura.

## Objetivo de cobertura: 20 direcciones y hasta 10 ofertas

Las ciudades objetivo generan 20 direcciones ordenadas posibles:

- `BOG→MDE`, `BOG→CLO`, `BOG→CTG`, `BOG→SMR`;
- `MDE→BOG`, `MDE→CLO`, `MDE→CTG`, `MDE→SMR`;
- `CLO→BOG`, `CLO→MDE`, `CLO→CTG`, `CLO→SMR`;
- `CTG→BOG`, `CTG→MDE`, `CTG→CLO`, `CTG→SMR`;
- `SMR→BOG`, `SMR→MDE`, `SMR→CLO`, `SMR→CTG`.

El objetivo por dirección es `TARGET_OFFERS_PER_DIRECTION = 10`. Es un máximo de exposición, no una cuota artificial.

Reglas del catálogo de lectura:

1. agrupar aeropuertos por ciudad turística (`EOH` y `MDE` pertenecen a Medellín);
2. considerar solo filas `active = TRUE`;
3. deduplicar por `source + origin + destination + travel_date + price + trip_type` cuando el tipo exista;
4. ordenar de forma determinista por fecha ascendente, precio ascendente, fuente y `id`;
5. exponer como máximo 10 ofertas por dirección;
6. conservar ofertas de diferentes fuentes para la misma fecha si tienen precios diferentes;
7. no inventar filas para alcanzar diez.

El catálogo bruto de PostgreSQL puede conservar más filas activas. Esto preserva evidencia, comparaciones y provenance mientras la API mantiene el contrato de hasta diez ofertas visibles.

### Estados de disponibilidad por dirección

- `AVAILABLE`: existen 10 o más ofertas reales en el catálogo bruto y el read model expone 10.
- `PARTIAL`: existen entre 1 y 9 ofertas reales.
- `NO_OFFERS`: las fuentes aplicables se pudieron observar correctamente y produjeron cero ofertas para esa dirección/fecha de consulta.
- `SOURCE_UNAVAILABLE`: no hay suficientes observaciones sanas para afirmar ausencia de ofertas porque una o más fuentes necesarias fallaron antes de observarse.

`NO_OFFERS` y `SOURCE_UNAVAILABLE` son estados semánticamente distintos.

Baseline previo a JetSMART/Wingo, validado en runtime el 2026-10-06:

- 77 ofertas de vuelo activas reales;
- 10 rutas dirigidas;
- 5 parejas bidireccionales;
- CLIC y SATENA productivos;
- Santa Marta sin cobertura;
- Bogotá↔Cartagena sin directo.

## Ingesta multi-ruta y fallos parciales

Cada fuente procesa sus `RouteSpec` independientemente, con un semáforo de máximo 2 adquisiciones simultáneas por fuente. Dask distribuye rutas independientes entre workers, pero el límite por fuente evita convertir la ampliación de cobertura en scraping agresivo.

Reglas:

1. Una ruta capturada correctamente refresca solo esa dirección.
2. Una ruta capturada correctamente con cero ofertas desactiva las ofertas anteriores de esa dirección observada para esa fuente/ruta.
3. Una ruta que falla antes de ser observada no desactiva su último catálogo válido.
4. Una fuente puede finalizar `SUCCESS`/`CACHED`/`STALE_FALLBACK` con diagnósticos parciales si algunas rutas fallan.
5. Una fuente totalmente bloqueada por política no impide que las demás fuentes continúen.
6. La ingesta no corta destructivamente al llegar a diez: las cuatro fuentes siguen siendo observables para salud, provenance y comparación. El límite de diez se aplica en lectura.
7. Las páginas que publiquen más de cinco ofertas por ruta deben poder aportar hasta el contenido real disponible; no existe un hardcode de cinco resultados en parser o adapter.

## Grafo turístico

Las cinco ciudades siguen siendo:

| Ciudad | Código turístico | Aeropuertos de vuelo |
| --- | --- | --- |
| Bogotá | `BOG` | `BOG` |
| Medellín | `MDE` | `MDE`, `EOH` |
| Cali | `CLO` | `CLO` |
| Cartagena | `CTG` | `CTG` |
| Santa Marta | `SMR` | `SMR` |

`MDE` y `EOH` se consolidan bajo Medellín solo en lectura. Los registros `flights` conservan el aeropuerto real scrapeado.

`travelNetwork.cities` expone siempre las cinco ciudades soportadas y `travelNetwork.routes` expone las 20 direcciones buscables con su cobertura directa real. Una dirección con cero filas activas sigue siendo buscable y aparece con `NO_OFFERS` o `SOURCE_UNAVAILABLE`; no se presenta como vuelo existente.

## Connection Engine

Se añade una unidad pura en el gateway, por ejemplo `backend/gateway/flight_connections.py`.

### Entrada

- ofertas activas directas para `origin → destination` en una fecha concreta;
- si no existen directas, ofertas activas de todas las rutas salientes del origen para esa fecha;
- ofertas activas desde cada posible ciudad intermedia al destino para la misma fecha.

### Reglas

- buscar directos primero;
- solo buscar conexiones si no hay directos para esa fecha;
- máximo una escala;
- ambos legs deben tener la misma `travel_date` solicitada;
- el aeropuerto intermedio puede resolverse a ciudad turística, pero cada leg conserva su aeropuerto real;
- no aceptar ciclos ni `origin == via == destination`;
- sumar precios solo cuando ambos legs comparten moneda `COP`;
- construir hasta 10 conexiones candidatas y exponer como máximo las 5 mejor clasificadas en la UX;
- ordenar candidatos por `total_price`, luego por ciudad intermedia, fuente e IDs de legs;
- deduplicar combinaciones equivalentes de IDs de vuelo.

### Semántica

El resultado se denomina siempre `suggested connection` / `conexión sugerida`.

La interfaz debe advertir: `Verifica los horarios exactos con las aerolíneas.`

No se afirma que la escala sea reservable o temporalmente viable porque no existe garantía de horarios en todas las fuentes.

## Flight Service

`/routes` permanece como agregado de vuelos directos activos.

`/flights` conserva filtros por múltiples aeropuertos y fecha.

No es necesario persistir conexiones como una tabla nueva. Las conexiones se calculan en lectura a partir del catálogo activo para evitar datos derivados obsoletos.

## GraphQL

Se conserva:

- `travelNetwork`;
- `travelAvailability` para paquetes directos/round-trip;
- `flightOffers`;
- `travelPackages`.

Se añaden `flightAvailability` y `flightSearch`:

```graphql
flightAvailability(
  origin: String!
  destination: String!
): FlightAvailabilityResult!

flightSearch(
  origin: String!
  destination: String!
  travelDate: String!
  limit: Int = 20
): FlightSearchResult!
```

Tipos conceptuales:

```graphql
type FlightAvailabilityResult {
  origin: String!
  destination: String!
  dates: [FlightDateOption!]!
}

type FlightDateOption {
  travelDate: String!
  directOfferCount: Int!
  connectionCandidateCount: Int!
}
```

`flightAvailability` calcula fechas exclusivamente desde ofertas directas activas o desde pares de legs reales de una escala que coinciden en la misma fecha. Devuelve como máximo 10 fechas ordenadas y nunca inventa un calendario. Esto permite buscar una dirección sin vuelo directo sin reintroducir un `input type="date"`.

```graphql
type FlightSearchResult {
  origin: String!
  destination: String!
  travelDate: String!
  status: String!
  availableCount: Int!
  sourcesChecked: Int!
  sourcesAvailable: Int!
  directOffers: [FlightOffer!]!
  connections: [SuggestedConnection!]!
}

type SuggestedConnection {
  via: String!
  stops: Int!
  totalPrice: Float!
  currency: String!
  legs: [FlightOffer!]!
  warning: String!
}
```

Reglas:

- si hay directos, `directOffers` contiene como máximo 10 ofertas seleccionadas y `connections` puede ser vacío;
- si no hay directos, GraphQL puede calcular hasta 10 candidatos y devuelve como máximo 5 conexiones;
- `status` usa `AVAILABLE`, `PARTIAL`, `NO_OFFERS` o `SOURCE_UNAVAILABLE`;
- `availableCount` refleja ofertas directas visibles para la dirección/fecha antes de recurrir a conexiones;
- `travelPackages` no consume `SuggestedConnection`;
- `flightSearch` solo recibe en UX normal una fecha procedente de `flightAvailability`; el resolver debe responder limpiamente con arrays vacíos ante una fecha sin datos.
- `travelAvailability` conserva su función para paquetes directos y no usa conexiones sugeridas.

## Salud de fuentes

El frontend puede mostrar estado agregado de fuentes basado en el último `scrape_runs` por fuente:

- `SUCCESS` / `CACHED` / `STALE_FALLBACK`: disponible;
- `SOURCE_UNAVAILABLE`: advertencia;
- fuente deshabilitada: no se cuenta como fuente activa.

El objetivo es mostrar algo como `Fuentes activas: 3 de 4` sin exponer stack traces.

## Cobertura y salud de direcciones

El gateway incorpora un read model puro, por ejemplo `backend/gateway/route_coverage.py`, responsable de:

- consolidar `EOH/MDE` como ciudad Medellín;
- seleccionar hasta 10 ofertas directas por dirección;
- calcular `AVAILABLE`, `PARTIAL`, `NO_OFFERS` y `SOURCE_UNAVAILABLE`;
- producir métricas de las 20 direcciones sin mutar PostgreSQL;
- mantener separada la salud de fuente (`sourceHealth`) de la disponibilidad de ruta.

Una fuente caída no convierte automáticamente una ruta con ofertas de otras fuentes en `SOURCE_UNAVAILABLE`. Ese estado se usa cuando el resultado cero no puede distinguirse de una adquisición incompleta.

## Frontend

La UI conserva los dos modos existentes.

### Explorar vuelos

Flujo:

1. cargar `travelNetwork`;
2. origen entre las cinco ciudades soportadas;
3. destino entre las otras cuatro ciudades, aunque la dirección tenga 0 directos;
4. cargar `flightAvailability`;
5. fechas representadas únicamente como chips/botones de datos directos o conexiones reales;
6. si `flightAvailability.dates` está vacío, mostrar el estado `NO_OFFERS` o `SOURCE_UNAVAILABLE` sin pedir fecha libre;
7. elegir una fecha real cuando exista;
8. ejecutar `flightSearch`;
9. mostrar directos si existen;
10. si no existen, mostrar `Conexiones sugeridas`;
11. filtros simples: menor precio/fecha, directos/conexiones y aerolínea cuando aplique.

No existe `input type="date"` en este flujo.

### Armar paquete

Sin cambios conceptuales:

- solo destinos con `packageAvailable=true`;
- vuelos directos ida y regreso;
- hotel + auto;
- 1–14 noches;
- fechas tomadas de `travelAvailability`;
- SAGA reserva solo los dos vuelos directos, hotel y auto.

Una conexión sugerida nunca habilita un paquete.

## Estados de UX

Mensajes funcionales esperados:

- `10 ofertas disponibles` cuando la dirección alcanza el objetivo visible.
- `Encontramos menos opciones de lo habitual para esta ruta.` cuando el estado es `PARTIAL`.
- `No encontramos vuelos disponibles actualmente. Es posible que los cupos estén agotados o que las aerolíneas todavía no hayan publicado disponibilidad para esta ruta.` para `NO_OFFERS`.
- `No pudimos comprobar completamente esta ruta porque algunas fuentes no estuvieron disponibles.` para `SOURCE_UNAVAILABLE`.
- `No hay ofertas directas para esta fecha. Estas son conexiones sugeridas.`
- `No encontramos vuelos ni conexiones de una escala para esta fecha.`
- `Verifica los horarios exactos con las aerolíneas antes de comprar.`
- `Hay vuelos disponibles, pero este destino aún no tiene hotel y auto scrapeados para armar un paquete.`
- `Algunas fuentes no estuvieron disponibles durante la última actualización.`

## Configuración

`.env.example` debe usar por defecto:

```env
SCRAPE_ENABLED_SOURCES=clicair,satena,jetsmart,wingo,ghl_porton_medellin,alkilautos_national_medellin
TARGET_OFFERS_PER_DIRECTION=10
MAX_ROUTE_CONCURRENCY_PER_SOURCE=2
```

La versión de Prefect del server y del cliente queda fijada al mismo valor en los requirements/imágenes de esta release.

LATAM no aparece en la lista por defecto.

El adapter LATAM puede mantenerse en el repositorio para evidencia histórica o eliminarse del registro productivo; en ambos casos no debe ejecutarse por defecto.

## Resiliencia y seguridad

- `robots.txt` se evalúa antes de adquirir una ruta.
- Un `ROBOTS_DISALLOWED` no se trata como fallo transitorio y no genera retries inútiles.
- Fallos `DNS`, timeout, `429` o `5xx` conservan la política de retries/backoff ya existente.
- La ausencia temporal de una fuente no invalida el grafo construido con otras fuentes.
- Las URLs siguen siendo server-side y allowlisted; el usuario no puede convertir el collector en proxy arbitrario.
- HTML de snapshots nunca se renderiza directamente en el frontend.

## Evidencia académica

La demo debe mostrar:

1. CLIC/SATENA/JetSMART/Wingo como pool activo de vuelos.
2. LATAM como fuente evaluada y deshabilitada por política.
3. snapshots HTML por fuente/ruta.
4. `scrape_runs` con éxito, cache, stale fallback o indisponibilidad.
5. `travelNetwork` construido desde PostgreSQL.
6. `flightSearch` con un vuelo directo.
7. `flightSearch` con una conexión sugerida de una escala cuando no haya directo.
8. `travelPackages` manteniéndose restringido a vuelos directos.

`scripts/scraping_study.sql` se amplía para comparar:

- ofertas por fuente;
- rutas por fuente;
- cobertura de las cinco ciudades;
- rutas directas disponibles;
- pares de ciudades sin directo pero conectables con una escala;
- precios directos por fuente;
- cantidad de snapshots y estados de scraping;
- cobertura objetivo `20` direcciones;
- direcciones `AVAILABLE`, `PARTIAL`, `NO_OFFERS`, `SOURCE_UNAVAILABLE`;
- conteo visible limitado a 10 por dirección;
- comparación baseline (77 ofertas, 10 direcciones) versus release nueva.

## Pruebas de aceptación

La implementación se acepta cuando:

1. `SCRAPE_ENABLED_SOURCES` ya no contiene LATAM por defecto.
2. JetSMART y Wingo tienen adapters HTTP productivos y allowlists específicas.
3. El parser común acepta `Hasta`, `A` y `Hacia`, además de `Fecha`/`Fechas` y los dos nombres de tipo.
4. CLIC y SATENA siguen parseando sin regresión.
5. Un `robots.txt` denegado corta una ruta sin retries transitorios repetitivos.
6. El registry no infiere automáticamente rutas inversas.
7. Las 20 direcciones soportadas aparecen como buscables en `travelNetwork`; una dirección sin ofertas no se marca disponible y conserva `NO_OFFERS`/`SOURCE_UNAVAILABLE`.
8. `flightSearch` devuelve directos primero.
9. Cada dirección expone máximo 10 ofertas directas reales totales entre todas las fuentes; el catálogo bruto puede conservar más evidencia.
10. Una dirección con 1–9 ofertas se clasifica `PARTIAL`, con 10 visibles `AVAILABLE`, con cero observadas sanamente `NO_OFFERS`, y con cero no verificables `SOURCE_UNAVAILABLE`.
11. Si no hay directos para una fecha, `flightSearch` puede construir hasta 10 candidatos y devolver máximo 5 conexiones de una escala.
12. `flightAvailability` no inventa fechas y puede devolver fechas de conexión real cuando no existen directos.
13. Cada conexión usa exactamente dos legs reales activos, misma fecha y COP.
14. Una conexión nunca aparece en `travelPackages` ni en el SAGA.
15. El frontend no contiene campos de fecha libres.
16. Origen/destino incluyen las cinco ciudades soportadas y excluyen únicamente origen=destino; disponibilidad y conexiones se derivan de datos reales.
17. Origen/destino siguen derivados de `travelNetwork`.
18. Las conexiones se rotulan explícitamente como sugeridas y muestran la advertencia de horarios.
19. Una fuente caída no produce error global si otras fuentes entregan datos.
20. Bogotá↔Medellín continúa funcionando.
21. Santa Marta puede mantenerse en la red mediante JetSMART/Wingo cuando publiquen ofertas activas.
22. La concurrencia real no supera 2 rutas simultáneas por fuente y Dask conserva dos workers funcionales.
23. Prefect server/client quedan alineados y el ZIP final contiene `ingestion/snapshots/{__init__.py,manager.py,metadata.py}`.
24. La suite completa permanece verde.
25. El ZIP final no contiene `.git`, `.env`, snapshots runtime, caches ni `node_modules`.

## Archivos previstos

### Nuevos

- `ingestion/sources/flights_jetsmart.py`
- pruebas JetSMART/Wingo HTTP y parser por alias
- `backend/gateway/flight_connections.py`
- `backend/gateway/route_coverage.py`
- pruebas de cobertura por dirección y límite de 10
- pruebas del Connection Engine
- documentación de source pool y conexiones sugeridas

### Modificados

- `ingestion/sources/flight_routes.py`
- `ingestion/sources/registry.py`
- `ingestion/sources/flights_wingo.py`
- `ingestion/parsers/flights.py`
- `ingestion/collectors/http.py` o política equivalente de robots/retry
- `ingestion/flow.py`
- `.env.example`
- `backend/gateway/main.py`
- `backend/gateway/travel_logic.py` cuando sea necesario para resolver ciudades
- `schema.graphql`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`
- `scripts/scraping_study.sql`
- `scripts/demo_validation.py`
- documentación de arquitectura/demo

## Fuera de alcance

- Bypass de políticas de acceso de aerolíneas.
- Reserva real en proveedores externos.
- Conexiones de más de una escala.
- Garantizar viabilidad horaria de una conexión sugerida.
- Afirmar que una oferta ausente fue vendida o agotada sin evidencia explícita del proveedor.
- Borrar ofertas reales excedentes solo para cumplir el máximo visible de diez.
- Incluir conexiones sugeridas dentro del SAGA.
- Añadir nuevos scrapers de hotel/auto fuera del catálogo actual.
- Rellenar rutas o fechas faltantes mediante inferencia.
