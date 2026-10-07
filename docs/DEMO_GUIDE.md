# Guion de demostración: scraping real + red multi-ciudad

## 0. Preparación

```bash
cp .env.example .env
docker compose up --build -d
```

Abra Frontend `:8080`, GraphiQL `:8000/graphql`, Prefect `:4200`, Dask `:8787/status` y Adminer `:8081`.

Si ejecuta el runner manual con `docker compose run`, confirme antes que `dask-worker-1` y `dask-worker-2` estén activos:

```bash
docker compose up -d dask-scheduler dask-worker-1 dask-worker-2
```

## 1. Servicios y ausencia de catálogo sintético

```bash
docker compose ps
```

Muestre PostgreSQL, Redis, Flight/Hotel/Car/Order, Gateway, Prefect, Dask scheduler + dos workers, ingestion-runner y frontend. No existe ningún servicio generador de ofertas sintéticas.

## 2. Ejecutar scraping real

```bash
docker compose run --rm --no-deps -e INGEST_RUN_ONCE=true ingestion-runner python -m ingestion.runner
```

Fuentes por defecto:

- CLIC: rutas nacionales multi-ciudad.
- SATENA: rutas nacionales y redundancia de varias conexiones.
- LATAM: cobertura adicional, especialmente Santa Marta.
- GHL Portón Medellín: hotel.
- Alkilautos/National Medellín: autos.

En Prefect muestre `collect`, `parse`, `normalize`, `persist`. En Dask confirme dos workers.

## 3. Mostrar snapshots y procedencia

```bash
docker compose exec ingestion-runner find /data/snapshots -type f | sort | tail -50
```

Abra un `.html` y su `.json`. Los archivos deben conectar fuente, URL, fecha, hash y contenido capturado.

## 4. Mostrar runs y red activa en PostgreSQL

```bash
docker compose exec postgres psql -U wandersync -d wandersync -c \
"SELECT id,source,kind,status,items_found,snapshot_id FROM scrape_runs ORDER BY id DESC LIMIT 20;"
```

Después:

```bash
docker compose exec -T postgres psql -U wandersync -d wandersync < scripts/scraping_study.sql
```

El estudio consolida `EOH/MDE` como Medellín solo para análisis y muestra rutas, fuentes, precios, fechas, pares ida/vuelta y capacidad de paquete.

## 5. GraphQL `travelNetwork`

```graphql
query {
  travelNetwork {
    cities { code name airports }
    routes {
      origin destination offerCount sources
      roundTripAvailable packageAvailable firstDate lastDate lowestPrice
    }
  }
}
```

Explique que una URL del registry no crea una ruta visible: la arista existe únicamente si hay ofertas activas persistidas.

## 6. Frontend: Explorar vuelos

Abra `http://localhost:8080` y seleccione **Explorar vuelos**.

- Origen y destino vienen de `travelNetwork`.
- No existen campos de fecha libre.
- Las fechas se ofrecen como chips provenientes de `travelAvailability`.
- Una ruta puede mostrarse aun cuando `packageAvailable=false`.
- Las tarjetas muestran aerolínea, ruta, fecha, precio, fuente y captura.

Intente una conexión fuera de Bogotá↔Medellín si el scraping actual produjo una arista activa, por ejemplo Cali/Cartagena/Santa Marta según disponibilidad real del día.

## 7. Frontend: Armar paquete

Cambie a **Armar paquete**. Solo aparecen destinos con ida + regreso + hotel + auto. Con el catálogo actual Medellín suele ser el principal destino completo.

Seleccione únicamente fechas ofrecidas por `travelAvailability`. El paquete contiene:

```text
vuelo ida + vuelo regreso + hotel × noches + auto × noches
```

## 8. SAGA happy path y compensación

Registre/login, reserve un paquete real y confirme `CONFIRMED` + `PAID`.

Después ejecute `scripts/demo_validation.py` o `simulateFailure:"return_flight"`. Debe observar compensación de `outbound_flight` cuando falla el hold del vuelo de regreso.

WanderSync **no realiza reservas en los proveedores externos**. Los holds y Billing son académicos/locales.

## 9. Cache y fallas externas

Ejecute nuevamente la ingesta antes del TTL: debe aparecer `CACHED`.

Ante fallo externo:

- snapshot real aceptable → `STALE_FALLBACK`;
- sin snapshot → `SOURCE_UNAVAILABLE`;
- nunca se generan ofertas artificiales.

## 10. Validación automatizada

```bash
python scripts/demo_validation.py
```

El script descubre `travelNetwork`, selecciona una ruta real, prueba disponibilidad y, si existe una ruta `packageAvailable`, ejecuta paquete + SAGA. Prefiere BOG↔MDE cuando está activa, pero no asume que todos los pares existan.

## 11. Seguridad y cierre

- mostrar Argon2id en `users.password_hash`;
- comparar SID antes/después del login;
- provocar `RATE_LIMITED`;
- explicar allowlist, SSRF, robots y ausencia de bypass CAPTCHA;
- ejecutar `security/audit.sh` o `security/audit.ps1`.

Cierre con `docs/MULTI_CITY_FLIGHT_NETWORK.md`, `REAL_SCRAPING_ACCEPTANCE.md`, `docs/COMPLIANCE.md` y `VERIFICATION_REPORT.txt`.

## Demo de cobertura de vuelos

1. Ejecutar la ingesta real y comprobar CLIC, SATENA, JetSMART y Wingo en `scrape_runs`.
2. Consultar `sourceHealth` y mostrar `Fuentes activas: X de 4`.
3. Consultar `travelNetwork`: deben existir cinco ciudades y **20 direcciones**, incluso cuando una tenga `NO_OFFERS`.
4. Elegir una ruta con vuelos, usar `flightAvailability` y seleccionar una fecha real.
5. Ejecutar `flightSearch`: mostrar hasta **10 ofertas** directas. Si no hay directos y existe una ruta de una escala en la misma fecha, mostrarla como **conexión sugerida**.
6. Para cualquier conexión remarcar: **Verifica los horarios exactos con las aerolíneas.** La misma fecha no garantiza los horarios.
7. Si la data externa actual no contiene una conexión candidata, reportar `SKIP/NOT AVAILABLE`; nunca fabricarla.
8. Para paquetes elegir únicamente una dirección `packageAvailable=true` y usar `travelAvailability` + `travelPackages`.

Estados esperados por dirección: `AVAILABLE`, `PARTIAL`, `NO_OFFERS`, `SOURCE_UNAVAILABLE`. GHL y Alkilautos siguen siendo el alcance de hotel/auto. `STALE_FALLBACK` significa reutilización de snapshot real anterior. WanderSync no realiza reservas en los proveedores externos; usa WanderSync Local Hold.
