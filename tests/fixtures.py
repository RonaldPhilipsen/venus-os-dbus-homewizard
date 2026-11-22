"""Sample /api/measurement payloads, with the field names of the HomeWizard API v2."""

P1_3PHASE = {
    "timestamp": "2026-11-22T12:00:00",
    "power_w": 1500.0,
    "power_l1_w": 500.0,
    "power_l2_w": 450.0,
    "power_l3_w": 550.0,
    "voltage_l1_v": 230.1,
    "voltage_l2_v": 229.8,
    "voltage_l3_v": 231.2,
    "current_l1_a": 2.2,
    "current_l2_a": 2.0,
    "current_l3_a": 2.4,
    "frequency_hz": 50.0,
    "energy_import_kwh": 12345.678,
    "energy_export_kwh": 234.5,
}

P1_1PHASE = {
    "power_w": 500.0,
    "power_l1_w": 500.0,
    "voltage_l1_v": 230.1,
    "current_l1_a": 2.2,
    "frequency_hz": 50.0,
    "energy_import_kwh": 12345.678,
    "energy_export_kwh": 234.5,
}

KWH1 = {
    "power_w": 800.0,
    "voltage_v": 231.4,
    "current_a": 3.5,
    "frequency_hz": 50.0,
    "energy_import_kwh": 1500.25,
    "energy_export_kwh": 20.5,
}

KWH3 = {
    "power_w": 3200.0,
    "power_l1_w": 1100.0,
    "power_l2_w": 1050.0,
    "power_l3_w": 1050.0,
    "voltage_l1_v": 230.0,
    "voltage_l2_v": 229.5,
    "voltage_l3_v": 231.0,
    "current_l1_a": 4.8,
    "current_l2_a": 4.6,
    "current_l3_a": 4.5,
    "frequency_hz": 50.0,
    "energy_import_kwh": 5000.0,
    "energy_export_kwh": 300.0,
}
