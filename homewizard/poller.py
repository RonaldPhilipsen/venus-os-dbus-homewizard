"""Poll one HomeWizard meter in its own thread."""

import threading
import time
from typing import Any, Callable, Dict

from homewizard.api import ApiError, AuthError, DeviceInfo
from homewizard.roles import product_for, tls_name

AUTH_BACKOFF_S = 60.0
DEVICE_RETRY_S = 10.0
UNKNOWN_PRODUCT_BACKOFF_S = 3600.0


class Poller:
    """Reads device info once, then measurements every interval.

    The callbacks go through `schedule(callback, arg)`, so they run in the GLib
    thread and never in the poll thread.
    """

    def __init__(
        self,
        client: Any,
        interval_s: float,
        schedule: Callable[..., Any],
        on_device: Callable[[DeviceInfo], None],
        on_measurement: Callable[[Dict[str, Any]], None],
        on_error: Callable[[Exception], None],
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.client = client
        self.interval_s = interval_s
        self._schedule = schedule
        self._on_device = on_device
        self._on_measurement = on_measurement
        self._on_error = on_error
        self._clock = clock
        self._stop = threading.Event()
        # With the default sleep, wait on the stop event so stop() ends the wait.
        self._sleep = self._stop.wait if sleep is time.sleep else sleep
        self._device = None  # type: Optional[DeviceInfo]
        self._thread = None  # type: Optional[threading.Thread]

    def step(self) -> float:
        """Do one unit of work and return the seconds to wait before the next step."""
        if self._device is None:
            return self._read_device()
        started = self._clock()
        try:
            measurement = self.client.get_measurement()
        except AuthError as exc:
            self._schedule(self._on_error, exc)
            return AUTH_BACKOFF_S
        except ApiError as exc:
            self._schedule(self._on_error, exc)
            return self.interval_s
        self._schedule(self._on_measurement, measurement)
        elapsed = self._clock() - started
        return max(0.0, self.interval_s - elapsed)

    def _read_device(self) -> float:
        try:
            info = self.client.get_device()
            product = product_for(info.product_type)
        except AuthError as exc:
            self._schedule(self._on_error, exc)
            return AUTH_BACKOFF_S
        except ApiError as exc:
            self._schedule(self._on_error, exc)
            return DEVICE_RETRY_S
        except ValueError as exc:
            self._schedule(self._on_error, exc)
            return UNKNOWN_PRODUCT_BACKOFF_S
        self.client.set_tls_name(tls_name(product, info.serial))
        self._device = info
        self._schedule(self._on_device, info)
        return 0.0

    def safe_step(self) -> float:
        """Run step(), and report an unexpected error in place of raising it."""
        try:
            return self.step()
        except Exception as exc:
            self._schedule(self._on_error, exc)
            return DEVICE_RETRY_S if self._device is None else self.interval_s

    def run(self) -> None:
        """Poll until stop() is called."""
        while not self._stop.is_set():
            self._sleep(self.safe_step())

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="homewizard-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.client.close()
