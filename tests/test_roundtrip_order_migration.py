from pathlib import Path

ROOT = Path(__file__).parents[1]
SQL = (ROOT / "infra" / "postgres" / "init.sql").read_text(encoding="utf-8").lower()
ORDER = (ROOT / "backend" / "order_service" / "main.py").read_text(encoding="utf-8").lower()


def test_order_migration_adds_explicit_roundtrip_leg_ids_idempotently():
    assert "outbound_flight_id" in SQL
    assert "return_flight_id" in SQL
    assert "alter table orders add column if not exists outbound_flight_id" in SQL
    assert "alter table orders add column if not exists return_flight_id" in SQL
    assert "setoutbound_flight_id=flight_id" in SQL.replace(" ", "")
    assert SQL.index("alter table orders add column if not exists outbound_flight_id") < SQL.index("create index if not exists idx_orders_user")


def test_new_checkout_writes_both_explicit_flight_legs():
    assert "outbound_flight_id" in ORDER
    assert "return_flight_id" in ORDER
    assert "insert into orders(id,user_id,flight_id,outbound_flight_id,return_flight_id" in ORDER
