from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import pytest
from backend.common.journey import validate_journey, itinerary
from backend.gateway.travel_logic import build_availability
from backend.gateway.route_coverage import select_direction_offers

def rows():
    return ({"origin":"BOG","destination":"EOH","travel_date":"2030-01-10"},
            {"origin":"MDE","destination":"BOG","travel_date":"2030-01-13"}, {"city":"MDE"}, {"city":"MDE"})

def test_valid_journey_and_airport_transfer_warning():
    out, back, hotel, car = rows()
    validate_journey(out, back, hotel, car, 3, today=date(2030,1,1))
    legs, warnings = itinerary(out, back, 3)
    assert len(legs) == 2 and all(not leg["time_confirmed"] for leg in legs)
    assert any("otro aeropuerto" in w for w in warnings)

@pytest.mark.parametrize("field,value", [("origin","CTG"),("destination","CLO"),("travel_date","2030-01-11")])
def test_rejects_incompatible_return(field,value):
    out, back, hotel, car = rows(); back[field] = value
    with pytest.raises(ValueError): validate_journey(out,back,hotel,car,3,today=date(2030,1,1))

def test_rejects_wrong_city_expired_date_and_invalid_hours():
    out, back, hotel, car = rows()
    with pytest.raises(ValueError): validate_journey(out,back,{"city":"CLO"},car,3,today=date(2030,1,1))
    with pytest.raises(ValueError): validate_journey(out,back,hotel,car,3,today=date(2030,1,11))
    out.update(departure_at="2030-01-10T12:00:00-05:00", arrival_at="2030-01-10T11:00:00-05:00")
    with pytest.raises(ValueError): validate_journey(out,back,hotel,car,3,today=date(2030,1,1))

def test_observed_duration_preserved():
    out, back, _, _ = rows()
    out.update(departure_at="2030-01-10T12:00:00-05:00",arrival_at="2030-01-10T13:15:00-05:00")
    legs, _ = itinerary(out,back,3)
    assert legs[0]["duration_minutes"] == 75
    assert legs[0]["time_confirmed"] is True

def test_extended_availability_and_offer_selection_do_not_truncate_to_ten():
    rows = [{"id":str(i),"source":"wingo","origin":"BOG","destination":"MDE","price":100+i,"currency":"COP","travel_date":(date(2030,1,1)+timedelta(days=i)).isoformat()} for i in range(60)]
    result = build_availability(rows,rows,90,90)
    assert len(result.outbound_dates) == 60
    assert len(select_direction_offers(rows,origin="BOG",destination="MDE",limit=100)) == 60
    assert len(select_direction_offers(rows,origin="BOG",destination="MDE")) == 10

def test_city_service_registry_has_independent_adapters_for_every_city(monkeypatch):
    from ingestion.sources.registry import get_enabled_adapters
    monkeypatch.delenv("SCRAPE_ENABLED_SOURCES",raising=False)
    adapters = get_enabled_adapters()
    for kind in ("hotels","cars"):
        assert {a.build_requests()[0].query["city"] for a in adapters if a.kind == kind} == {"BOG","MDE","CLO","CTG","SMR"}

def test_daily_schedule_uses_persisted_start(monkeypatch):
    import ingestion.runner as runner
    import psycopg
    now = datetime(2030,1,1,tzinfo=timezone.utc)
    class Result:
        def fetchone(self): return (now-timedelta(hours=23),)
    class Conn:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def execute(self,*a): return Result()
    monkeypatch.setattr(psycopg,"connect",lambda *a,**k:Conn())
    monkeypatch.setattr(runner,"INTERVAL",86400)
    assert runner.seconds_until_next_run(now) == 3600

def test_persisted_pacing_survives_process_memory_reset(tmp_path,monkeypatch):
    from ingestion.policies import pacing
    monkeypatch.setattr(pacing.time,"time",lambda:1000)
    monkeypatch.setattr(pacing.random,"uniform",lambda a,b:90)
    pacing.mark_shared_source_run("wingo",tmp_path)
    pacing._LAST_RUN.clear()
    assert pacing.shared_pacing_delay("wingo",tmp_path,90,180) == 90
