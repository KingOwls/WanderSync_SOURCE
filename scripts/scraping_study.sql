\echo '=== 1. Runs por fuente y estado ==='
SELECT source, kind, status, COUNT(*) AS runs, SUM(items_found) AS items_reported
FROM scrape_runs
GROUP BY source, kind, status
ORDER BY source, status;

\echo '=== 2. Ofertas activas por ruta turistica y fuente ==='
WITH mapped_flights AS (
  SELECT
    source,
    airline,
    CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END AS tourist_origin,
    CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END AS tourist_destination,
    travel_date,
    price,
    currency,
    snapshot_id,
    scraped_at
  FROM flights
  WHERE active = TRUE
)
SELECT source, airline, tourist_origin, tourist_destination,
       COUNT(*) AS offers,
       MIN(price) AS min_price,
       ROUND(AVG(price), 2) AS avg_price,
       MAX(price) AS max_price,
       MIN(travel_date) AS first_date,
       MAX(travel_date) AS last_date
FROM mapped_flights
WHERE tourist_origin <> tourist_destination
GROUP BY source, airline, tourist_origin, tourist_destination
ORDER BY tourist_origin, tourist_destination, source, airline;

\echo '=== 3. Grafo dirigido activo consolidado por ciudad turistica ==='
WITH mapped_flights AS (
  SELECT
    CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END AS tourist_origin,
    CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END AS tourist_destination,
    source,
    travel_date,
    price
  FROM flights
  WHERE active = TRUE
)
SELECT tourist_origin, tourist_destination,
       COUNT(*) AS offer_count,
       COUNT(DISTINCT source) AS source_count,
       ARRAY_AGG(DISTINCT source ORDER BY source) AS sources,
       MIN(price) AS min_price,
       ROUND(AVG(price), 2) AS avg_price,
       MAX(price) AS max_price,
       MIN(travel_date) AS first_date,
       MAX(travel_date) AS last_date
FROM mapped_flights
WHERE tourist_origin <> tourist_destination
GROUP BY tourist_origin, tourist_destination
ORDER BY tourist_origin, tourist_destination;

\echo '=== 4. Pares de ciudades con ida y regreso activos ==='
WITH directed AS (
  SELECT DISTINCT
    CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END AS tourist_origin,
    CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END AS tourist_destination
  FROM flights
  WHERE active = TRUE
), roundtrips AS (
  SELECT d.tourist_origin AS origin, d.tourist_destination AS destination
  FROM directed d
  JOIN directed r
    ON r.tourist_origin = d.tourist_destination
   AND r.tourist_destination = d.tourist_origin
  WHERE d.tourist_origin <> d.tourist_destination
)
SELECT origin, destination
FROM roundtrips
ORDER BY origin, destination;

\echo '=== 5. Destinos con capacidad actual de paquete ==='
WITH directed AS (
  SELECT DISTINCT
    CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END AS tourist_origin,
    CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END AS tourist_destination
  FROM flights
  WHERE active = TRUE
), roundtrips AS (
  SELECT d.tourist_origin AS origin, d.tourist_destination AS destination
  FROM directed d
  JOIN directed r
    ON r.tourist_origin = d.tourist_destination
   AND r.tourist_destination = d.tourist_origin
  WHERE d.tourist_origin <> d.tourist_destination
), service_flags AS (
  SELECT city,
         EXISTS (SELECT 1 FROM hotels h WHERE h.active = TRUE AND h.city = c.city) AS hotel_available,
         EXISTS (SELECT 1 FROM cars a WHERE a.active = TRUE AND a.city = c.city) AS car_available
  FROM (SELECT DISTINCT tourist_destination AS city FROM directed) c
)
SELECT r.origin, r.destination,
       s.hotel_available,
       s.car_available,
       (s.hotel_available AND s.car_available) AS package_capable
FROM roundtrips r
JOIN service_flags s ON s.city = r.destination
ORDER BY r.origin, r.destination;

\echo '=== 6. Fechas reales por ruta y fuente ==='
WITH mapped_flights AS (
  SELECT
    source,
    CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END AS tourist_origin,
    CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END AS tourist_destination,
    travel_date,
    price
  FROM flights
  WHERE active = TRUE
)
SELECT source, tourist_origin, tourist_destination, travel_date,
       MIN(price) AS lowest_price,
       COUNT(*) AS offers
FROM mapped_flights
WHERE tourist_origin <> tourist_destination
GROUP BY source, tourist_origin, tourist_destination, travel_date
ORDER BY tourist_origin, tourist_destination, travel_date, source;

\echo '=== 7. Muestra de vuelos activos con procedencia ==='
SELECT source, airline, origin, destination, travel_date, price, currency,
       source_url, snapshot_id, scraped_at
FROM flights
WHERE active = TRUE
ORDER BY source, origin, destination, travel_date, price
LIMIT 100;

\echo '=== 8. Snapshots recientes ==='
SELECT id, source, kind, source_url, captured_at, status, snapshot_path
FROM scrape_snapshots
ORDER BY captured_at DESC
LIMIT 40;

\echo '=== 9. Ultimos runs ==='
SELECT id, source, kind, status, items_found, snapshot_id, error_message
FROM scrape_runs
ORDER BY id DESC
LIMIT 50;

