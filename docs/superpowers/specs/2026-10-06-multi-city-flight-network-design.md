# WanderSync Multi-City Flight Network Design

## Estado

Diseño arquitectónico aprobado conversacionalmente para ampliar WanderSync desde una ruta fija Bogotá ↔ Medellín a una red turística dinámica basada únicamente en ofertas de vuelo scrapeadas y activas.

Fecha: 2026-10-06

## Objetivo

Permitir que WanderSync explore vuelos entre Bogotá, Medellín, Cali, Cartagena y Santa Marta usando rutas y fechas realmente publicadas por fuentes externas, sin listas de destinos ni fechas inventadas en el frontend.

La experiencia queda separada en dos modos:

1. **Explorar vuelos**: funciona sobre toda la red de vuelos activos disponible en PostgreSQL.
2. **Armar paquete**: solo se habilita cuando el destino dispone simultáneamente de vuelo de ida, vuelo de regreso, hotel y auto scrapeados.

## Restricciones no negociables

- Cero fallback mock.
- No inventar rutas, fechas, precios, aeropuertos ni disponibilidad.
- Una ruta existe para el usuario solo si hay al menos una oferta activa almacenada para esa dirección.
- Una ruta ida/vuelta se considera completa solo si existen ofertas activas en ambas direcciones.
- El frontend no permite escribir fechas manualmente; las fechas se seleccionan únicamente desde `travelAvailability`.
- CLIC y SATENA conservan adquisición HTTP pública con snapshots y cache.
- LATAM se incorpora como fuente pública adicional para mejorar cobertura, especialmente Santa Marta. Debe usar HTTP público cuando el HTML contenga las ofertas; si la adquisición no es aceptable, se marca `SOURCE_UNAVAILABLE`. No se implementan técnicas de evasión.
- GHL y Alkilautos no se modifican en esta fase.
- Los paquetes locales siguen siendo reservas académicas internas; WanderSync no afirma reservar en sistemas externos.

## Ciudades y resolución de aeropuertos

El dominio turístico inicial queda limitado a cinco ciudades:

| Ciudad | Código turístico | Aeropuertos aceptados para vuelos | Ciudad de servicios |
| --- | --- | --- | --- |
| Bogotá | `BOG` | `BOG` | `BOG` |
| Medellín | `MDE` | `MDE`, `EOH` | `MDE` |
| Cali | `CLO` | `CLO` | `CLO` |
| Cartagena | `CTG` | `CTG` | `CTG` |
| Santa Marta | `SMR` | `SMR` | `SMR` |

`MDE` sigue siendo el código turístico de Medellín, aunque CLIC/SATENA publiquen vuelos usando `EOH` y LATAM pueda publicar `MDE`.

## Fuentes de vuelo

### CLIC

CLIC mantiene el parser tabular actual `Desde | Hasta | Tipo de vuelo | Fecha | Precio`.

Rutas iniciales configuradas y verificadas para el registry:

- `BOG → EOH`
- `EOH → BOG`
- `BOG → CLO`
- `CLO → BOG`
- `EOH → CLO`
- `CLO → EOH`
- `EOH → CTG`
- `CTG → EOH`
- `CLO → CTG`
- `CTG → CLO`

Las rutas se consultan por URL pública específica. Una URL configurada no crea una arista visible por sí sola: si el snapshot no produce ofertas normalizadas activas, la ruta no aparece en el grafo.

### SATENA

SATENA mantiene el parser tabular compartido con CLIC.

Rutas iniciales:

- `BOG → EOH`
- `EOH → BOG`
- `BOG → CLO`
- `CLO → BOG`
- `EOH → CLO`
- `CLO → EOH`

SATENA actúa también como segunda fuente para rutas que CLIC publique, permitiendo comparar proveedores sin alterar el modelo común `Flight`.

### LATAM

Se añade `LatamFlightsAdapter` con parser separado para las tarjetas/textos públicos de ofertas LATAM.

