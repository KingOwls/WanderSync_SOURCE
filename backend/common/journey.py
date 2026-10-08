"""Pure itinerary validation shared by checkout and presentation."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

CITY_AIRPORTS = {"BOG": "BOG", "MDE": "MDE", "EOH": "MDE", "CLO": "CLO", "CTG": "CTG", "SMR": "SMR"}

def as_datetime(value):
    if not value:
        return None
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Flight times require a timezone")
    return result

def validate_journey(outbound, returning, hotel, car, nights, today=None):
    today = today or datetime.now(ZoneInfo("America/Bogota")).date()
    origin = CITY_AIRPORTS.get(outbound["origin"])
    destination = CITY_AIRPORTS.get(outbound["destination"])
    if not origin or not destination or origin == destination:
        raise ValueError("Unsupported or identical origin and destination")
    if CITY_AIRPORTS.get(returning["origin"]) != destination or CITY_AIRPORTS.get(returning["destination"]) != origin:
        raise ValueError("Return flight must reverse the outbound route")
    start, end = date.fromisoformat(str(outbound["travel_date"])), date.fromisoformat(str(returning["travel_date"]))
    if start < today or (end - start).days != nights or not 1 <= nights <= 14:
        raise ValueError("Flight dates must match the requested stay of 1–14 nights")
    if hotel["city"] != destination or car["city"] != destination:
        raise ValueError("Hotel and car must belong to the destination city")
    out_arrival = as_datetime(outbound.get("arrival_at"))
    back_departure = as_datetime(returning.get("departure_at"))
    for flight in (outbound, returning):
        departure, arrival = as_datetime(flight.get("departure_at")), as_datetime(flight.get("arrival_at"))
        if departure and departure.astimezone(ZoneInfo("America/Bogota")).date() != date.fromisoformat(str(flight["travel_date"])):
            raise ValueError("Departure timestamp does not match flight date")
        if departure and arrival and arrival <= departure:
            raise ValueError("Flight arrival must follow departure")
    if out_arrival and back_departure and back_departure <= out_arrival:
        raise ValueError("Return departure must follow outbound arrival")

def itinerary(outbound, returning, nights):
    events = []
    for label, flight in (("Ida", outbound), ("Regreso", returning)):
        departure, arrival = as_datetime(flight.get("departure_at")), as_datetime(flight.get("arrival_at"))
        duration = int((arrival - departure).total_seconds() / 60) if departure and arrival else None
        events.append({"label": label, "date": str(flight["travel_date"]), "origin": flight["origin"], "destination": flight["destination"],
                       "departure_at": str(flight.get("departure_at")) if flight.get("departure_at") else None,
                       "arrival_at": str(flight.get("arrival_at")) if flight.get("arrival_at") else None,
                       "duration_minutes": duration, "time_confirmed": bool(departure and arrival)})
    warnings = ["Tarifas públicas estimadas; confirma disponibilidad, horarios e impuestos con los proveedores."]
    if not all(e["time_confirmed"] for e in events):
        warnings.append("Horarios por confirmar: la fuente solo publica fechas.")
    if outbound["destination"] != returning["origin"]:
        warnings.append("El regreso usa otro aeropuerto: debes prever el traslado entre aeropuertos.")
    if outbound["origin"] != returning["destination"]:
        warnings.append("La llegada del regreso usa otro aeropuerto de la ciudad de origen.")
    return events, warnings