\echo '=== 10. Cobertura de las 20 direcciones objetivo (read model, cap visible=10) ==='
WITH cities(code) AS (
  VALUES ('BOG'),('MDE'),('CLO'),('CTG'),('SMR')
), pairs AS (
  SELECT a.code AS origin, b.code AS destination
  FROM cities a CROSS JOIN cities b
  WHERE a.code <> b.code
), mapped AS (
  SELECT
    CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END AS origin,
    CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END AS destination,
    source, travel_date, price
  FROM flights WHERE active=TRUE
), counts AS (
  SELECT origin, destination, COUNT(*) AS raw_count
  FROM mapped WHERE origin <> destination GROUP BY origin,destination
), latest_source AS (
  SELECT DISTINCT ON (source) source,status
  FROM scrape_runs
  WHERE source IN ('clicair','satena','jetsmart','wingo')
  ORDER BY source,id DESC
), health AS (
  SELECT COUNT(*) FILTER (WHERE status IN ('SUCCESS','CACHED','STALE_FALLBACK')) AS available_sources
  FROM latest_source
)
SELECT p.origin,p.destination,
       COALESCE(c.raw_count,0) AS raw_count,
       LEAST(COALESCE(c.raw_count,0),10) AS visible_count,
       CASE
         WHEN COALESCE(c.raw_count,0) >= 10 THEN 'AVAILABLE'
         WHEN COALESCE(c.raw_count,0) > 0 THEN 'PARTIAL'
         WHEN (SELECT available_sources FROM health) = 4 THEN 'NO_OFFERS'
         ELSE 'SOURCE_UNAVAILABLE'
       END AS coverage_status
FROM pairs p
LEFT JOIN counts c USING(origin,destination)
ORDER BY p.origin,p.destination;

\echo '=== 11. Totales de estados de cobertura ==='
WITH cities(code) AS (VALUES ('BOG'),('MDE'),('CLO'),('CTG'),('SMR')),
pairs AS (SELECT a.code origin,b.code destination FROM cities a CROSS JOIN cities b WHERE a.code<>b.code),
mapped AS (
 SELECT CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END origin,
        CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END destination
 FROM flights WHERE active=TRUE
), counts AS (SELECT origin,destination,COUNT(*) raw_count FROM mapped WHERE origin<>destination GROUP BY 1,2),
latest_source AS (
 SELECT DISTINCT ON (source) source,status FROM scrape_runs
 WHERE source IN ('clicair','satena','jetsmart','wingo') ORDER BY source,id DESC
), health AS (SELECT COUNT(*) FILTER (WHERE status IN ('SUCCESS','CACHED','STALE_FALLBACK')) available_sources FROM latest_source),
coverage AS (
 SELECT CASE WHEN COALESCE(c.raw_count,0)>=10 THEN 'AVAILABLE'
             WHEN COALESCE(c.raw_count,0)>0 THEN 'PARTIAL'
             WHEN (SELECT available_sources FROM health)=4 THEN 'NO_OFFERS'
             ELSE 'SOURCE_UNAVAILABLE' END status
 FROM pairs p LEFT JOIN counts c USING(origin,destination)
)
SELECT status,COUNT(*) directions FROM coverage GROUP BY status ORDER BY status;

\echo '=== 12. Pares sin directo con camino candidato de una escala (NO garantiza horario) ==='
WITH mapped AS (
 SELECT DISTINCT
   CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END origin,
   CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END destination,
   travel_date
 FROM flights WHERE active=TRUE
), candidate_connections AS (
 SELECT a.origin, b.destination, a.destination AS via, a.travel_date
 FROM mapped a JOIN mapped b
   ON a.destination=b.origin AND a.travel_date=b.travel_date
 WHERE a.origin<>b.destination
   AND a.origin<>a.destination
   AND b.origin<>b.destination
   AND a.destination<>a.origin
   AND a.destination<>b.destination
   AND NOT EXISTS (
     SELECT 1 FROM mapped d
     WHERE d.origin=a.origin AND d.destination=b.destination AND d.travel_date=a.travel_date
   )
)
SELECT origin,destination,via,travel_date,COUNT(*) AS candidate_paths
FROM candidate_connections
GROUP BY origin,destination,via,travel_date
ORDER BY origin,destination,travel_date,via;

\echo '=== 13. Precio directo min/avg/max por fuente y ruta ==='
WITH mapped AS (
 SELECT source,
   CASE WHEN origin IN ('EOH','MDE') THEN 'MDE' ELSE origin END origin,
   CASE WHEN destination IN ('EOH','MDE') THEN 'MDE' ELSE destination END destination,
   price
 FROM flights WHERE active=TRUE
)
SELECT source,origin,destination,MIN(price),ROUND(AVG(price),2),MAX(price),COUNT(*) offers
FROM mapped WHERE origin<>destination
GROUP BY source,origin,destination
ORDER BY origin,destination,source;

\echo '=== 14. Fuentes productivas y ultimo run ==='
SELECT s.source,r.status,r.items_found,r.finished_at
FROM (VALUES ('clicair'),('satena'),('jetsmart'),('wingo')) s(source)
LEFT JOIN LATERAL (
 SELECT status,items_found,finished_at FROM scrape_runs
 WHERE source=s.source ORDER BY id DESC LIMIT 1
) r ON TRUE
ORDER BY s.source;

\echo '=== 15. Baseline previo a JetSMART/Wingo ==='
SELECT 77 AS baseline_active_flight_rows,
       10 AS baseline_directed_routes,
       5 AS baseline_bidirectional_pairs,
       20 AS target_directed_directions,
       10 AS target_visible_offers_per_direction;