Rutas iniciales orientadas a Santa Marta:

- `BOG → SMR`
- `SMR → BOG`
- `MDE → SMR`
- `SMR → MDE`
- `CLO → SMR`
- `SMR → CLO`
- `CTG → SMR`

La dirección `SMR → CTG` solo se activa cuando exista una página pública verificable que produzca ofertas normalizadas. No se infiere una ruta inversa por simetría.

El parser LATAM debe extraer únicamente ofertas de solo ida con fecha concreta, precio COP, origen y destino reconocibles. Las ofertas agregadas mensuales sin fecha exacta no entran a `flights`.

## Route Registry

Se crea una unidad dedicada, por ejemplo `ingestion/sources/flight_routes.py`, con una estructura explícita:

```python
@dataclass(frozen=True)
class RouteSpec:
    source: str
    origin: str
    destination: str
    url: str
    acquisition_mode: str
```

Los adapters de vuelo construyen `ScrapeRequest` desde sus `RouteSpec` en vez de tener dos URLs fijas dentro de cada clase.

Responsabilidades:

- contener únicamente rutas configuradas y auditables;
- proporcionar contexto `origin`, `destination`, `route_key` a cada request;
- permitir agregar o retirar una ruta sin modificar el parser;
- no afirmar disponibilidad: esa responsabilidad pertenece a los datos activos persistidos.

## Ingesta multi-ruta

El batch de vuelos ya soporta múltiples `ScrapeRequest`; esta fase lo generaliza a varias rutas por fuente.

Flujo por fuente:

1. Prefect inicia la cadena de la fuente.
2. El adapter produce N requests desde el registry.
3. Dask adquiere cada ruta respetando cache, pacing, robots y allowlist.
4. Cada snapshot se registra antes de parsear.
5. El parser procesa cada snapshot de manera independiente.
6. Las rutas exitosas se normalizan y se acumulan.
7. `persist_catalog_batch()` refresca solamente las rutas exitosas cuando alguna ruta de la fuente falla, preservando rutas no observadas durante el fallo parcial.
8. El resultado de la fuente puede ser `SUCCESS`, `CACHED`, `STALE_FALLBACK` o parcial con diagnóstico en `error_message`.

Una ruta fallida no elimina las ofertas vigentes de otras rutas de la misma fuente.

## Grafo dinámico de rutas

El frontend deja de usar una constante de ciudades/destinos. El grafo se deriva exclusivamente de `flights.active = TRUE`.

El Flight Service añade un endpoint agregado, por ejemplo `GET /routes`, que devuelve por combinación `origin,destination`:

- cantidad de ofertas activas;
- fuentes distintas;
- primera y última fecha disponible;
- precio mínimo opcional.

El Gateway transforma aeropuertos a códigos turísticos usando el resolver de ubicaciones.

Ejemplos:

- `EOH → CLO` se expone como `MDE → CLO`.
- `MDE → SMR` se expone también como `MDE → SMR`.
- Si existen `EOH → CLO` y `MDE → CLO`, se consolidan en una sola arista turística `MDE → CLO` acumulando ofertas y fuentes.

## GraphQL

Se añade una consulta de red:

```graphql
travelNetwork: TravelNetwork!
```

Tipos conceptuales:

```graphql
type TravelNetwork {
  cities: [TravelCity!]!
  routes: [TravelRoute!]!
}

type TravelCity {
  code: String!
  name: String!
  airports: [String!]!
}

type TravelRoute {
  origin: String!
  destination: String!
  offerCount: Int!
  sources: [String!]!
  outboundAvailable: Boolean!
  roundTripAvailable: Boolean!
  packageAvailable: Boolean!
  firstDate: String
  lastDate: String
  lowestPrice: Float
}
```

### `packageAvailable`

Es `true` únicamente cuando:

- hay al menos una oferta activa de ida;
- hay al menos una oferta activa de regreso;
- existe al menos un hotel activo en `destination.service_city`;
- existe al menos un auto activo en `destination.service_city`.

