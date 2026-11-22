import pytest

from homewizard.config import ROLES
from homewizard.roles import (
    format_class_instance,
    other_evchargers,
    parse_class_instance,
    product_for,
    service_name,
    settings_base,
    tls_name,
)


def test_p1_allows_grid_only():
    p = product_for("HWE-P1")
    assert p.allowed_roles == ("grid",)
    assert p.default_offline_s == 15
    assert p.cert_type == "p1dongle"


def test_kwh3_allows_all_roles():
    p = product_for("HWE-KWH3")
    assert p.allowed_roles == ROLES
    assert p.phases == 3


def test_unknown_product_raises():
    with pytest.raises(ValueError):
        product_for("HWE-SKT")


def test_names():
    assert tls_name(product_for("HWE-KWH1"), "5c2fafaabbcc") == "appliance/energymeter/5c2fafaabbcc"
    assert service_name("heatpump", "5c2fafaabbcc") == "com.victronenergy.heatpump.homewizard_5c2fafaabbcc"
    assert settings_base("5c2fafaabbcc") == "/Settings/Devices/homewizard_5c2fafaabbcc"


def test_class_instance_round_trip():
    assert parse_class_instance("heatpump:40") == ("heatpump", 40)
    assert format_class_instance("grid", 41) == "grid:41"


@pytest.mark.parametrize("value", ["heatpump", "heatpump:x", "boiler:40"])
def test_parse_class_instance_rejects_bad_values(value):
    with pytest.raises(ValueError):
        parse_class_instance(value)


def test_other_evchargers():
    names = [
        "com.victronenergy.evcharger.smartevse_43",
        "com.victronenergy.evcharger.homewizard_x",
        "com.victronenergy.system",
    ]
    assert other_evchargers(names, "com.victronenergy.evcharger.homewizard_x") == [
        "com.victronenergy.evcharger.smartevse_43"
    ]
