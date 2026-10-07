# Matriz de cumplimiento

| Solicitud | Implementación | Evidencia |
|---|---|---|
| Docker Compose | 15 servicios/infraestructura coordinados | `docker compose ps` |
| Microservicios | Flight, Hotel, Car, Order/Billing, Gateway | `backend/`, Compose |
| Gateway GraphQL único | Strawberry GraphQL; frontend solo usa `VITE_GRAPHQL_URL` | GraphiQL, `frontend/src/api.js` |
| Consultas complejas | `flightOffers`, `travelPackages`, bookings y eventos | `schema.graphql`, Gateway |
| SAGA | Order Service orquesta local holds + Billing | `saga_events`, `docs/SAGA.md` |
| Happy path | Flight → Hotel → Car → Billing | orden `CONFIRMED` |
| Compensación | rollback inverso idempotente | fallo `car`/`billing` → `CANCELLED` |
| Scraping real | Playwright captura CLIC, SATENA, GHL y Alkilautos | snapshots HTML + `scrape_runs` |
| Cero fallback sintético | solo snapshot real fresco/antiguo permitido | `ingestion/flow.py`, tests |
| Dask distribuido | scheduler + 2 workers; Futures | dashboard `:8787/status` |
| Prefect | Flow `WanderSync real scraping ingestion` | UI `:4200` |
| Etapas observables | collect / parse / normalize / persist | Prefect + `ingestion/flow.py` |
| Parsing offline | BeautifulSoup sobre snapshots | `ingestion/parsers/` |
| Persistencia | UPSERT con `source_url`, `snapshot_id`, `scraped_at` | PostgreSQL/Adminer |
| Trazabilidad | `scrape_runs` + `scrape_snapshots` + SHA-256 | consultas SQL |
| Caché | snapshot real <30 min → `CACHED` | segunda ingesta |
| Resiliencia | snapshot real <=24 h o `SOURCE_UNAVAILABLE` | tests + logs |
| Scraping responsable | robots, allowlist, pacing 90–180 s, concurrencia 1 | collector/policies |
| SSRF | host allowlist + rechazo IP/DNS no público | `test_scrape_security.py` |
| CAPTCHA/403 | detener, no bypass | collector + logs |
| Argon2id | contraseña hasheada | `users.password_hash` |
| Session Fixation | SID eliminado/rotado después de login | Gateway + Redis |
| Rate limiting | Redis en login/checkout/payment | HTTP 429 / `RATE_LIMITED` |
| Supply Chain | pip-audit backend/ingestion + npm audit frontend | `security/reports/` |
| DB idempotente | `db-bootstrap` aplica schema | Compose + `init.sql` |
| Pruebas | pytest + verificador estático + demo runtime | `tests/`, `VERIFICATION_REPORT.txt` |

## Frontera transaccional

Los sitios externos suministran información pública. WanderSync **no realiza reservas en los proveedores externos**. SAGA trabaja con un **WanderSync Local Hold** para demostrar consistencia distribuida sin alterar o representar inventario real de terceros.

## Política de fuentes y cobertura

Las fuentes productivas de vuelos son CLIC, SATENA, JetSMART y Wingo. LATAM fue evaluada y está deshabilitada por `ROBOTS_DISALLOWED`; no se evade `robots.txt`. La aplicación ofrece las **20 direcciones** entre cinco ciudades y expone como máximo **10 ofertas** reales por dirección, con `AVAILABLE`, `PARTIAL`, `NO_OFFERS` o `SOURCE_UNAVAILABLE`.

Las conexiones son una **conexión sugerida**, no una reserva garantizada. El mensaje obligatorio es **Verifica los horarios exactos con las aerolíneas.** Los paquetes permanecen direct-only. WanderSync no realiza reservas en los proveedores externos.
