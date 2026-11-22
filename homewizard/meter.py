"""Runtime of one HomeWizard meter: its D-Bus service, stored values and writes.

The meter writes to mappings only (the service and the settings), so this
module does not import dbus, vedbus or settingsdevice.
"""
import logging
from typing import Any, Callable, Dict, Iterable, List, MutableMapping

from homewizard.api import DeviceInfo
from homewizard.config import MeterConfig
from homewizard.dbus_service import publish
from homewizard.mapping import measurement_paths, to_values
from homewizard.roles import (
    format_class_instance,
    other_evchargers,
    parse_class_instance,
    product_for,
    service_name,
    settings_base,
)
from homewizard.state import MeterState

PROCESS_NAME = "dbus-homewizard"
PRODUCT_ID = 0xFFFF
PRODUCT_PREFIX = "HomeWizard "
POSITIONS = (0, 1, 2)


class Registry:
    """Remembers which config section owns which meter serial."""

    def __init__(self) -> None:
        self._owners: Dict[str, str] = {}

    def claim(self, serial: str, section: str) -> bool:
        owner = self._owners.setdefault(serial, section)
        return owner == section


class Meter:
    def __init__(
        self,
        cfg: MeterConfig,
        info: DeviceInfo,
        settings: MutableMapping[str, Any],
        make_service: Callable[[str, "Meter"], MutableMapping[str, Any]],
        restart: Callable[[], None],
        log: logging.Logger,
        bus_names: Iterable[str] = (),
        version: str = "0.0.0-dev",
    ):
        self.cfg = cfg
        self.info = info
        self.product = product_for(info.product_type)
        self.settings = settings
        self.restart = restart
        self.log = log

        self.role, self.instance = self._stored_role_and_instance()
        self.state = MeterState(
            self.product, cfg.offline_timeout_s or self.product.default_offline_s
        )
        self._warned_missing_timestamp = False
        self.measurement_paths: List[str] = measurement_paths(self.product, cfg.phase)

        product_name = PRODUCT_PREFIX + info.product_name
        self.product_name = product_name
        first_values: Dict[str, Any] = {
            "/Mgmt/ProcessName": PROCESS_NAME,
            "/Mgmt/ProcessVersion": version,
            "/Mgmt/Connection": "HomeWizard API v2 " + cfg.host,
            "/DeviceInstance": self.instance,
            "/ProductId": PRODUCT_ID,
            "/ProductName": product_name,
            "/CustomName": settings["custom_name"] or product_name,
            "/FirmwareVersion": info.firmware_version,
            "/Serial": info.serial,
            "/Role": self.role,
            "/AllowedRoles": list(self.product.allowed_roles),
            "/Position": settings["position"],
            "/Connected": 0,
            "/UpdateIndex": 0,
        }
        for path in self.measurement_paths:
            first_values[path] = None

        self.paths: List[str] = list(first_values)
        name = service_name(self.role, info.serial)
        self.service = make_service(name, self)
        for path, value in first_values.items():
            self.service[path] = value

        if self.role == "evcharger":
            others = other_evchargers(bus_names, name)
            if others:
                log.warning(
                    "meter %s has role evcharger, and %s are also EV chargers. "
                    "The charger counts twice in the AC loads.",
                    info.serial, ", ".join(others),
                )

    @staticmethod
    def settings_spec(cfg: MeterConfig, info: DeviceInfo) -> Dict[str, list]:
        product = product_for(info.product_type)
        base = settings_base(info.serial)
        class_instance = format_class_instance(
            cfg.role or product.default_role, cfg.device_instance
        )
        return {
            "class_instance": [base + "/ClassAndVrmInstance", class_instance, 0, 0],
            "custom_name": [base + "/CustomName", cfg.custom_name or "", 0, 0],
            "position": [base + "/Position", cfg.position, 0, 2],
        }

    def on_measurement(self, m: Dict[str, Any], now: float) -> None:
        """Store a measurement, and publish it at once when it is new."""
        is_new = self.state.accept(m, now)
        if self.state.energy_went_down:
            self.log.warning(
                "meter %s: the imported energy went down. Was the meter reset?",
                self.info.serial,
            )
            self.state.energy_went_down = False
        if self.state.missing_timestamp and not self._warned_missing_timestamp:
            self._warned_missing_timestamp = True
            self.log.warning(
                "meter %s: the P1 Meter sends no timestamp, so the meter stays "
                "disconnected.", self.info.serial,
            )
        if is_new:
            self._publish_values()

    def tick(self, now: float) -> None:
        """Publish the values while the meter is online, or clear them."""
        if self.state.online(now):
            self._publish_values()
        else:
            publish(self.service, self.measurement_paths, None)

    def _publish_values(self) -> None:
        values = to_values(
            self.state.measurement, self.product, self.role,
            self.cfg.phase, self.cfg.reverse,
        )
        publish(self.service, self.measurement_paths, values)

    def on_write(self, path: str, value: Any) -> bool:
        if path == "/Role":
            return self._write_role(value)
        if path == "/CustomName":
            return self._write_custom_name(str(value))
        if path == "/Position":
            if isinstance(value, int) and not isinstance(value, bool) and value in POSITIONS:
                self.settings["position"] = int(value)
                return True
            return False
        return False

    def _write_custom_name(self, name: str) -> bool:
        self.settings["custom_name"] = name
        if name:
            return True
        # An empty name shows the product name. vedbus stores the written
        # value after a True return, so return False to keep the product
        # name. The writer then gets an error code, but the name is right.
        self.service["/CustomName"] = self.product_name
        return False

    def on_setting_changed(self, setting: str, old: Any, new: Any) -> None:
        """Handle a change in localsettings, made by another process.

        A new role or instance needs a new service name, so restart.
        """
        if setting != "class_instance":
            return
        if new != format_class_instance(self.role, self.instance):
            self.restart()

    def _write_role(self, value: Any) -> bool:
        if not isinstance(value, str) or value not in self.product.allowed_roles:
            return False
        if value == self.role:
            return True
        self.settings["class_instance"] = format_class_instance(value, self.instance)
        self.restart()
        return True

    def _stored_role_and_instance(self):
        stored = self.settings["class_instance"]
        try:
            role, instance = parse_class_instance(stored)
        except ValueError:
            self.log.error(
                "meter %s: stored ClassAndVrmInstance %r is not valid, using the config file",
                self.info.serial, stored,
            )
            role = self.cfg.role or self.product.default_role
            instance = self.cfg.device_instance
        if role not in self.product.allowed_roles:
            self.log.error(
                "meter %s: stored role %s is not allowed for %s, using %s",
                self.info.serial, role, self.product.product_type, self.product.default_role,
            )
            role = self.product.default_role
        return role, instance
