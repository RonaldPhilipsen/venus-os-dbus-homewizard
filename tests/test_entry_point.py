"""Tests for dbus-homewizard.py with stub dbus, GLib, vedbus and settingsdevice.

No real D-Bus is used. The stubs record the calls that the entry point makes.
"""

import importlib.util
import os
import sys
import types

import pytest

from homewizard.api import DeviceInfo
from homewizard.config import MeterConfig

ENTRY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dbus-homewizard.py"
)
SERIAL = "5c2fafaabbcc"


class StubBus:
    def __init__(self, kind, private):
        self.kind = kind
        self.private = private
        self.closed = False

    def list_names(self):
        return []

    def close(self):
        self.closed = True


class StubService:
    created = []

    def __init__(self, name, bus=None, register=True):
        self.name = name
        self.bus = bus
        self.values = {}
        self.registered = False
        StubService.created.append(self)

    def add_path(self, path, value, **kwargs):
        self.values[path] = value

    def __getitem__(self, path):
        return self.values[path]

    def __setitem__(self, path, value):
        self.values[path] = value

    def register(self):
        self.registered = True


class StubSettings:
    fail = False
    callbacks = []

    def __init__(self, bus, spec, callback):
        if StubSettings.fail:
            raise RuntimeError("localsettings is not there")
        StubSettings.callbacks.append(callback)
        self.values = {name: item[1] for name, item in spec.items()}

    def __getitem__(self, name):
        return self.values[name]

    def __setitem__(self, name, value):
        self.values[name] = value


class StubGLib:
    def __init__(self):
        self.timeouts = []
        self.timeouts_s = []

    def timeout_add(self, ms, fn):
        self.timeouts.append((ms, fn))

    def timeout_add_seconds(self, s, fn):
        self.timeouts_s.append((s, fn))


@pytest.fixture
def entry(monkeypatch):
    StubService.created = []
    StubSettings.fail = False
    StubSettings.callbacks = []
    buses = []

    def system_bus(private=False):
        bus = StubBus("system", private)
        buses.append(bus)
        return bus

    def session_bus(private=False):
        bus = StubBus("session", private)
        buses.append(bus)
        return bus

    # Write to __dict__: ty does not allow new attributes on a module object.
    dbus = types.ModuleType("dbus")
    dbus.__dict__["SystemBus"] = system_bus
    dbus.__dict__["SessionBus"] = session_bus
    mainloop = types.ModuleType("dbus.mainloop")
    mainloop_glib = types.ModuleType("dbus.mainloop.glib")
    mainloop_glib.__dict__["DBusGMainLoop"] = lambda set_as_default=False: None
    gi = types.ModuleType("gi")
    gi_repository = types.ModuleType("gi.repository")
    glib = StubGLib()
    gi_repository.__dict__["GLib"] = glib
    vedbus = types.ModuleType("vedbus")
    vedbus.__dict__["VeDbusService"] = StubService
    settingsdevice = types.ModuleType("settingsdevice")
    settingsdevice.__dict__["SettingsDevice"] = StubSettings
    for name, module in (
        ("dbus", dbus),
        ("dbus.mainloop", mainloop),
        ("dbus.mainloop.glib", mainloop_glib),
        ("gi", gi),
        ("gi.repository", gi_repository),
        ("vedbus", vedbus),
        ("settingsdevice", settingsdevice),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)

    spec = importlib.util.spec_from_file_location("dbus_homewizard_entry", ENTRY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__dict__["test_glib"] = glib
    module.__dict__["test_buses"] = buses
    return module


def make_cfg(name="hp"):
    return MeterConfig(
        name=name,
        host="192.168.1.10",
        token="0" * 32,
        role=None,
        device_instance=40,
        custom_name=None,
        phase=1,
        reverse=False,
        position=0,
        poll_interval_s=1.0,
        offline_timeout_s=None,
        verify_tls=True,
    )


def make_info(serial=SERIAL):
    return DeviceInfo(
        product_name="Energy Meter", product_type="HWE-KWH1", serial=serial, firmware_version="4.19"
    )


class StubPoller:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def make_slot(entry, name="hp"):
    slot = entry.MeterSlot(make_cfg(name))
    slot.poller = StubPoller()
    return slot


def test_private_bus_uses_the_system_bus(entry):
    bus = entry.private_bus()
    assert bus.kind == "system" and bus.private is True


def test_private_bus_uses_the_session_bus_when_set(entry, monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/x")
    bus = entry.private_bus()
    assert bus.kind == "session" and bus.private is True


def test_make_service_passes_the_bus(entry):
    bus = StubBus("system", True)
    svc = entry.make_service("com.victronenergy.acload.x", bus)
    assert svc.bus is bus


def test_each_meter_gets_its_own_private_bus(entry):
    shared = StubBus("system", False)
    first = entry.setup_meter(make_slot(entry, "a"), make_info("5c2fafaabb01"), shared, "1")
    second = entry.setup_meter(make_slot(entry, "b"), make_info("5c2fafaabb02"), shared, "1")
    assert first is not None and second is not None
    buses = [svc.bus for svc in StubService.created]
    assert len(buses) == 2 and buses[0] is not buses[1]
    assert all(bus.private and bus is not shared for bus in buses)
    assert all(svc.registered for svc in StubService.created)


def test_setup_failure_stops_the_slot_and_schedules_one_restart(entry, caplog):
    StubSettings.fail = True
    shared = StubBus("system", False)
    first, second = make_slot(entry, "a"), make_slot(entry, "b")
    assert entry.setup_meter(first, make_info("5c2fafaabb01"), shared, "1") is None
    assert entry.setup_meter(second, make_info("5c2fafaabb02"), shared, "1") is None
    assert first.stopped and first.poller.stopped and second.stopped
    assert [s for s, _ in entry.test_glib.timeouts_s] == [60]
    assert caplog.text.count("restarts in 60 seconds") == 1


def test_setup_failure_closes_the_private_bus(entry, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("name in use")

    monkeypatch.setattr(StubService, "register", fail)
    slot = make_slot(entry)
    assert entry.setup_meter(slot, make_info(), StubBus("system", False), "1") is None
    private = [bus for bus in entry.test_buses if bus.private]
    assert len(private) == 1 and private[0].closed


def test_class_instance_change_restarts(entry):
    slot = make_slot(entry)
    meter = entry.setup_meter(slot, make_info(), StubBus("system", False), "1")
    callback = StubSettings.callbacks[-1]
    callback("custom_name", "", "Heat pump")
    callback("class_instance", "acload:40", "acload:40")
    assert entry.test_glib.timeouts == []
    callback("class_instance", "acload:40", "heatpump:40")
    assert [ms for ms, _ in entry.test_glib.timeouts] == [1000]
    assert meter.role == "acload"
