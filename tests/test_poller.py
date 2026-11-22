import threading
import time

import pytest

from homewizard.api import ApiError, AuthError, DeviceInfo
from homewizard.poller import Poller

P1_INFO = DeviceInfo("P1 Meter", "HWE-P1", "5c2fafaabbcc", "6.00")


class FakeClient:
    def __init__(self, devices=None, measurements=None):
        self.devices = list(devices or [P1_INFO])
        self.measurements = list(measurements or [])
        self.tls_name = None
        self.closed = 0

    def _next(self, items):
        item = items.pop(0) if len(items) > 1 else items[0]
        if isinstance(item, BaseException):
            raise item
        return item

    def get_device(self):
        return self._next(self.devices)

    def get_measurement(self):
        return self._next(self.measurements)

    def set_tls_name(self, name):
        self.tls_name = name

    def close(self):
        self.closed += 1


class Recorder:
    def __init__(self):
        self.devices = []
        self.measurements = []
        self.errors = []


def make_poller(client, interval_s=1.0, clock=None, sleep=None):
    rec = Recorder()
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    if sleep is not None:
        kwargs["sleep"] = sleep
    poller = Poller(
        client,
        interval_s,
        schedule=lambda fn, arg: fn(arg),
        on_device=rec.devices.append,
        on_measurement=rec.measurements.append,
        on_error=rec.errors.append,
        **kwargs,
    )
    return poller, rec


def ticking_clock(*values):
    readings = list(values)
    return lambda: readings.pop(0) if len(readings) > 1 else readings[0]


def test_first_step_reads_device_and_sets_tls_name():
    fake = FakeClient()
    poller, rec = make_poller(fake)
    assert poller.step() == 0
    assert fake.tls_name == "appliance/p1dongle/5c2fafaabbcc"
    assert rec.devices == [P1_INFO]
    assert rec.errors == []


def test_measurement_waits_rest_of_interval():
    fake = FakeClient(measurements=[{"power_w": 5}])
    poller, rec = make_poller(fake, interval_s=1, clock=ticking_clock(10.0, 10.3))
    poller.step()
    assert poller.step() == pytest.approx(0.7)
    assert rec.measurements == [{"power_w": 5}]


def test_slow_measurement_does_not_wait():
    fake = FakeClient(measurements=[{}])
    poller, _ = make_poller(fake, interval_s=1, clock=ticking_clock(10.0, 12.0))
    poller.step()
    assert poller.step() == 0


def test_auth_error_backs_off_60():
    fake = FakeClient(devices=[AuthError("HTTP 401")])
    poller, rec = make_poller(fake)
    assert poller.step() == 60
    assert len(rec.errors) == 1 and isinstance(rec.errors[0], AuthError)
    assert rec.devices == []


def test_auth_error_on_measurement_backs_off_60():
    fake = FakeClient(measurements=[AuthError("HTTP 401")])
    poller, rec = make_poller(fake)
    poller.step()
    assert poller.step() == 60
    assert len(rec.errors) == 1


def test_api_error_on_device_backs_off_10():
    fake = FakeClient(devices=[ApiError("timeout")])
    poller, rec = make_poller(fake)
    assert poller.step() == 10
    assert len(rec.errors) == 1
    assert fake.tls_name is None


def test_api_error_on_measurement_waits_interval():
    fake = FakeClient(measurements=[ApiError("timeout")])
    poller, rec = make_poller(fake, interval_s=2.5)
    poller.step()
    assert poller.step() == 2.5
    assert len(rec.errors) == 1


def test_unknown_product_backs_off_3600():
    fake = FakeClient(devices=[DeviceInfo("Water", "HWE-WTR", "abc", "1.0")])
    poller, rec = make_poller(fake)
    assert poller.step() == 3600
    assert len(rec.errors) == 1 and isinstance(rec.errors[0], ValueError)
    assert rec.devices == []
    assert fake.tls_name is None


def test_device_is_read_again_after_device_error():
    fake = FakeClient(devices=[ApiError("timeout"), P1_INFO])
    poller, rec = make_poller(fake)
    assert poller.step() == 10
    assert poller.step() == 0
    assert rec.devices == [P1_INFO]


def test_error_does_not_stop_the_loop():
    fake = FakeClient(measurements=[ApiError("a"), ApiError("b"), {}])
    poller, rec = make_poller(fake)
    poller.step()
    for _ in range(3):
        poller.step()
    assert rec.measurements == [{}]
    assert len(rec.errors) == 2


def test_unexpected_error_before_device_waits_10():
    fake = FakeClient(devices=[RuntimeError("boom")])
    poller, rec = make_poller(fake)
    assert poller.safe_step() == 10
    assert len(rec.errors) == 1 and isinstance(rec.errors[0], RuntimeError)


def test_unexpected_error_after_device_waits_interval():
    fake = FakeClient(measurements=[KeyError("boom"), {}])
    poller, rec = make_poller(fake, interval_s=2)
    poller.safe_step()
    assert poller.safe_step() == 2
    assert len(rec.errors) == 1 and isinstance(rec.errors[0], KeyError)
    poller.safe_step()
    assert rec.measurements == [{}]


def test_loop_survives_unexpected_error_and_stops():
    fake = FakeClient(devices=[RuntimeError("boom"), P1_INFO], measurements=[{}])
    waits = []
    poller = None

    def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 3:
            assert poller is not None
            poller.stop()

    poller, rec = make_poller(fake, sleep=sleep)
    poller.run()
    assert waits[:2] == [10, 0]
    assert rec.devices == [P1_INFO]
    assert rec.measurements == [{}]
    assert len(rec.errors) == 1


def test_start_and_stop_thread():
    fake = FakeClient(measurements=[{}])
    measured = threading.Event()
    poller = Poller(
        fake,
        0.01,
        schedule=lambda fn, arg: fn(arg),
        on_device=lambda info: None,
        on_measurement=lambda m: measured.set(),
        on_error=lambda exc: None,
    )
    started = time.monotonic()
    poller.start()
    assert measured.wait(0.5)
    poller.stop()
    thread = poller._thread
    assert thread is not None
    thread.join(0.5)
    assert not thread.is_alive()
    assert fake.closed >= 1
    assert time.monotonic() - started < 1.0
