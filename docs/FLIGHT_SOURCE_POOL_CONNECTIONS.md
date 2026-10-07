# Pool de fuentes de vuelos y cobertura de red

## Fuentes productivas

WanderSync consulta cuatro fuentes públicas de vuelos mediante HTTP respetuoso y snapshots reales: **CLIC**, **SATENA**, **JetSMART** y **Wingo**. El registro de rutas es auditable y cada URL debe permanecer dentro del host permitido por su adaptador. La adquisición respeta `robots.txt`, cache, backoff, límites de concurrencia y fallback solo a snapshots obtenidos realmente.

**LATAM fue evaluada pero está deshabilitada en producción con estado `ROBOTS_DISALLOWED`** porque las rutas requeridas no permiten el recolector académico. WanderSync no evade esa restricción. Sus registros históricos pueden conservarse como evidencia, pero no se programan nuevos runs productivos.

## Objetivo de cobertura

Las ciudades soportadas son Bogotá (`BOG`), Medellín (`MDE`, resolviendo también `EOH`), Cali (`CLO`), Cartagena (`CTG`) y Santa Marta (`SMR`). Las cinco ciudades forman **20 direcciones** ordenadas buscables. La ausencia de un vuelo directo no elimina la dirección de la interfaz.

Para cada dirección, el read model expone **hasta 10 ofertas reales** sumando todas las aerolíneas. PostgreSQL puede conservar más de 10 filas reales para auditoría; el límite de 10 es de selección/visualización y nunca rellena huecos con mocks.

Estados:
- `AVAILABLE`: 10 o más ofertas reales en el catálogo bruto y 10 visibles.
- `PARTIAL`: entre 1 y 9 ofertas reales.
- `NO_OFFERS`: las fuentes necesarias se comprobaron y no publicaron ofertas válidas.
- `SOURCE_UNAVAILABLE`: no fue posible comprobar completamente la dirección.

`NO_OFFERS` no significa necesariamente que los vuelos “se vendieron”. Puede indicar falta de programación publicada o ausencia de cupos visibles en las fuentes consultadas.

## Adquisición y parser

CLIC, SATENA, JetSMART y Wingo usan páginas públicas. El parser semántico acepta alias de encabezados como `Hasta`, `A`, `Hacia`, `Fecha`, `Fechas`, `Tipo de vuelo` y `Tipo de tarifa`, y exige fecha concreta y precio COP concreto.

Las rutas de una misma fuente pueden adquirirse con concurrencia limitada por `MAX_ROUTE_CONCURRENCY_PER_SOURCE=2`. Esto acelera el catálogo sin convertir el scraping en una ráfaga agresiva.

## Vuelos directos y conexiones

`flightSearch` busca primero vuelos directos para la fecha elegida. Si hay directos, expone hasta 10 y no necesita expandir el grafo. Si no existen directos, puede generar candidatos de **una sola escala** usando exactamente dos legs activos y reales, en la misma fecha, con moneda COP y sin ciclos.

El backend puede considerar hasta 10 candidatos y el frontend muestra las mejores 5 conexiones. Las conexiones se derivan en lectura y no se persisten como vuelos nuevos.

Toda conexión se presenta con la advertencia:

> **Conexión sugerida. Verifica los horarios exactos con las aerolíneas.**

La misma fecha no garantiza compatibilidad horaria. Por ello las conexiones sugeridas son exploratorias y no participan en checkout.

## Fechas

`flightAvailability` devuelve únicamente fechas reales donde existe un directo o una conexión candidata válida según el catálogo actual. No existe input de fecha libre en el frontend.

`travelAvailability` continúa reservado a paquetes ida/vuelta directos de 1 a 14 noches.

## Paquetes y SAGA

Los paquetes siguen siendo estrictamente directos: vuelo directo de ida + vuelo directo de regreso + hotel + vehículo. GHL y Alkilautos continúan siendo las fuentes actuales de hotel y auto para el alcance disponible. Las conexiones sugeridas nunca se envían a checkout ni al SAGA.

WanderSync **no realiza reservas en los proveedores externos**. Las operaciones de demostración crean `WanderSync Local Hold` en los microservicios locales para mostrar la SAGA y sus compensaciones.

## Salud y tolerancia a fallos

`sourceHealth` resume únicamente las cuatro fuentes activas de vuelos. La interfaz muestra `Fuentes activas: X de 4` y una advertencia genérica si alguna fuente no estuvo disponible, sin exponer stack traces.

Los estados de adquisición conservados son `SUCCESS`, `CACHED`, `STALE_FALLBACK` y `SOURCE_UNAVAILABLE`. `STALE_FALLBACK` solo puede usar un snapshot real anterior dentro del límite configurado.

## Baseline académico

Antes de JetSMART/Wingo, la ejecución estable verificada por el usuario produjo **77 ofertas activas de vuelos**, **10 rutas dirigidas** y **5 parejas bidireccionales**, con CLIC y SATENA. Santa Marta no tenía cobertura y Bogotá↔Cartagena carecía de directo. Esta línea base permite medir el crecimiento real del nuevo pool.
