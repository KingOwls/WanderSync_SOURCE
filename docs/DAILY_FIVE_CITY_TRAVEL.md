# Actualización diaria y viajes en cinco ciudades

## Alcance

Bogotá (BOG), Medellín (MDE/EOH), Cali (CLO), Cartagena (CTG) y Santa Marta (SMR) pueden seleccionarse como origen y destino en ambos modos. Las 20 direcciones son consultables; su existencia en el registro no garantiza vuelos publicados. JetSMART y Wingo tienen páginas candidatas para todas las direcciones, conservando las páginas originales de CLIC y SATENA. Una página inexistente, bloqueada o sin filas parseables queda sin cobertura comprobada.

Los paquetes combinan dos vuelos directos, hotel y vehículo en destino para una estancia de 1–14 noches. Las tarifas de alojamiento y automóvil son estimaciones basadas en precios públicos, no cotizaciones de inventario para fechas específicas. La reserva y el cobro siguen siendo exclusivamente locales.

## Programación y vigencia

`INGEST_INTERVAL_SECONDS=86400` programa ciclos cada 24 horas desde el inicio del ciclo anterior. El primer arranque ejecuta una ingesta. El instante se persiste en `ingestion_cycles`, por lo que reiniciar un contenedor no dispara un ciclo nuevo cuando ya existe uno vigente. Un lock de PostgreSQL evita ciclos simultáneos; un ciclo interrumpido queda identificado y puede reiniciarse. La programación no exige mantener abierto el navegador.

- Snapshots frescos: caché de 30 minutos.
- Fallback de adquisición: snapshots reales de hasta 24 horas.
- Catálogo consultable y reservable: capturas de hasta 48 horas, dando margen al ciclo diario. Superado el plazo, desaparecen de consulta aunque se conservan en la base para auditoría.
- Vuelos con fecha pasada: excluidos usando el día de Colombia.
- `scrape_route_runs`: adquisición/parsing por fuente y dirección.
- `offer_observations`: precios observados por oferta y snapshot; su historial no sobrescribe capturas anteriores.

La interfaz muestra el último ciclo y refresca la información cada minuto. La ingesta de vuelos puede tardar decenas de minutos debido al pacing entre páginas.

## Fuentes de servicios por ciudad

| Ciudad | Hotel | Vehículos |
|---|---|---|
| BOG | GHL Collection 93 | National en Alkilautos Bogotá |
| MDE | GHL Portón Medellín | National en Alkilautos Medellín |
| CLO | Spiwak Chipichape, página oficial de habitaciones | National en Alkilautos Cali |
| CTG | GHL Relax Corales de Indias | National en Alkilautos Cartagena |
| SMR | GHL Relax Costa Azul | National en Alkilautos Santa Marta |

Las fuentes tienen adaptadores independientes; una falla no desactiva los servicios de otra ciudad. Sonesta Cali fue descartada por robots.txt. No se evaden bloqueos ni se incorporan precios de promociones como tarifas de habitación.

## Consultas e itinerario

`flightAvailability` y `travelAvailability` aceptan `startDate`/`endDate`. La interfaz ofrece hasta 90 fechas publicadas; la API admite hasta 366. `flightSearch` pagina vuelos directos con `limit` y `offset`, devuelve `totalCount` y `hasMore`. Diez ofertas son el tamaño inicial de página, no el máximo de exploración. Internamente se consultan páginas estables del servicio de vuelos; si se exceden 10.000 filas se solicita estrechar el rango.

Cada paquete devuelve `itinerary`, `warnings` y `priceBasis`. Los tramos muestran fecha, aeropuerto, horas observadas y duración cuando existen ambos timestamps. Si la fuente solo publica la fecha, las horas quedan por confirmar. Se advierte si la ida y el regreso requieren usar diferentes aeropuertos de Medellín.

## Checkout y recuperación

El servidor valida la ruta inversa, fechas, noches, destino de hotel y vehículo, vigencia y precio. Un importe cambiado requiere refrescar el paquete. `idempotencyKey` es obligatorio en checkout: repetir la misma solicitud devuelve la orden existente; reutilizar la clave con otros datos devuelve conflicto. La interfaz conserva la clave ante fallos de red, incluso después de recargar la pestaña.

Los holds son idempotentes por orden y oferta. Antes de compensar, la orden pasa a `COMPENSATING`; se recuperan los holds persistidos aunque su respuesta HTTP se haya perdido. Si una compensación falla se usa `COMPENSATION_PENDING`. El Order Service revisa cada 30 segundos operaciones interrumpidas con más de cinco minutos y vuelve a compensar. Una interrupción durante el cobro local cancela y revierte cualquier registro local de pago. No se integra una pasarela externa.

## Despliegue y verificación

Se aplican tablas adicionales mediante `db-bootstrap`; no se requiere eliminar los volúmenes.

```bash
docker compose build
docker compose up -d --force-recreate
pytest -q
python scripts/verify_project.py
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/demo_validation.py
```

El script demo crea un usuario y órdenes de demostración locales. No ejecuta reservas ni pagos externos. Los adaptadores respetan robots.txt, allowlists y pacing compartido. HTTP valida cada redirección antes de solicitarla.
