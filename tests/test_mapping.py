from homewizard.mapping import measurement_paths, to_values
from homewizard.roles import product_for
from tests.fixtures import KWH1, KWH3, P1_1PHASE, P1_3PHASE


def test_kwh1_on_l2():
    v = to_values(KWH1, product_for("HWE-KWH1"), "heatpump", 2, False)
    assert set(v) == set(measurement_paths(product_for("HWE-KWH1"), 2))
    assert v["/Ac/L2/Power"] == KWH1["power_w"] and v["/Ac/Power"] == KWH1["power_w"]
    assert v["/Ac/L2/Energy/Forward"] == KWH1["energy_import_kwh"] and v["/NrOfPhases"] == 1
    assert "/Ac/L1/Power" not in v


def test_kwh3_has_no_phase_energy():
    v = to_values(KWH3, product_for("HWE-KWH3"), "acload", 1, False)
    assert v["/Ac/L3/Voltage"] == KWH3["voltage_l3_v"] and "/Ac/L1/Energy/Forward" not in v


def test_kwh3_publishes_three_phases():
    v = to_values(KWH3, product_for("HWE-KWH3"), "acload", 1, False)
    assert v["/Ac/L2/Current"] == KWH3["current_l2_a"] and v["/NrOfPhases"] == 3


def test_pvinverter_flips_sign_and_swaps_energy():
    v = to_values(KWH3, product_for("HWE-KWH3"), "pvinverter", 1, False)
    assert (
        v["/Ac/Power"] == -KWH3["power_w"] and v["/Ac/Energy/Forward"] == KWH3["energy_export_kwh"]
    )
    assert v["/Ac/Energy/Reverse"] == KWH3["energy_import_kwh"]
    assert v["/Ac/L1/Power"] == -KWH3["power_l1_w"]


def test_flip_keeps_voltage_current_and_frequency():
    v = to_values(KWH3, product_for("HWE-KWH3"), "genset", 1, False)
    assert v["/Ac/L1/Voltage"] == KWH3["voltage_l1_v"]
    assert v["/Ac/L1/Current"] == KWH3["current_l1_a"]
    assert v["/Ac/Frequency"] == KWH3["frequency_hz"]


def test_reverse_cancels_pvinverter_flip():
    v = to_values(KWH3, product_for("HWE-KWH3"), "pvinverter", 1, True)
    assert (
        v["/Ac/Power"] == KWH3["power_w"] and v["/Ac/Energy/Forward"] == KWH3["energy_import_kwh"]
    )


def test_reverse_flips_heatpump():
    v = to_values(KWH3, product_for("HWE-KWH3"), "heatpump", 1, True)
    assert (
        v["/Ac/Power"] == -KWH3["power_w"] and v["/Ac/Energy/Forward"] == KWH3["energy_export_kwh"]
    )


def test_p1_single_phase_leaves_l2_l3_empty():
    v = to_values(P1_1PHASE, product_for("HWE-P1"), "grid", 1, False)
    assert v["/Ac/L2/Power"] is None and v["/Ac/L3/Current"] is None and v["/NrOfPhases"] == 1


def test_p1_three_phase_counts_three_phases():
    v = to_values(P1_3PHASE, product_for("HWE-P1"), "grid", 1, False)
    assert v["/NrOfPhases"] == 3 and v["/Ac/L3/Power"] == P1_3PHASE["power_l3_w"]
    assert "/Ac/L1/Energy/Forward" not in v


def test_missing_field_is_none():
    v = to_values({}, product_for("HWE-KWH3"), "grid", 1, False)
    assert all(value is None for path, value in v.items() if path != "/NrOfPhases")


def test_missing_field_stays_none_when_flipped():
    v = to_values({}, product_for("HWE-KWH1"), "pvinverter", 1, False)
    assert v["/Ac/Power"] is None and v["/Ac/Energy/Forward"] is None
