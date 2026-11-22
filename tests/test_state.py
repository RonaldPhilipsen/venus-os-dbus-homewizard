from homewizard.roles import product_for
from homewizard.state import MeterState


def test_kwh_offline_after_timeout():
    s = MeterState(product_for("HWE-KWH1"), 5)
    assert not s.online(100.0)
    assert s.accept({"power_w": 1}, 100.0) and s.online(104.9) and not s.online(105.0)


def test_p1_same_timestamp_is_not_new():
    s = MeterState(product_for("HWE-P1"), 15)
    assert s.accept({"timestamp": "t1"}, 0.0)
    assert not s.accept({"timestamp": "t1"}, 10.0) and not s.online(15.0)
    assert s.accept({"timestamp": "t2"}, 16.0) and s.online(16.0)


def test_p1_without_timestamp_is_not_new():
    s = MeterState(product_for("HWE-P1"), 15)
    assert not s.accept({"timestamp": None}, 0.0)
    assert not s.accept({}, 1.0)
    assert not s.online(1.0)


def test_missing_timestamp_flag():
    s = MeterState(product_for("HWE-P1"), 15)
    assert s.missing_timestamp is False
    s.accept({"timestamp": "t1"}, 0.0)
    assert s.missing_timestamp is False
    s.accept({}, 1.0)
    assert s.missing_timestamp is True


def test_missing_timestamp_flag_not_set_for_kwh():
    s = MeterState(product_for("HWE-KWH1"), 5)
    s.accept({"power_w": 1}, 0.0)
    assert s.missing_timestamp is False


def test_not_new_measurement_is_not_stored():
    s = MeterState(product_for("HWE-P1"), 15)
    s.accept({"timestamp": "t1", "power_w": 100}, 0.0)
    s.accept({"timestamp": "t1", "power_w": 999}, 1.0)
    assert s.measurement == {"timestamp": "t1", "power_w": 100}


def test_energy_went_down_flag():
    s = MeterState(product_for("HWE-KWH1"), 5)
    s.accept({"energy_import_kwh": 10.0}, 0.0)
    assert not s.energy_went_down
    s.accept({"energy_import_kwh": 9.0}, 1.0)
    assert s.energy_went_down


def test_energy_check_skips_not_new_p1_measurement():
    s = MeterState(product_for("HWE-P1"), 15)
    s.accept({"timestamp": "t1", "energy_import_kwh": 10.0}, 0.0)
    s.accept({"timestamp": "t1", "energy_import_kwh": 9.0}, 1.0)
    assert not s.energy_went_down


def test_offline_uses_injected_monotonic_clock():
    # a "now" value lower than the last accept (a clock that went back) is online, never an exception
    s = MeterState(product_for("HWE-KWH1"), 5)
    s.accept({}, 100.0)
    assert s.online(50.0)
