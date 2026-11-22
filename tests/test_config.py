import pytest

from homewizard.config import ROLES, load_config

TOKEN = "A" * 32


def write(tmp_path, text):
    path = tmp_path / "config.ini"
    path.write_text(text)
    return str(path)


def meter(extra="", token=TOKEN, host="10.0.0.5", section="METER:hp"):
    return "[%s]\nHost = %s\nToken = %s\n%s" % (section, host, token, extra)


def test_roles_are_in_constraint_order():
    assert ROLES == ("grid", "pvinverter", "genset", "acload", "heatpump", "evcharger")


def test_minimal_meter_gets_defaults(tmp_path):
    cfg = load_config(write(tmp_path, meter()))
    m = cfg.meters[0]
    assert cfg.sign_of_life_minutes == 10
    assert (m.name, m.host, m.role, m.custom_name) == ("hp", "10.0.0.5", None, None)
    assert (m.phase, m.reverse, m.position, m.verify_tls) == (1, False, 0, True)
    assert m.poll_interval_s == 1.0 and m.offline_timeout_s is None
    assert m.device_instance == 40


def test_default_device_instance_counts_up_per_section(tmp_path):
    text = meter(section="METER:a") + "\n" + meter(section="METER:b")
    cfg = load_config(write(tmp_path, text))
    assert [m.device_instance for m in cfg.meters] == [40, 41]


def test_default_section_values_apply_to_meters(tmp_path):
    text = "[DEFAULT]\nPollIntervalSeconds = 2\n\n" + meter()
    cfg = load_config(write(tmp_path, text))
    assert cfg.meters[0].poll_interval_s == 2.0


def test_token_is_normalized(tmp_path):
    cfg = load_config(write(tmp_path, meter(token="  " + "ab" * 16 + "  ")))
    assert cfg.meters[0].token == "AB" * 16


def test_phase_l3_maps_to_3(tmp_path):
    cfg = load_config(write(tmp_path, meter("Phase = L3\n")))
    assert cfg.meters[0].phase == 3


def test_empty_optional_values_mean_none(tmp_path):
    text = meter("Role =\nCustomName =\nOfflineTimeoutSeconds =\n")
    m = load_config(write(tmp_path, text)).meters[0]
    assert (m.role, m.custom_name, m.offline_timeout_s) == (None, None, None)


def test_explicit_values_are_read(tmp_path):
    text = meter(
        "Role = grid\nDeviceInstance = 52\nCustomName = Main\nPhase = L2\n"
        "Reverse = 1\nPosition = 2\nPollIntervalSeconds = 0.5\n"
        "OfflineTimeoutSeconds = 7.5\nVerifyTls = 0\n"
    )
    cfg = load_config(write(tmp_path, text))
    m = cfg.meters[0]
    assert (m.role, m.device_instance, m.custom_name) == ("grid", 52, "Main")
    assert (m.phase, m.reverse, m.position) == (2, True, 2)
    assert m.poll_interval_s == 0.5 and m.offline_timeout_s == 7.5
    assert m.verify_tls is False


def test_missing_meter_section_is_an_error(tmp_path):
    with pytest.raises(ValueError):
        load_config(write(tmp_path, "[DEFAULT]\nSignOfLifeLog = 10\n"))


@pytest.mark.parametrize(
    "text, key",
    [
        (meter().replace("Host = 10.0.0.5\n", ""), "Host"),
        (meter().replace("Token = " + TOKEN + "\n", ""), "Token"),
        (meter(token="A" * 31), "Token"),
        (meter(token="G" * 32), "Token"),
        (meter("Role = boiler\n"), "Role"),
        (meter("Phase = L4\n"), "Phase"),
        (meter("Position = 3\n"), "Position"),
        (meter("PollIntervalSeconds = 0\n"), "PollIntervalSeconds"),
        (meter("OfflineTimeoutSeconds = -1\n"), "OfflineTimeoutSeconds"),
    ],
)
def test_invalid_meter_value_names_section_and_key(tmp_path, text, key):
    with pytest.raises(ValueError) as err:
        load_config(write(tmp_path, text))
    assert "METER:hp" in str(err.value) and key in str(err.value)


def test_duplicate_device_instance_is_an_error(tmp_path):
    text = meter("DeviceInstance = 50\n", section="METER:a") + "\n" + meter(
        "DeviceInstance = 50\n", section="METER:b"
    )
    with pytest.raises(ValueError):
        load_config(write(tmp_path, text))


def test_flag_off_is_false(tmp_path):
    cfg = load_config(write(tmp_path, meter("Reverse = off\n")))
    assert cfg.meters[0].reverse is False


def test_empty_flag_uses_default(tmp_path):
    cfg = load_config(write(tmp_path, meter("VerifyTls =\n")))
    assert cfg.meters[0].verify_tls is True


def test_invalid_flag_names_section_and_key(tmp_path):
    with pytest.raises(ValueError) as err:
        load_config(write(tmp_path, meter("VerifyTls = fasle\n")))
    assert "METER:hp" in str(err.value) and "VerifyTls" in str(err.value)
