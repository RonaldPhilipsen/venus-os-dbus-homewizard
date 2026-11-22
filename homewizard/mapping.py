"""Map HomeWizard measurements to Victron D-Bus paths."""

from typing import Any, Dict, List, Optional

from homewizard.roles import Product

FLIPPED_ROLES = ("pvinverter", "genset")
COMMON_PATHS = [
    "/Ac/Power",
    "/Ac/Frequency",
    "/Ac/Energy/Forward",
    "/Ac/Energy/Reverse",
    "/NrOfPhases",
]


def measurement_paths(product: Product, phase: int) -> List[str]:
    """Return the D-Bus paths that this meter publishes."""
    paths = list(COMMON_PATHS)
    if product.phases == 3:
        for n in (1, 2, 3):
            paths += ["/Ac/L%d/Power" % n, "/Ac/L%d/Voltage" % n, "/Ac/L%d/Current" % n]
    else:
        paths += [
            "/Ac/L%d/Power" % phase,
            "/Ac/L%d/Voltage" % phase,
            "/Ac/L%d/Current" % phase,
            "/Ac/L%d/Energy/Forward" % phase,
            "/Ac/L%d/Energy/Reverse" % phase,
        ]
    return paths


def to_values(
    m: Dict[str, Any], product: Product, role: str, phase: int, reverse: bool
) -> Dict[str, Any]:
    """Map one measurement to D-Bus values. Missing fields become None."""
    flip = (role in FLIPPED_ROLES) != reverse
    if flip:
        forward_key, reverse_key = "energy_export_kwh", "energy_import_kwh"
    else:
        forward_key, reverse_key = "energy_import_kwh", "energy_export_kwh"

    values = {
        "/Ac/Power": _signed(m.get("power_w"), flip),
        "/Ac/Frequency": m.get("frequency_hz"),
        "/Ac/Energy/Forward": m.get(forward_key),
        "/Ac/Energy/Reverse": m.get(reverse_key),
        "/NrOfPhases": _phase_count(m, product),
    }
    if product.phases == 3:
        for n in (1, 2, 3):
            values["/Ac/L%d/Power" % n] = _signed(m.get("power_l%d_w" % n), flip)
            values["/Ac/L%d/Voltage" % n] = m.get("voltage_l%d_v" % n)
            values["/Ac/L%d/Current" % n] = m.get("current_l%d_a" % n)
    else:
        values["/Ac/L%d/Power" % phase] = _signed(m.get("power_w"), flip)
        values["/Ac/L%d/Voltage" % phase] = m.get("voltage_v")
        values["/Ac/L%d/Current" % phase] = m.get("current_a")
        values["/Ac/L%d/Energy/Forward" % phase] = m.get(forward_key)
        values["/Ac/L%d/Energy/Reverse" % phase] = m.get(reverse_key)
    return values


def _signed(value: Optional[float], flip: bool) -> Optional[float]:
    if value is None or not flip:
        return value
    return -value


def _phase_count(m: Dict[str, Any], product: Product) -> int:
    if product.kind == "p1" and m.get("power_l2_w") is None and m.get("power_l3_w") is None:
        return 1
    return product.phases
