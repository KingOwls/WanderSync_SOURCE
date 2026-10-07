# Auditoría previa al arranque - Real Scraping

## Estructura validada sin Docker

1. Compose contiene 15 servicios/infraestructura y no contiene un generador runtime de ofertas.
2. Scheduler, workers y runner usan `./ingestion` y `PYTHONPATH=/app`.
3. Workers y runner comparten `scrape_snapshots:/data/snapshots`.
4. La imagen de ingesta instala Playwright, Chromium, BeautifulSoup, Dask, Prefect y Bokeh.
5. PostgreSQL contiene `scrape_runs` y `scrape_snapshots` además del catálogo y la SAGA.
6. Los servicios de dominio usan **WanderSync Local Hold** y no decrementan inventario externo.
7. Gateway conserva GraphQL, Argon2id, rotación SID y rate limiting.
8. CLIC, SATENA, GHL y Alkilautos están encapsulados en adaptadores con allowlists; Wingo permanece como experimental desactivado.
9. La política de adquisición usa snapshots/caché, `robots.txt`, pacing y no bypass de challenges.
10. `scripts/verify_project.py` comprueba estos contratos automáticamente.

## Evidencia runtime pendiente

En el equipo con Docker e Internet ejecute:

```bash
docker compose config
docker compose up --build -d
docker compose ps
docker compose run --rm -e INGEST_RUN_ONCE=true ingestion-runner python runner.py
python scripts/demo_validation.py
```

Después complete `REAL_SCRAPING_ACCEPTANCE.md` con evidencia de dos workers Dask, Flow Prefect, snapshots HTML reales, trazabilidad SQL, caché, GraphQL y SAGA.

## Riesgos externos legítimos

Las páginas públicas pueden cambiar HTML, bloquear automatización o dejar de publicar un campo. La conducta esperada es `STALE_FALLBACK` sobre un snapshot real permitido o `SOURCE_UNAVAILABLE`, nunca evasión ni fabricación de datos.
