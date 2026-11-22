#!/usr/bin/env python3
"""Venus OS driver: HomeWizard energy meters as Victron meters on D-Bus."""
import configparser
import logging
import os
import platform
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
# velib_python comes from the GX device.
sys.path.insert(1, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")

import dbus  # noqa: E402
from dbus.mainloop.glib import DBusGMainLoop  # noqa: E402
from gi.repository import GLib  # noqa: E402
from settingsdevice import SettingsDevice  # noqa: E402
from vedbus import VeDbusService  # noqa: E402

from homewizard import __version__  # noqa: E402
from homewizard.api import AuthError, Client  # noqa: E402
from homewizard.config import load_config  # noqa: E402
from homewizard.dbus_service import WRITEABLE_PATHS, text_for  # noqa: E402
from homewizard.meter import Meter, Registry  # noqa: E402
from homewizard.poller import Poller  # noqa: E402

FATAL_DELAY_S = 60
ERROR_LOG_INTERVAL_S = 60.0
RESTART_DELAY_MS = 1000

log = logging.getLogger("homewizard")


def fatal(message, *args, exc_info=False):
    """Log an error and exit late, so daemontools does not restart in a tight loop."""
    log.error(message, *args, exc_info=exc_info)
    time.sleep(FATAL_DELAY_S)
    sys.exit(1)


def system_bus():
    if "DBUS_SESSION_BUS_ADDRESS" in os.environ:
        return dbus.SessionBus()
    return dbus.SystemBus()


def make_service(name):
    """Create a VeDbusService for both newer (register=False) and older vedbus."""
    try:
        return VeDbusService(name, register=False)
    except TypeError:
        return VeDbusService(name)


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.WARNING,
                        format="%(levelname)s %(name)s %(message)s")
    try:
        start()
    except Exception as e:
        fatal("startup failed: %s", e, exc_info=True)
    GLib.MainLoop().run()


def make_meter_service(name, meter):
    """Create the service with all paths of the meter. The caller registers it."""
    svc = make_service(name)
    for path in meter.paths:
        writeable = path in WRITEABLE_PATHS
        svc.add_path(path, None, gettextcallback=text_for(path),
                     writeable=writeable,
                     onchangecallback=meter.on_write if writeable else None)
    return svc


def restart():
    """Exit after a delay, so localsettings stores the new value first.

    Daemontools starts the driver again.
    """
    GLib.timeout_add(RESTART_DELAY_MS, lambda: os._exit(0))


class MeterSlot:
    """One config section: its poller, and its Meter once the device is known."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.poller = None
        self.meter = None
        self.stopped = False
        self.last_error_log = None

    def stop(self):
        self.stopped = True
        self.poller.stop()


def start():
    """Set up the pollers and the timers. The caller runs the loop."""
    config_path = os.path.join(HERE, "config.ini")
    if not os.path.exists(config_path):
        fatal("config file not found: %s", config_path)
    try:
        cfg = load_config(config_path)
    except (ValueError, KeyError, configparser.Error) as e:
        fatal("invalid config file %s: %s", config_path, e)

    DBusGMainLoop(set_as_default=True)
    bus = system_bus()
    version = "%s on Python %s" % (__version__, platform.python_version())
    registry = Registry()
    owners = {}  # serial -> config section name, for the duplicate message
    slots = []

    # 1. One poller per meter. The callbacks run in the GLib thread through
    #    idle_add, and return False so that GLib calls them only once.
    def device_handler(slot):
        def on_device(info):
            if slot.stopped:
                return False
            if not registry.claim(info.serial, slot.cfg.name):
                log.error("meter %s in [METER:%s] is the same meter as in [METER:%s]. "
                          "Ignoring [METER:%s].", info.serial, slot.cfg.name,
                          owners[info.serial], slot.cfg.name)
                slot.stop()
                return False
            owners[info.serial] = slot.cfg.name
            try:
                settings = SettingsDevice(
                    bus, Meter.settings_spec(slot.cfg, info),
                    lambda *a: None)
                meter = Meter(slot.cfg, info, settings, make_meter_service,
                              restart, log, bus_names=bus.list_names(),
                              version=version)
                if hasattr(meter.service, "register"):
                    meter.service.register()
            except Exception:
                log.exception("meter %s in [METER:%s]: setup failed",
                              info.serial, slot.cfg.name)
                slot.stop()
                return False
            slot.meter = meter
            return False
        return on_device

    def measurement_handler(slot):
        def on_measurement(m):
            if slot.stopped or slot.meter is None:
                return False
            try:
                slot.meter.on_measurement(m, time.monotonic())
            except Exception:
                log.exception("meter [METER:%s]: measurement failed", slot.cfg.name)
            return False
        return on_measurement

    def error_handler(slot):
        def on_error(e):
            if slot.stopped:
                return False
            now = time.monotonic()
            if (slot.last_error_log is not None
                    and now - slot.last_error_log < ERROR_LOG_INTERVAL_S):
                return False
            slot.last_error_log = now
            if isinstance(e, AuthError):
                log.warning("meter [METER:%s] at %s: the token is not valid. "
                            "Run pair.py %s to get a new token.",
                            slot.cfg.name, slot.cfg.host, slot.cfg.host)
            else:
                log.warning("meter [METER:%s] at %s: %s",
                            slot.cfg.name, slot.cfg.host, e)
            return False
        return on_error

    for meter_cfg in cfg.meters:
        slot = MeterSlot(meter_cfg)
        client = Client(meter_cfg.host, meter_cfg.token, meter_cfg.verify_tls)
        slot.poller = Poller(client, meter_cfg.poll_interval_s, GLib.idle_add,
                             device_handler(slot), measurement_handler(slot),
                             error_handler(slot))
        slots.append(slot)

    # 2. Update D-Bus every second.
    def update():
        now = time.monotonic()
        for slot in slots:
            if slot.meter is None or slot.stopped:
                continue
            try:
                slot.meter.tick(now)
            except Exception:
                log.exception("meter [METER:%s]: update failed", slot.cfg.name)
        return True

    GLib.timeout_add(1000, update)

    # 3. Sign of life, then start the pollers.
    def sign_of_life():
        for slot in slots:
            meter = slot.meter
            if slot.stopped:
                continue
            if meter is None:
                log.warning("sign of life: [METER:%s] at %s: no device info yet",
                            slot.cfg.name, slot.cfg.host)
                continue
            log.warning("sign of life: serial=%s connected=%s power=%s role=%s",
                        meter.info.serial, meter.service["/Connected"],
                        meter.service["/Ac/Power"], meter.role)
        return True

    if cfg.sign_of_life_minutes > 0:
        GLib.timeout_add_seconds(cfg.sign_of_life_minutes * 60, sign_of_life)

    for slot in slots:
        slot.poller.start()


if __name__ == "__main__":
    main()
