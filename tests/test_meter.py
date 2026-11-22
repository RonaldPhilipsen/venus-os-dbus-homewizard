import logging


from homewizard.api import DeviceInfo
from homewizard.config import ROLES, MeterConfig
from homewizard.mapping import measurement_paths, to_values
from homewizard.meter import Meter, Registry
from homewizard.roles import product_for
from tests.fixtures import KWH1, P1_3PHASE

SERIAL = "5c2fafaabbcc"
LOG = logging.getLogger("test_meter")


def make_cfg(**changes):
    values = dict(
        name="hp", host="192.168.1.10", token="0" * 32, role=None, device_instance=40,
        custom_name=None, phase=1, reverse=False, position=0, poll_interval_s=1.0,
        offline_timeout_s=None, verify_tls=True,
    )
    values.update(changes)
    return MeterConfig(**values)


def make_info(product_type="HWE-KWH1"):
    return DeviceInfo(product_name="Energy Meter", product_type=product_type,
                      serial=SERIAL, firmware_version="4.19")


class Harness:
    def __init__(self, settings, product_type="HWE-KWH1", bus_names=(), **cfg_changes):
        self.settings = settings
        self.created_names = []
        self.paths_at_create = None
        self.restarts = []
        self.cfg = make_cfg(**cfg_changes)
        self.meter = Meter(self.cfg, make_info(product_type), settings, self.make_service,
                           self.restart, LOG, bus_names=bus_names, version="1.2.3")

    def make_service(self, name, meter):
        self.created_names.append(name)
        self.paths_at_create = list(meter.paths)
        return {}

    def restart(self):
        self.restarts.append(len(self.restarts) + 1)


def stored(class_instance="heatpump:42", custom_name="", position=0):
    return {"class_instance": class_instance, "custom_name": custom_name, "position": position}


def test_service_name_from_stored_role():
    h = Harness(stored(), product_type="HWE-KWH1")
    m = h.meter
    assert h.created_names == ["com.victronenergy.heatpump.homewizard_5c2fafaabbcc"]
    assert m.role == "heatpump" and m.instance == 42 and m.service["/DeviceInstance"] == 42
    assert m.service["/AllowedRoles"] == list(ROLES)


def test_first_values():
    h = Harness(stored(position=2), product_type="HWE-KWH1")
    svc = h.meter.service
    assert svc["/Mgmt/ProcessName"] == "dbus-homewizard"
    assert svc["/Mgmt/ProcessVersion"] == "1.2.3"
    assert svc["/Mgmt/Connection"] == "HomeWizard API v2 192.168.1.10"
    assert svc["/FirmwareVersion"] == "4.19"
    assert svc["/Serial"] == SERIAL
    assert svc["/Role"] == "heatpump"
    assert svc["/Position"] == 2
    assert svc["/ProductId"] == 0xFFFF
    assert svc["/ProductName"] == "HomeWizard Energy Meter"
    assert svc["/CustomName"] == "HomeWizard Energy Meter"
    assert svc["/Connected"] == 0 and svc["/UpdateIndex"] == 0
    for path in measurement_paths(product_for("HWE-KWH1"), 1):
        assert svc[path] is None


def test_paths_are_set_before_make_service():
    h = Harness(stored())
    assert h.paths_at_create == h.meter.paths
    assert sorted(h.meter.paths) == sorted(h.meter.service)


def test_stored_custom_name_is_used():
    h = Harness(stored(custom_name="Heat pump"))
    assert h.meter.service["/CustomName"] == "Heat pump"


def test_stored_role_not_allowed_uses_default(caplog):
    settings = stored(class_instance="heatpump:42")
    with caplog.at_level(logging.ERROR):
        h = Harness(settings, product_type="HWE-P1")
    assert h.meter.role == "grid" and h.meter.instance == 42
    assert h.created_names == ["com.victronenergy.grid.homewizard_5c2fafaabbcc"]
    assert h.meter.service["/AllowedRoles"] == ["grid"]
    assert settings["class_instance"] == "heatpump:42"
    assert "heatpump" in caplog.text


def test_settings_spec_defaults_to_config():
    base = "/Settings/Devices/homewizard_" + SERIAL
    spec = Meter.settings_spec(make_cfg(), make_info("HWE-KWH1"))
    assert spec == {
        "class_instance": [base + "/ClassAndVrmInstance", "acload:40", 0, 0],
        "custom_name": [base + "/CustomName", "", 0, 0],
        "position": [base + "/Position", 0, 0, 2],
    }
    spec = Meter.settings_spec(make_cfg(device_instance=41), make_info("HWE-P1"))
    assert spec["class_instance"][1] == "grid:41"


def test_settings_spec_uses_config_values():
    cfg = make_cfg(role="heatpump", custom_name="Heat pump", position=1)
    spec = Meter.settings_spec(cfg, make_info("HWE-KWH1"))
    assert spec["class_instance"][1] == "heatpump:40"
    assert spec["custom_name"][1] == "Heat pump"
    assert spec["position"][1] == 1


