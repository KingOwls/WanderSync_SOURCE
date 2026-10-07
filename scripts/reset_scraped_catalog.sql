-- Development-only cleanup. Preserves user accounts while clearing scraped catalog and demo transactions.
TRUNCATE TABLE billing_events, saga_events, orders,
    flight_reservations, hotel_reservations, car_reservations,
    flights, hotels, cars, scrape_runs, scrape_snapshots
RESTART IDENTITY CASCADE;
