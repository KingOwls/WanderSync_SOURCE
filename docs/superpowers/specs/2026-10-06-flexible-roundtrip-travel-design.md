# Flexible Round-Trip Travel Design

## Goal

Extend WanderSync's proven real-scraping pipeline so the demo can build real Bogotá ↔ Medellín round-trip packages from CLIC and SATENA offers, expose up to eight scraped outbound dates and eight scraped return dates, resolve the Medellín city selection to the real EOH airport used by the flight sources, and price/book a package using both flight legs plus hotel and car.

The scraping architecture already validated in production-like runs remains intact: CLIC/SATENA use respectful public HTTP collection with snapshots/cache, GHL and Alkilautos use Playwright, Prefect orchestrates, Dask executes distributed work, PostgreSQL persists, and GraphQL is the only frontend API.

## Success criteria

1. CLIC and SATENA each scrape both `BOG → EOH` and `EOH → BOG` from their public route pages.
2. Only real one-way offers published by the sources are persisted as flight inventory. No date, price, airport, or availability value is invented.
3. The catalog exposes up to 8 distinct outbound dates and up to 8 distinct return dates for the Bogotá ↔ Medellín demo route. If fewer than 8 real dates exist, only the available dates are returned.
4. The user may continue selecting Medellín as `MDE` in the UI while GraphQL resolves that city to flight airports `[MDE, EOH]`; scraped flight rows remain unchanged as `EOH`.
5. Return dates must be after departure dates. Valid trip duration is 1–14 nights.
6. GraphQL returns the best valid round-trip combinations, ranked by flight total first and package total when hotel/car prices are included.
7. A round-trip package price is `outbound flight + return flight + nightly hotel × nights + daily car × nights` and all prices must be COP.
8. Checkout/SAGA reserves and compensates both flight legs, not only the outbound leg.
9. Existing successful scraping for GHL and Alkilautos is unchanged.
10. Wingo remains disabled by default and is not part of the demo path.

## Public flight sources

### CLIC

Outbound page:
`https://clicair.co/destinos-colombia/es/vuelos-desde-bogota-a-medellin`

Return page:
`https://clicair.co/destinos-colombia/es/vuelos-desde-medellin-a-bogota`

Both pages expose a public table with the columns `Desde`, `Hasta`, `Tipo de vuelo`, `Fecha`, and `Precio`. The persisted production offers are restricted to rows whose trip type is `Solo ida`.

### SATENA

Outbound page:
`https://rutas-destinos.satena.com/es/vuelos-baratos-desde-bogota-a-medellin`

Return page:
`https://rutas-destinos.satena.com/es/vuelos-baratos-desde-medellin-a-bogota`

The same `Desde / Hasta / Tipo de vuelo / Fecha / Precio` contract is used. Production persistence is restricted to `Solo ida` offers.

## Ingestion changes

### Multi-request source execution

The current ingestion flow calls `adapter.build_requests()[0]`; this must be replaced by request-batch execution.

Each CLIC/SATENA adapter returns two `ScrapeRequest` values:

- outbound metadata: `{origin: "BOG", destination: "EOH", direction: "outbound"}`
- return metadata: `{origin: "EOH", destination: "BOG", direction: "return"}`

For each adapter run:

1. collect every request independently through the existing cache/robots/pacing collector;
2. register each real snapshot;
3. parse each snapshot independently;
4. normalize all valid rows;
5. combine the rows for that source;
6. persist them as one source refresh.

This prevents the existing `UPDATE flights SET active=FALSE WHERE source=%s` behavior from deactivating one direction while the other direction is being persisted.

A source run succeeds when at least one request yields valid real data. Request-level failures are retained as diagnostics in run metadata/logs; no failed route creates synthetic rows.

## Flight persistence

No new column is required to distinguish outbound and return flights because the persisted `origin` and `destination` already encode direction.

The existing stable flight identity continues to include source/route/date/price so outbound and return offers cannot collide.

When refreshing a flight source:

1. mark existing rows from that source inactive once;
2. upsert the combined normalized rows from every successful request;
3. reactivate only rows observed in the current refresh.

