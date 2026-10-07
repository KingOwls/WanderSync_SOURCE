# Revisión final de cumplimiento: versión Real Scraping

Fecha de revisión estructural: 2026-10-05.

## Resultado ejecutivo

- **Datos turísticos:** adquisición desde páginas públicas reales mediante Playwright; no hay generador runtime de ofertas.
- **Fuentes activas por defecto:** CLIC y SATENA (vuelos), GHL Portón Medellín (hotel) y Alkilautos/National Medellín (vehículos). Wingo queda disponible como fuente experimental desactivada.
- **Trazabilidad:** snapshots HTML + metadata, SHA-256, `scrape_runs` y `scrape_snapshots`.
- **Dask + Prefect:** etapas de collect/parse/normalize/persist integradas en el pipeline.
- **GraphQL:** conserva el Gateway único y expone procedencia scrapeada.
- **SAGA:** usa **WanderSync Local Hold**; no representa inventario de terceros.
- **Seguridad:** Argon2id, rotación SID, rate limiting, allowlists de scraping, defensa SSRF, robots y no bypass de challenges.
- **Verificación local de generación:** `pytest` y `scripts/verify_project.py` se ejecutan antes de empaquetar.
- **Docker/runtime externo:** debe validarse en un host con Docker e Internet; este entorno de generación no dispone de Docker CLI. No se presenta esa parte como ejecutada.
- **Frontend build/auditorías externas:** la red del generador devolvió `EAI_AGAIN` al intentar acceder al registro npm y `pip-audit` no estaba instalado; esas evidencias permanecen pendientes y los comandos reproducibles están incluidos.

## Arquitectura y Dockerización

Compose contiene PostgreSQL, db-bootstrap, Redis, Flight, Hotel, Car, Order, GraphQL Gateway, Prefect, Dask Scheduler, dos Workers, ingestion-runner, Adminer y frontend. Los componentes de ingesta comparten `./ingestion`, `PYTHONPATH=/app` y el volumen `scrape_snapshots`.

## GraphQL y persistencia

El frontend usa exclusivamente GraphQL. El catálogo guarda `source`, `source_url`, `snapshot_id`, `scraped_at` y `active`. PostgreSQL incluye `scrape_runs` y `scrape_snapshots` para demostrar la procedencia de cada oferta.

## SAGA

Order Service mantiene el happy path y las compensaciones inversas. Flight/Hotel/Car crean holds locales sobre ofertas scrapeadas activas. WanderSync **no realiza reservas en los proveedores externos**, por lo que una cancelación SAGA modifica únicamente el hold local.

## Dask + Prefect + scraping

Playwright captura HTML renderizado y lo guarda antes del parsing. BeautifulSoup procesa snapshots offline. Prefect registra etapas visibles y Dask ejecuta los trabajos a través del scheduler. La adquisición usa una sola navegación simultánea por fuente y caché para minimizar tráfico.

## Fuentes y manejo de fallas

- CLIC: `https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin`
- SATENA: `https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-medellin`
- Wingo: adaptador experimental, desactivado por defecto por challenges observados.
- GHL: `https://www.ghlhoteles.com/es/hoteles/colombia/medellin/ghl-porton-medellin/`
- Alkilautos/National: `https://alkilautos.com/alquiler-carros-medellin/ciudad/national/`

403/429 persistentes, CAPTCHA, challenge o cambio de DOM no activan evasión. Se reutiliza únicamente un snapshot real de hasta 24 h; de no existir, se registra `SOURCE_UNAVAILABLE`.

## Ciberseguridad

Se conservan Argon2id, sesiones server-side en Redis, rotación SID y rate limiting. La capa de scraping añade allowlists por adaptador, validación de IP/DNS pública, `robots.txt`, User-Agent académico, timeout y retries acotados.

## Evidencia

- `VERIFICATION_REPORT.txt`
- `REAL_SCRAPING_ACCEPTANCE.md`
- `docs/ARCHITECTURE.md`
- `docs/DEMO_GUIDE.md`
- `docs/COMPLIANCE.md`
- `scripts/demo_validation.py`
- `security/audit.sh` / `.ps1`

La aceptación runtime final debe completarse en el computador de entrega siguiendo `REAL_SCRAPING_ACCEPTANCE.md`.
