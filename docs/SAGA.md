# Patrón SAGA

WanderSync usa **SAGA por orquestación**. `order-service` conoce el proceso y conserva la secuencia de acciones/compensaciones en `saga_events`.

## Happy path

```mermaid
sequenceDiagram
  participant G as GraphQL Gateway
  participant O as Order Service
  participant F as Flight
  participant H as Hotel
  participant C as Car
  participant B as Billing

  G->>O: checkout
  O->>F: reserve flight
  F-->>O: confirmed
  O->>H: reserve hotel
  H-->>O: confirmed
  O->>C: reserve car
  C-->>O: confirmed
  O->>B: charge
  B-->>O: paid
  O-->>G: CONFIRMED
```

## Falla en vehículo y compensación

```mermaid
sequenceDiagram
  participant G as GraphQL Gateway
  participant O as Order Service
  participant F as Flight
  participant H as Hotel
  participant C as Car

  G->>O: checkout(simulateFailure: "car")
  O->>F: reserve
  F-->>O: confirmed F1
  O->>H: reserve
  H-->>O: confirmed H1
  O->>C: reserve (forced failure)
  C--xO: 503
  O->>H: cancel H1
  H-->>O: CANCELLED
  O->>F: cancel F1
  F-->>O: CANCELLED
  O-->>G: CANCELLED / NOT_CHARGED
```

## Fallas disponibles para demo

- `flight`: falla antes de confirmar recursos.
- `hotel`: compensa vuelo.
- `car`: compensa hotel y vuelo.
- `billing`: compensa auto, hotel y vuelo.

Las fallas solo se aceptan cuando `ALLOW_FAILURE_INJECTION=true`.

## SAGA de dos vuelos

El orden aprobado es `outbound_flight → return_flight → hotel → car → billing`. Una falla inyectada como `return_flight` debe compensar el hold de `outbound_flight`. Los dos vuelos son WanderSync Local Holds y el sistema no realiza reservas en los proveedores externos.