Con el catálogo actual esto hará que Medellín sea el principal destino de paquete, pero permitirá llegar a Medellín desde cualquier origen con ruta ida/vuelta activa, no solo Bogotá.

### `travelAvailability`

Se conserva y pasa a operar con cualquier combinación válida del resolver de ciudades.

- máximo 8 fechas de ida;
- máximo 8 fechas de regreso;
- regreso posterior a salida;
- duración de 1 a 14 noches;
- máximo 12 combinaciones recomendadas;
- fechas provenientes únicamente de ofertas activas.

### `flightOffers`

Se conserva para explorar vuelos de una ruta turística. Debe aceptar `MDE` y resolver tanto `EOH` como `MDE`.

## Frontend

La pestaña actual de búsqueda se divide visualmente en dos modos.

### Modo 1: Explorar vuelos

Objetivo: demostrar toda la red scrapeada aunque no haya hotel/auto en el destino.

Comportamiento:

1. Al cargar, consulta `travelNetwork`.
2. El selector Origen contiene solamente ciudades con rutas salientes activas.
3. El selector Destino se recalcula a partir de las rutas activas del origen seleccionado.
4. Al cambiar origen/destino, consulta `travelAvailability`.
5. No existe `input type=date`.
6. Se muestran chips para fechas de salida reales.
7. Al elegir salida se muestran regresos compatibles cuando existan.
8. Se listan ofertas reales con aerolínea, ruta, fecha, precio, fuente y fecha de scraping.
9. Si no existe regreso activo, el modo vuelos puede seguir mostrando las ofertas de solo ida y debe indicar que no hay combinación ida/vuelta disponible.

### Modo 2: Armar paquete

Objetivo: reservar el bundle académico completo.

- Origen: ciudades con una ruta hacia un destino `packageAvailable=true`.
- Destino: únicamente destinos con `packageAvailable=true` para el origen elegido.
- Fechas: solo chips de `travelAvailability`; sin edición manual.
- Resultados: `travelPackages` ida + vuelta + hotel + auto.
- Si una ruta tiene vuelos pero no paquete, el frontend ofrece un enlace/cambio a “Explorar vuelos” en vez de mostrar error genérico.

## Mensajes de estado

Sustituir mensajes ambiguos por estados específicos:

- `No hay ofertas activas para esta ruta en el último scraping.`
- `Hay vuelos de ida, pero todavía no hay ofertas de regreso.`
- `Hay vuelos disponibles, pero este destino aún no tiene hotel y auto scrapeados para armar un paquete.`
- `No hay combinación de 1–14 noches entre las fechas publicadas.`

Nunca pedir al usuario revisar Prefect como primera explicación funcional; Prefect queda como evidencia técnica, no como parte de la UX normal.

## Hoteles y autos fuera de Medellín

Esta fase **no** añade nuevos scrapers de hoteles/autos para Cali, Cartagena, Santa Marta o Bogotá.

Motivo: el objetivo inmediato es terminar una red de vuelos real y demostrable sin multiplicar simultáneamente las fuentes externas frágiles.

El modelo queda preparado para que futuros adapters agreguen `city=CLO`, `CTG`, `SMR` o `BOG`; cuando eso ocurra, `packageAvailable` cambiará automáticamente sin hardcodear el frontend.

## Persistencia

No se requiere cambiar el esquema de `flights`.

Cada vuelo conserva:

- aeropuerto real en `origin` y `destination`;
- `travel_date` real;
- precio y moneda;
- `source`;
- `source_url`;
- `snapshot_id`;
- `scraped_at`.

El grafo turístico se construye en lectura mediante la capa de resolución de ciudades; no se reescriben los códigos de aeropuerto scrapeados.

## Resiliencia y seguridad

