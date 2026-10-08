# WanderSync Travel Solutions

WanderSync es una plataforma académica de exploración de vuelos y composición de paquetes turísticos con ofertas observadas en fuentes públicas reales. Usa React, GraphQL, microservicios FastAPI, PostgreSQL, Redis, Prefect y Dask.

## Versión actual: actualización diaria y cinco ciudades

- Bogotá, Medellín, Cali, Cartagena y Santa Marta; 20 direcciones consultables.
- Ciclo de ingesta cada 24 horas, persistente entre reinicios y con trazabilidad por ruta.
- Consultas por intervalo de fechas, hasta 90 fechas en la interfaz y paginación de ofertas.
- Hoteles y vehículos configurados para las cinco ciudades.
- Paquetes de ida y vuelta de 1–14 noches, con itinerario cronológico y desglose estimado.
- Horarios por confirmar cuando la fuente no los publica; ninguna hora se inventa.
- Checkout valida coherencia, vigencia y precio; idempotencia y recuperación de SAGA.
- Snapshots y precios históricos conservados para auditoría.

La cobertura efectiva depende de las páginas públicas. Una dirección consultable puede no tener vuelos publicados, o una fuente puede fallar. Las tarifas de hotel y vehículo no confirman disponibilidad para las fechas solicitadas.

**Las reservas y el cobro son una demostración local. No se realizan reservas ni pagos en proveedores externos.**

Lee [el funcionamiento completo de esta versión](docs/DAILY_FIVE_CITY_TRAVEL.md). Los documentos de hotfix anteriores conservan decisiones históricas y pueden describir límites reemplazados por esta versión.

## Inicio

```bash
cp .env.example .env
docker compose up --build -d
```

Para actualizar una instalación existente, ajusta `INGEST_INTERVAL_SECONDS=86400` y la lista ampliada `SCRAPE_ENABLED_SOURCES` de `.env.example` en tu `.env`. Conserva las credenciales existentes.

```bash
docker compose build
docker compose up -d --force-recreate
```

El bootstrap aplica tablas nuevas conservando el catálogo y los usuarios. No es necesario borrar los volúmenes.

| Interfaz | URL |
|---|---|
| WanderSync | http://localhost:8080 |
| GraphQL | http://localhost:8000/graphql |
| Prefect | http://localhost:4200 |
| Dask | http://localhost:8787/status |
| Adminer | http://localhost:8081 |

La primera ingesta ampliada puede durar decenas de minutos por los intervalos de adquisición responsables. La interfaz se actualiza cada minuto.

## Validación

```bash
pytest -q
python scripts/verify_project.py
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/demo_validation.py
```

La validación runtime crea registros locales de demostración. La ingesta jamás rellena resultados con datos sintéticos. Reutiliza snapshots reales de hasta 24 horas ante fallos; las consultas excluyen capturas de más de 48 horas y vuelos pasados.

## Arquitectura

Fuentes públicas → adquisición HTTP/Playwright → snapshots → parsing offline → normalización → PostgreSQL → servicios de catálogo → GraphQL → React.

Prefect coordina las etapas y Dask ejecuta el procesamiento distribuido. Order Service coordina la SAGA de holds locales, conserva sus eventos y recupera operaciones interrumpidas. Redis administra sesiones y límites de solicitudes.

## Seguridad y operación

Argon2id, rotación de sesión al ingresar, cookies HttpOnly, límites Redis, validación de propiedad de órdenes, allowlists de fuentes, robots.txt, validación de redirecciones HTTP y pacing entre procesos. CAPTCHA y bloqueos se detienen; no se evaden.

```bash
./security/audit.sh
```

La configuración Docker incluida está orientada a demostración local. Los dashboards e interfaces administrativas requieren protección adicional antes de publicarse en Internet.
