"""Product, role and naming rules for HomeWizard devices."""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from homewizard.config import ROLES

SERVICE_PREFIX = "com.victronenergy."
EVCHARGER_PREFIX = SERVICE_PREFIX + "evcharger."
SETTINGS_ROOT = "/Settings/Devices/"


@dataclass(frozen=True)
class Product:
    product_type: str
    kind: str
    phases: int
    cert_type: str
    allowed_roles: Tuple[str, ...]
    default_role: str
    default_offline_s: float


PRODUCTS: Dict[str, Product] = {
    "HWE-P1": Product("HWE-P1", "p1", 3, "p1dongle", ("grid",), "grid", 15),
    "HWE-KWH1": Product("HWE-KWH1", "kwh", 1, "energymeter", ROLES, "acload", 5),
    "SDM230-wifi": Product("SDM230-wifi", "kwh", 1, "energymeter", ROLES, "acload", 5),
    "HWE-KWH3": Product("HWE-KWH3", "kwh", 3, "energymeter", ROLES, "acload", 5),
    "SDM630-wifi": Product("SDM630-wifi", "kwh", 3, "energymeter", ROLES, "acload", 5),
}


def product_for(product_type: str) -> Product:
    try:
        return PRODUCTS[product_type]
    except KeyError:
        raise ValueError("unknown HomeWizard product type: %s" % product_type)


def tls_name(product: Product, serial: str) -> str:
    return "appliance/%s/%s" % (product.cert_type, serial)


def settings_base(serial: str) -> str:
    return SETTINGS_ROOT + "homewizard_" + serial


def service_name(role: str, serial: str) -> str:
    return "%s%s.homewizard_%s" % (SERVICE_PREFIX, role, serial)


def parse_class_instance(value: str) -> Tuple[str, int]:
    """Split a value such as "heatpump:40" into its role and device instance."""
    role, sep, instance_text = value.partition(":")
    if not sep or role not in ROLES:
        raise ValueError("expected <role>:<instance> with a known role, not %s" % value)
    try:
        instance = int(instance_text)
    except ValueError:
        raise ValueError("device instance must be a whole number, not %s" % value)
    return role, instance


def format_class_instance(role: str, instance: int) -> str:
    return "%s:%d" % (role, instance)


def other_evchargers(bus_names: Iterable[str], own_name: str) -> List[str]:
    return [
        name for name in bus_names
        if name.startswith(EVCHARGER_PREFIX) and name != own_name
    ]
