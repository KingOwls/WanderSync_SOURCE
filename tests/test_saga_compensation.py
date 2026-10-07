import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from common.reservation import CompensationStep, reverse_compensation_order

class SagaCompensationTests(unittest.TestCase):
    def test_compensation_reverses_successful_steps(self):
        steps = [
            CompensationStep("flight", "F1"),
            CompensationStep("hotel", "H1"),
            CompensationStep("car", "C1"),
        ]
        result = reverse_compensation_order(steps)
        self.assertEqual([x.service for x in result], ["car", "hotel", "flight"])

    def test_empty_steps_is_safe(self):
        self.assertEqual(reverse_compensation_order([]), [])

if __name__ == "__main__":
    unittest.main()


def test_compensation_services_do_not_restore_fake_external_inventory():
    root = Path(__file__).resolve().parents[1]
    for service in ("flight_service", "hotel_service", "car_service"):
        text = (root / "backend" / service / "main.py").read_text(encoding="utf-8").lower()
        assert "available_seats" not in text
        assert "available_rooms" not in text
        assert "available_units" not in text


def test_roundtrip_saga_has_distinct_outbound_and_return_steps_and_reverse_compensation():
    text = (ROOT / "backend" / "order_service" / "main.py").read_text(encoding="utf-8").lower()
    assert '("outbound_flight", "flight", req.outbound_flight_id)' in text
    assert '("return_flight", "flight", req.return_flight_id)' in text
    assert "req.simulate_failure == event_step" in text
    assert "event_step=event_step" in text
    assert 'allowed_failures = {none, "flight", "outbound_flight", "return_flight", "hotel", "car", "billing"}' in text
