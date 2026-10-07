# API GraphQL

El contrato legible completo está en `schema.graphql`. GraphiQL queda disponible en `http://localhost:8000/graphql`.

## Sesión

```graphql
query {
  sessionInfo { authenticated sessionPrefix createdAt rotatedAt userEmail }
  me { id email fullName }
}
```

## Red turística activa

El frontend no mantiene una lista fija de ciudades. Consulta `travelNetwork`, construido a partir de vuelos `active=TRUE`:

```graphql
query {
  travelNetwork {
    cities { code name airports }
    routes {
      origin destination offerCount sources
      outboundAvailable roundTripAvailable packageAvailable
      firstDate lastDate lowestPrice
    }
  }
}
```

`MDE` representa Medellín como ciudad turística y puede consolidar vuelos publicados con `MDE` o `EOH`. Una ruta configurada en el registry no aparece si no hay ofertas activas.

## Explorar vuelos por fecha scrapeada

```graphql
query($origin:String!,$destination:String!,$date:String!){
  flightOffers(origin:$origin,destination:$destination,travelDate:$date,limit:50) {
    id airline origin destination travelDate price currency
    source sourceUrl snapshotId scrapedAt
  }
}
```

`travelDate` debe seleccionarse desde `travelAvailability`; no se inventan fechas.

## Disponibilidad flexible ida/vuelta

```graphql
query($origin:String!,$destination:String!){
  travelAvailability(origin:$origin,destination:$destination,outboundLimit:8,returnLimit:8) {
    airportCodes
    outboundDates
    returnDates
    combinations { departureDate returnDate nights lowestFlightTotal }
  }
}
```

La consulta devuelve hasta 8 fechas reales por dirección y hasta 12 combinaciones de 1–14 noches. Si solo existe ida, `outboundDates` puede tener valores mientras `returnDates`/`combinations` quedan vacíos.

## Buscar paquetes ida + vuelta

Use una combinación real y una ruta con `packageAvailable=true`:

```graphql
query($origin:String!,$destination:String!,$start:String!,$end:String!){
  travelPackages(
    origin:$origin,
    destination:$destination,
    startDate:$start,
    endDate:$end,
    limit:12
  ) {
    nights total flightTotal
    outboundFlight { id airline travelDate price currency source sourceUrl snapshotId scrapedAt }
    returnFlight { id airline travelDate price currency source sourceUrl snapshotId scrapedAt }
    hotel { id name roomType nightlyPrice currency source sourceUrl snapshotId scrapedAt }
    car { id provider model dailyPrice currency source sourceUrl snapshotId scrapedAt }
  }
}
```

El total se compone de vuelo de ida + vuelo de regreso + hotel × noches + auto × noches.

## Reservar paquete académico

Tome los IDs del paquete retornado por GraphQL:

```graphql
mutation {
  checkoutPackage(
    outboundFlightId:"ID-REAL-IDA",
    returnFlightId:"ID-REAL-REGRESO",
    hotelId:"ID-REAL-HOTEL",
    carId:"ID-REAL-AUTO",
    nights:3,
    total:100000
  ) {
    id status paymentStatus total failureReason
  }
}
```

`total` enviado por el cliente es informativo. Order Service recalcula el precio autoritativo a partir de ofertas activas.

## Falla controlada en regreso

```graphql
mutation {
  checkoutPackage(
    outboundFlightId:"ID-REAL-IDA",
    returnFlightId:"ID-REAL-REGRESO",
    hotelId:"ID-REAL-HOTEL",
    carId:"ID-REAL-AUTO",
    nights:3,
    total:100000,
    simulateFailure:"return_flight"
  ) {
    id status paymentStatus failureReason
  }
}
```

## Trazabilidad SAGA

```graphql
query {
  sagaEvents(orderId:"UUID-DE-LA-ORDEN") { step action status detail createdAt }
}
```

Las reservas son **WanderSync Local Hold**. WanderSync no realiza reservas en los proveedores externos.

## Cobertura multi-ciudad y búsqueda de vuelos

`travelNetwork` siempre expone las cinco ciudades y sus **20 direcciones**. Cada ruta incluye `coverageStatus`, `visibleOfferCount` (máximo **10 ofertas**), `rawOfferCount`, `sourcesChecked` y `sourcesAvailable`. Los estados son `AVAILABLE`, `PARTIAL`, `NO_OFFERS` y `SOURCE_UNAVAILABLE`.

`flightAvailability(origin,destination)` devuelve fechas obtenidas exclusivamente de ofertas directas o candidatos de conexión reales. `flightSearch(origin,destination,travelDate)` devuelve `directOffers` primero y, si no hay directos, hasta cinco conexiones sugeridas derivadas de dos legs activos de la misma fecha.

`sourceHealth` resume CLIC, SATENA, JetSMART y Wingo. LATAM no forma parte del pool productivo por `ROBOTS_DISALLOWED`.

Las conexiones muestran **Verifica los horarios exactos con las aerolíneas.** y no se usan para `travelPackages` ni checkout. Los paquetes continúan direct-only.