- Cache reciente evita visitas repetidas.
- `STALE_FALLBACK` solo usa snapshots reales previos.
- Fallos parciales de una ruta no deben desactivar rutas no observadas.
- Persisten allowlists por dominio.
- No se siguen URLs suministradas por el usuario.
- No se implementa bypass de CAPTCHA, fingerprint spoofing, proxies rotativos ni técnicas de evasión.
- Si LATAM deja de publicar una estructura parseable, su ruta desaparece progresivamente cuando ya no haya ofertas activas válidas; las demás fuentes continúan.

## Evidencia académica

La demo debe poder mostrar cuatro capas:

1. **Fuentes**: CLIC, SATENA y LATAM con URLs públicas.
2. **Snapshots**: HTML y metadata por ruta.
3. **Red**: `travelNetwork` derivado de vuelos activos.
4. **UX**: selección de origen/destino/fechas sin valores inventados.

Se ampliará `scripts/scraping_study.sql` para incluir:

- ofertas por ciudad origen/destino;
- fuentes por ruta;
- precio mínimo/promedio/máximo por ruta;
- primera/última fecha observada;
- cantidad de rutas de solo ida;
- cantidad de pares con ida/vuelta;
- rutas con `packageAvailable`.

## Pruebas de aceptación

La implementación se acepta cuando se demuestra lo siguiente:

1. El registry contiene las rutas iniciales declaradas y cada request conserva `origin`, `destination` y URL.
2. CLIC/SATENA continúan parseando sus tablas actuales.
3. LATAM parsea ofertas de solo ida con fecha exacta y COP; ignora resúmenes mensuales sin fecha.
4. Un fallo en una ruta no desactiva ofertas de otras rutas de la misma fuente.
5. `resolve_location()` reconoce `BOG`, `MDE`, `CLO`, `CTG`, `SMR` y consolida `EOH/MDE` bajo Medellín.
6. `/routes` agrega únicamente vuelos activos.
7. `travelNetwork` no devuelve una ruta sin ofertas activas.
8. Destinos del frontend cambian dinámicamente al cambiar origen.
9. El frontend no contiene `input type="date"` en la búsqueda turística.
10. Las fechas mostradas proceden de `travelAvailability`.
11. “Explorar vuelos” puede mostrar rutas sin paquete.
12. “Armar paquete” solo muestra destinos con ida + regreso + hotel + auto.
13. Bogotá↔Medellín sigue funcionando sin regresión.
14. Una ruta como Cali↔Medellín puede producir disponibilidad de ida/vuelta si las fuentes activas la publican.
15. Santa Marta aparece en la red únicamente cuando LATAM produce ofertas activas válidas.
16. La suite completa existente sigue verde.
17. El ZIP final no contiene `.env`, `.git`, snapshots de ejecución ni caches locales.

## Archivos previstos

### Nuevos

- `ingestion/sources/flight_routes.py`
- `ingestion/sources/flights_latam.py`
- pruebas del parser LATAM y route registry
- pruebas de red GraphQL/frontend
- documentación de red multi-ciudad

### Modificados

- `ingestion/sources/flights_clic.py`
- `ingestion/sources/flights_satena.py`
- `ingestion/sources/registry.py`
- `ingestion/parsers/flights.py` o parser LATAM dedicado según aislamiento final
- `ingestion/flow.py`
- `backend/flight_service/main.py`
- `backend/gateway/travel_logic.py`
- `backend/gateway/main.py`
- `schema.graphql`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`
- `scripts/scraping_study.sql`
- `scripts/demo_validation.py`
- documentación de arquitectura, GraphQL y demo

## Fuera de alcance

- Scraping de nuevos hoteles/autos fuera de Medellín.
- Compra o reserva real en las aerolíneas.
- Itinerarios multi-tramo reservables.
- Predicción de precios.
- Rellenar rutas faltantes mediante inferencia.
- Forzar una malla completa entre las cinco ciudades.

La red visible siempre será un reflejo del catálogo scrapeado activo, no un mapa teórico de conexiones posibles.
