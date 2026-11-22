"""Configuration loader for dbus-homewizard."""
import configparser
import math
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

ROLES: Tuple[str, ...] = ("grid", "pvinverter", "genset", "acload", "heatpump", "evcharger")
PHASES = {"L1": 1, "L2": 2, "L3": 3}
METER_PREFIX = "METER:"
TOKEN_PATTERN = re.compile(r"[0-9A-F]{32}")
FIRST_DEVICE_INSTANCE = 40


@dataclass
class MeterConfig:
    name: str
    host: str
    token: str
    role: Optional[str]
    device_instance: int
    custom_name: Optional[str]
    phase: int
    reverse: bool
    position: int
    poll_interval_s: float
    offline_timeout_s: Optional[float]
    verify_tls: bool


@dataclass
class Config:
    sign_of_life_minutes: int
    meters: List[MeterConfig]


def load_config(path: str) -> Config:
    parser = configparser.ConfigParser(interpolation=None)
    if not parser.read(path):
        raise ValueError("cannot read config file: %s" % path)

    meter_sections = [s for s in parser.sections() if s.startswith(METER_PREFIX)]
    if not meter_sections:
        raise ValueError("config needs at least one [METER:<name>] section")

    sign_of_life = to_int("DEFAULT", "SignOfLifeLog", get(parser["DEFAULT"], "SignOfLifeLog", "10"))
    meters = []
    used_instances = set()
    for index, section_name in enumerate(meter_sections):
        meter = load_meter(parser[section_name], section_name, index)
        if meter.device_instance in used_instances:
            raise ValueError(
                "[%s] DeviceInstance %d is already used by another meter"
                % (section_name, meter.device_instance)
            )
        used_instances.add(meter.device_instance)
        meters.append(meter)
    return Config(sign_of_life_minutes=sign_of_life, meters=meters)


def load_meter(section, section_name: str, index: int) -> MeterConfig:
    host = get(section, "Host", "")
    if not host:
        raise ValueError("[%s] Host is required" % section_name)

    token = get(section, "Token", "").upper()
    if not token:
        raise ValueError("[%s] Token is required" % section_name)
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("[%s] Token must be 32 hex characters" % section_name)

    role = get(section, "Role", "") or None
    if role is not None and role not in ROLES:
        raise ValueError(
            "[%s] Role must be one of %s, not %s" % (section_name, ", ".join(ROLES), role)
        )

    phase_name = get(section, "Phase", "L1").upper()
    if phase_name not in PHASES:
        raise ValueError("[%s] Phase must be L1, L2 or L3, not %s" % (section_name, phase_name))

    position = to_int(section_name, "Position", get(section, "Position", "0"))
    if position not in (0, 1, 2):
        raise ValueError("[%s] Position must be 0, 1 or 2, not %d" % (section_name, position))

    offline_raw = get(section, "OfflineTimeoutSeconds", "")
    offline_timeout = None
    if offline_raw:
        offline_timeout = positive_float(section_name, "OfflineTimeoutSeconds", offline_raw)

    return MeterConfig(
        name=section_name[len(METER_PREFIX):],
        host=host,
        token=token,
        role=role,
        device_instance=to_int(
            section_name,
            "DeviceInstance",
            get(section, "DeviceInstance", str(FIRST_DEVICE_INSTANCE + index)),
        ),
        custom_name=get(section, "CustomName", "") or None,
        phase=PHASES[phase_name],
        reverse=flag(section, "Reverse", "0"),
        position=position,
        poll_interval_s=positive_float(
            section_name, "PollIntervalSeconds", get(section, "PollIntervalSeconds", "1")
        ),
        offline_timeout_s=offline_timeout,
        verify_tls=flag(section, "VerifyTls", "1"),
    )


def get(section, key: str, default: str) -> str:
    """Return the stripped value of a key, or the default when it is empty or missing."""
    raw = str(section.get(key, "")).strip()
    return raw if raw else default


def flag(section, key: str, default: str) -> bool:
    return get(section, key, default).lower() in ("1", "true", "yes", "on")


def to_int(section_name: str, key: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ValueError("[%s] %s must be a whole number, not %s" % (section_name, key, raw))


def positive_float(section_name: str, key: str, raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise ValueError("[%s] %s must be a number, not %s" % (section_name, key, raw))
    if not (math.isfinite(value) and value > 0):
        raise ValueError("[%s] %s must be greater than 0, not %s" % (section_name, key, raw))
    return value
