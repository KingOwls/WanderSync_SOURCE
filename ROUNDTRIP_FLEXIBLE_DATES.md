# WanderSync: ida y vuelta con fechas flexibles

Esta versión convierte las ofertas scrapeadas de CLIC y SATENA en un flujo de viaje completo Bogotá ↔ Medellín sin inventar fechas, precios ni disponibilidad.

## Rutas reales

Cada fuente captura dos páginas públicas: `BOG → EOH` y `EOH → BOG`. El usuario sigue eligiendo Medellín como `MDE`; el Gateway resuelve `MDE` a los aeropuertos `[MDE, EOH]` solo durante la consulta. Los registros scrapeados permanecen fieles a la fuente y conservan `EOH`.

## travelAvailability

La consulta GraphQL `travelAvailability` devuelve hasta **8** fechas reales de salida, hasta **8** fechas reales de regreso y hasta 12 recomendaciones. Solo son válidas combinaciones de **1–14 noches**. Si una fuente publica menos de ocho fechas, WanderSync devuelve únicamente ese subconjunto real.

```graphql
query {
  travelAvailability(origin:"BOG", destination:"MDE", outboundLimit:8, returnLimit:8) {
    airportCodes outboundDates returnDates
    combinations { departureDate returnDate nights lowestFlightTotal }
  }
}
```

## Paquetes ida + vuelta

`travelPackages` usa la fecha exacta seleccionada para buscar un `outboundFlight` y un `returnFlight`. Puede combinar CLIC/SATENA por pierna. El total es:

`ida + regreso + hotel × noches + auto × noches`.

No se convierten monedas; todos los componentes del paquete deben estar en COP.

## SAGA

El checkout reserva localmente: `outbound_flight → return_flight → hotel → car → billing`. Si falla `return_flight`, se compensa el hold de `outbound_flight` y la orden queda cancelada sin cobro. Los holds son internos de WanderSync: **no realiza reservas en los proveedores externos**.

## Evidencia sugerida

1. `scripts/scraping_study.sql` para mostrar precios, fechas y direcciones por fuente.
2. `travelAvailability` para demostrar las fechas reales publicadas.
3. `travelPackages` para demostrar cruces CLIC/SATENA.
4. `scripts/demo_validation.py` para happy path y compensación del vuelo de regreso.
