from dataclasses import dataclass


@dataclass
class CompensationStep:
    service: str
    reservation_id: str
    event_step: str | None = None


def reverse_compensation_order(confirmed_steps: list[CompensationStep]) -> list[CompensationStep]:
    """SAGA compensates in reverse order of successful reservations."""
    return list(reversed(confirmed_steps))
