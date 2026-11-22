"""Victron D-Bus paths, their text formats, and the function that fills them.

publish uses only [] get and [] set, because VeDbusService has no other
mapping methods (no .get). So this module does not import dbus or vedbus.
"""

from typing import Any, Callable, Dict, List, MutableMapping, Optional

WRITEABLE_PATHS = ("/Role", "/CustomName", "/Position")


def _unit(fmt: str) -> Callable[[str, Any], str]:
    def text(path: str, value: Any) -> str:
        if value is None:
            return "---"
        return fmt.format(value)

    return text


_w = _unit("{:.0f}W")
_v = _unit("{:.1f}V")
_a = _unit("{:.1f}A")
_kwh = _unit("{:.2f}kWh")
_hz = _unit("{:.2f}Hz")
_plain = _unit("{}")

_BY_LAST_SEGMENT = {
    "Power": _w,
    "Voltage": _v,
    "Current": _a,
    "Frequency": _hz,
}


def text_for(path: str) -> Callable[[str, Any], str]:
    """Return the text formatter for a path.

    Energy paths (/Ac/Energy/Forward, /Ac/L1/Energy/Reverse) use kWh. Other
    paths use the last segment, such as Power or Voltage.
    """
    if "/Energy/" in path:
        return _kwh
    return _BY_LAST_SEGMENT.get(path.rsplit("/", 1)[-1], _plain)


def _read(svc: MutableMapping[str, Any], path: str) -> Any:
    """Return the value of path, or None when the service does not have it."""
    try:
        return svc[path]
    except KeyError:
        return None


def publish(
    svc: MutableMapping[str, Any], paths: List[str], values: Optional[Dict[str, Any]]
) -> None:
    """Write the values of paths, or clear them when values is None.

    Sets /Connected to 1 with values, or 0 without. Then counts /UpdateIndex
    up modulo 256, as smartevse.dbus_service.publish_state does.
    """
    for path in paths:
        svc[path] = None if values is None else values.get(path)
    svc["/Connected"] = 0 if values is None else 1
    index = _read(svc, "/UpdateIndex")
    svc["/UpdateIndex"] = 0 if index is None else (index + 1) % 256