Cached or stale-fallback snapshots remain acceptable because they contain previously captured real public HTML.

## City and airport resolution

Introduce a small query-layer resolver, not a normalization rewrite.

Initial demo mapping:

```text
BOG -> flight airports [BOG], lodging/car city BOG
MDE -> flight airports [MDE, EOH], lodging/car city MDE
```

The frontend continues to display `Medellín (MDE)` because that is the user-facing city selector already used for hotels and cars. Flight rows stay faithful to the external sources and therefore remain `EOH` when the source says EOH.

This resolver must be isolated so additional airport/city mappings can be added later without changing scraping or stored source data.

## GraphQL availability API

Add a query conceptually equivalent to:

```graphql
travelAvailability(
  origin: String!
  destination: String!
  outboundLimit: Int! = 8
  returnLimit: Int! = 8
): TravelAvailability!
```

The result contains:

- normalized user-facing origin/destination cities;
- airport codes actually found in scraped offers;
- up to 8 distinct outbound dates sorted ascending;
- up to 8 distinct return dates sorted ascending;
- total outbound offer count;
- total return offer count;
- a bounded list of recommended valid date combinations.

A recommended date combination contains:

- `departureDate`
- `returnDate`
- `nights`
- `lowestOutboundPrice`
- `lowestReturnPrice`
- `lowestFlightTotal`

Rules:

- `returnDate > departureDate`;
- nights between 1 and 14 inclusive;
- only dates actually present in active scraped flight rows;
- no more than 12 recommended combinations returned;
- combinations sorted by `lowestFlightTotal`, then departure date, then return date.

## Round-trip packages

Change `TravelPackage` from one flight to two explicit legs:

- `outboundFlight`
- `returnFlight`
- `hotel`
- `car`
- `nights`
- `flightTotal`
- `total`

`travelPackages(origin, destination, startDate, endDate, limit)` keeps its external argument shape for frontend simplicity.

The resolver:

1. resolves origin and destination cities to acceptable flight airport sets;
2. fetches active outbound offers for the exact selected start date;
3. fetches active return offers for the exact selected end date in the reverse direction;
4. fetches destination hotels and cars by city code;
5. rejects trips outside 1–14 nights;
6. filters every component to COP;
7. creates combinations across airlines so CLIC/SATENA can mix by leg;
8. ranks by total package price;
9. returns at most 12 packages.

Examples of valid flight pairs include:

- CLIC outbound + CLIC return
- CLIC outbound + SATENA return
- SATENA outbound + CLIC return
- SATENA outbound + SATENA return

No combination is created unless both flight rows exist in PostgreSQL.

## Flight service API

Extend the existing `/flights` endpoint so the gateway can query:

- multiple destination airports;
- exact `travel_date`;
- reverse direction for returns.

Prefer a backward-compatible query contract. Existing callers using single `origin` and `destination` continue to work.

The service must return only `active=TRUE` rows and must preserve source provenance fields.

## Checkout and SAGA

A displayed round-trip package must be reservable as a round trip.

Extend the checkout input and order representation from one flight to two legs:

- `outbound_flight_id`
- `return_flight_id`

The SAGA sequence becomes:

1. create local order;
2. hold outbound flight;
3. hold return flight;
4. hold hotel;
5. hold car;
6. authorize payment;
7. confirm order.

Compensation occurs in reverse order for every completed hold. If holding the return flight fails, the outbound hold must be released. Existing local-hold semantics remain academic/local and must not be represented as a reservation made with CLIC or SATENA.

Database migration must be idempotent for existing volumes. The current single `flight_id` field may be retained temporarily for backward compatibility only if existing historical orders require it, but new round-trip orders must store both explicit leg IDs.

## Frontend behavior

### Bootstrap

The frontend no longer invents `tomorrow(+2)` and `tomorrow(+6)` when no exact `MDE` airport offer is found.

On startup or route change:

1. call `travelAvailability(BOG, MDE)`;
2. select the first recommended combination when available;
3. set the departure and return controls from real scraped dates.

### Date controls

