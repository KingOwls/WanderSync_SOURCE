import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1] / "backend"))
from datetime import date, timedelta
import pytest
import psycopg  # Avoid the legacy API test's module stub.
from backend.order_service import main as orders


def request(**overrides):
    data = dict(user_id=1,outbound_flight_id='out',return_flight_id='back',hotel_id='hotel',car_id='car',nights=3,quoted_total=1100,idempotency_key='checkout-test-key')
    data.update(overrides)
    return orders.CheckoutRequest(**data)


def test_completed_idempotent_replay_does_not_recheck_expired_catalog(monkeypatch):
    import hashlib, json
    req=request()
    digest=hashlib.sha256(json.dumps(req.model_dump(exclude={'idempotency_key'}),sort_keys=True).encode()).hexdigest()
    calls=[]
    def fetch(sql,params):
        calls.append(sql)
        return dict(id='order',status='CONFIRMED',payment_status='PAID',failure_reason=None,request_hash=digest)
    monkeypatch.setattr(orders,'fetch_one',fetch)
    result=asyncio.run(orders.checkout(req))
    assert result['id']=='order'
    assert len(calls)==1 and 'idempotency_key' in calls[0]


def test_reused_key_with_changed_selection_is_rejected(monkeypatch):
    monkeypatch.setattr(orders,'fetch_one',lambda *a:dict(request_hash='other',status='CONFIRMED'))
    with pytest.raises(orders.HTTPException) as exc: asyncio.run(orders.checkout(request()))
    assert exc.value.status_code==409


def test_checkout_rejects_wrong_destination_before_creating_order(monkeypatch):
    tomorrow=date.today()+timedelta(days=1)
    selected={
      'out':dict(origin='BOG',destination='MDE',travel_date=tomorrow),
      'back':dict(origin='MDE',destination='BOG',travel_date=tomorrow+timedelta(days=3)),
      'hotel':dict(city='CTG'),'car':dict(city='MDE')}
    monkeypatch.setattr(orders,'fetch_one',lambda sql,params:None if 'idempotency_key' in sql else selected[params[0]])
    with pytest.raises(orders.HTTPException) as exc: asyncio.run(orders.checkout(request()))
    assert exc.value.status_code==422


def test_price_change_requires_refresh_before_order_creation(monkeypatch):
    tomorrow=date.today()+timedelta(days=1)
    selected={'out':dict(origin='BOG',destination='MDE',travel_date=tomorrow),'back':dict(origin='MDE',destination='BOG',travel_date=tomorrow+timedelta(days=3)),'hotel':dict(city='MDE'),'car':dict(city='MDE')}
    monkeypatch.setattr(orders,'fetch_one',lambda sql,params:None if 'idempotency_key' in sql else selected[params[0]])
    monkeypatch.setattr(orders,'_authoritative_total',lambda *a:orders.Decimal('1200'))
    with pytest.raises(orders.HTTPException) as exc: asyncio.run(orders.checkout(request()))
    assert exc.value.status_code==409