def test_role_write_stores_and_restarts():
    h = Harness(stored())
    assert h.meter.on_write("/Role", "grid") is True
    assert h.settings["class_instance"] == "grid:42" and h.restarts == [1]


def test_role_write_same_role_does_nothing():
    h = Harness(stored())
    assert h.meter.on_write("/Role", "heatpump") is True
    assert h.settings["class_instance"] == "heatpump:42" and h.restarts == []


def test_role_write_not_allowed_on_p1():
    h = Harness(stored(class_instance="grid:40"), product_type="HWE-P1")
    assert h.meter.on_write("/Role", "heatpump") is False
    assert h.settings["class_instance"] == "grid:40" and h.restarts == []


def test_role_write_unknown_or_not_string():
    h = Harness(stored())
    assert h.meter.on_write("/Role", "boiler") is False
    assert h.meter.on_write("/Role", 3) is False
    assert h.settings["class_instance"] == "heatpump:42" and h.restarts == []


def test_custom_name_write():
    h = Harness(stored())
    assert h.meter.on_write("/CustomName", "Heat pump") is True
    assert h.settings["custom_name"] == "Heat pump"
    assert h.meter.on_write("/CustomName", "") is True
    assert h.settings["custom_name"] == ""


def test_position_write_range():
    h = Harness(stored())
    assert h.meter.on_write("/Position", 2) is True and h.settings["position"] == 2
    assert h.meter.on_write("/Position", 3) is False
    assert h.meter.on_write("/Position", "x") is False
    assert h.meter.on_write("/Position", -1) is False
    assert h.settings["position"] == 2


def test_other_path_write_is_refused():
    h = Harness(stored())
    assert h.meter.on_write("/Ac/Power", 5) is False


def test_tick_offline_publishes_none():
    h = Harness(stored())
    m = h.meter
    m.on_measurement(dict(KWH1), 100.0)
    m.tick(100.5)
    assert m.service["/Ac/Power"] == 800.0
    m.tick(105.0)
    assert m.service["/Connected"] == 0
    for path in measurement_paths(product_for("HWE-KWH1"), 1):
        assert m.service[path] is None


def test_tick_before_any_measurement_publishes_none():
    h = Harness(stored())
    h.meter.tick(0.0)
    assert h.meter.service["/Connected"] == 0 and h.meter.service["/Ac/Power"] is None


def test_tick_online_publishes_values():
    h = Harness(stored(class_instance="grid:40"), product_type="HWE-P1")
    m = h.meter
    m.on_measurement(dict(P1_3PHASE), 10.0)
    m.tick(11.0)
    expected = to_values(P1_3PHASE, product_for("HWE-P1"), "grid", 1, False)
    for path, value in expected.items():
        assert m.service[path] == value
    assert m.service["/Connected"] == 1 and m.service["/UpdateIndex"] == 1


def test_offline_timeout_from_config():
    h = Harness(stored(), offline_timeout_s=30.0)
    h.meter.on_measurement(dict(KWH1), 0.0)
    h.meter.tick(29.0)
    assert h.meter.service["/Connected"] == 1


def test_energy_down_logs_warning(caplog):
    h = Harness(stored())
    m = h.meter
    m.on_measurement(dict(KWH1), 0.0)
    lower = dict(KWH1, energy_import_kwh=KWH1["energy_import_kwh"] - 1)
    with caplog.at_level(logging.WARNING):
        m.on_measurement(lower, 1.0)
    assert SERIAL in caplog.text
    assert m.state.energy_went_down is False


def test_evcharger_role_warns_about_other_charger(caplog):
    other = "com.victronenergy.evcharger.smartevse_1"
    names = [other, "com.victronenergy.evcharger.homewizard_" + SERIAL,
             "com.victronenergy.grid.homewizard_x"]
    with caplog.at_level(logging.WARNING):
        Harness(stored(class_instance="evcharger:42"), bus_names=names)
    assert other in caplog.text and "twice" in caplog.text


def test_evcharger_role_without_other_charger_is_quiet(caplog):
    with caplog.at_level(logging.WARNING):
        Harness(stored(class_instance="evcharger:42"),
                bus_names=["com.victronenergy.grid.x",
                           "com.victronenergy.evcharger.homewizard_" + SERIAL])
    assert caplog.text == ""


def test_registry_rejects_duplicate_serial():
    r = Registry()
    assert r.claim("5c2fafaabbcc", "hp") and not r.claim("5c2fafaabbcc", "hp2")
    assert r.claim("5c2fafaabbdd", "hp2")


def test_stored_class_instance_not_valid_uses_config(caplog):
    with caplog.at_level(logging.ERROR):
        h = Harness(stored(class_instance="garbage"), role="heatpump", device_instance=45)
    assert h.meter.role == "heatpump" and h.meter.instance == 45
    assert "garbage" in caplog.text