Show up to 8 outbound dates as selectable recommendations.

After selecting an outbound date, show only valid return dates that:

- exist in scraped return offers;
- occur after the selected departure;
- produce a stay of 1–14 nights.

The native date inputs may remain for manual selection, but unsupported values must not silently produce an empty UX. When an unsupported date is entered, show the nearest actual scraped choices.

### Package results

Each result card shows:

- outbound airline, route, date, price, source;
- return airline, route, date, price, source;
- hotel nightly price and nights;
- car daily price and nights;
- flight subtotal;
- complete package total;
- provenance/scraped timestamps already available in the model.

Recommended combinations should make it visible when mixing airlines produces the lower total.

## Error handling

- Fewer than 8 scraped dates is not an error; return the real subset.
- No outbound offers: availability returns empty outbound dates and no combinations.
- Outbound offers but no valid return date: preserve outbound dates and return an empty recommendation list.
- One airline unavailable: use the other airline's active rows.
- One route snapshot stale-fallback: it remains eligible because it is a prior real snapshot; provenance/status stays visible through scrape runs.
- Currency mismatch: exclude that component from package calculation rather than converting or inventing a rate.
- Manual date not published: return no exact package plus real alternative dates.

## Testing

### Ingestion

- CLIC adapter returns two route requests with correct metadata.
- SATENA adapter returns two route requests with correct metadata.
- A source refresh persists outbound and return rows together.
- Refreshing a source does not deactivate the opposite direction.
- One failed route request does not erase valid rows from the other direction.

### Query layer

- `MDE` resolves flight queries to `MDE` and `EOH` while hotel/car stay `MDE`.
- Availability returns at most 8 unique dates per direction.
- Return dates before/equal to departure are rejected from recommendations.
- 1-night and 14-night trips are valid; 0-night and 15-night trips are invalid.
- Recommended combinations contain only actual rows and are price-sorted.
- A single surviving airline still produces availability/packages.

### Package calculation

- total includes both flight legs exactly once;
- hotel and car are multiplied by nights;
- mixed-airline combinations are supported;
- non-COP components are excluded.

### SAGA

- happy path holds outbound + return + hotel + car before payment;
- return hold failure compensates outbound hold;
- later failure compensates both flight legs plus any subsequent holds already completed.

### Frontend

- bootstraps from real availability rather than tomorrow dates;
- renders up to 8 outbound options;
- return recommendations update after outbound selection;
- unsupported manual dates show real alternatives;
- round-trip cards show both legs and correct total.

## Demonstration sequence

1. Show `scrape_runs` with CLIC/SATENA SUCCESS or CACHED.
2. Show outbound and return HTML snapshots for both sources.
3. Query PostgreSQL for active `BOG → EOH` and `EOH → BOG` rows.
4. Run `travelAvailability(BOG, MDE)` and show up to 8 real dates in each direction.
5. Select a recommended combination in the frontend.
6. Show multiple package cards, including mixed-airline options where available.
7. Show package total including both flight legs.
8. Run one successful checkout and one injected SAGA failure demonstrating compensation of both flight holds.

## Scope exclusions

This iteration intentionally does not:

- add additional destination cities beyond the existing Bogotá ↔ Medellín demonstration;
- scrape booking engines or perform external airline reservations;
- infer unavailable departure/arrival times;
- create synthetic offers to reach exactly 8 dates;
- convert currencies;
- re-enable Wingo by default;
- modify the already working GHL or Alkilautos collectors/parsers.

## Files expected to change

Primary implementation surfaces:

- `ingestion/sources/flights_clic.py`
- `ingestion/sources/flights_satena.py`
- `ingestion/flow.py`
- `backend/flight_service/main.py`
- `backend/gateway/main.py`
- `backend/order_service/main.py`
- `backend/common/reservation.py` if local-hold interfaces require two flight legs
- `schema/init.sql`
- `schema.graphql`
- `frontend/src/main.jsx`
- `frontend/src/styles.css`
- focused tests under `tests/`
- demo/verification documentation

No change is expected to the GHL/Alkilautos source adapters or parsers.
