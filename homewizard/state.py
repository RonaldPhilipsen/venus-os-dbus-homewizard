"""Freshness and offline state for one HomeWizard meter."""
from typing import Any, Dict, Optional

from homewizard.roles import Product


class MeterState:
    """Tracks the last new measurement of a meter and whether it is still fresh.

    Times are time.monotonic() values passed in by the caller.
    """

    def __init__(self, product: Product, timeout_s: float):
        self.product = product
        self.timeout_s = timeout_s
        self.measurement: Optional[Dict[str, Any]] = None
        self.energy_went_down = False
        # True once a P1 measurement came without a timestamp. Such a
        # measurement is never new, so the meter stays disconnected.
        self.missing_timestamp = False
        self._last_timestamp: Any = None
        self._last_new_at: Optional[float] = None

    def accept(self, m: Dict[str, Any], now: float) -> bool:
        """Store m if it is a new measurement. Return True when it is new."""
        if self.product.kind == "p1":
            timestamp = m.get("timestamp")
            if timestamp is None:
                self.missing_timestamp = True
                return False
            if timestamp == self._last_timestamp:
                return False
            self._last_timestamp = timestamp

        self._check_energy(m)
        self.measurement = m
        self._last_new_at = now
        return True

    def online(self, now: float) -> bool:
        if self._last_new_at is None:
            return False
        return now - self._last_new_at < self.timeout_s

    def _check_energy(self, m: Dict[str, Any]) -> None:
        if self.measurement is None:
            return
        previous = self.measurement.get("energy_import_kwh")
        current = m.get("energy_import_kwh")
        if previous is not None and current is not None and current < previous:
            self.energy_went_down = True
