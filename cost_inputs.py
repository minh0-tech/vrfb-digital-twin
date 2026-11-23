"""Source-aligned constants for the rebuilt VRFB techno-economic model.

Values come from the user-provided workbook/PDF in sources/ unless noted.
All monetary figures are nominally treated as source-year dollars unless a delta
calculation explicitly compares against the same PNNL benchmark basis.
"""

POWER_MW = 10.0
DURATION_H = 10.0
DELIVERED_MWH_DAY = POWER_MW * DURATION_H
ANALYSIS_YEARS = 20
CYCLES_PER_YEAR = 365.0

PNNL = {
    "VRFB": {
        "installed_usd_kwh": 504.72,
        "dc_block_usd_kwh": 300.24,
        "dc_bos_usd_kwh": 49.64,
        "power_equip_usd_kw": 133.00,
        "controls_usd_kw": 7.60,
        "grid_usd_kw": 25.00,
        "system_integration_usd_kwh": 38.93,
        "epc_usd_kwh": 46.21,
        "project_dev_usd_kwh": 53.14,
        "fom_usd_kwyr": 12.82,
        "warranty_usd_kwhyr": 1.47,
        "stack_repl_usd_kw": 538.6,
        "recycle_usd_kwh": 26.74,
        "rte": 0.65,
        "stack_life_year": 12,
        "lcos_usd_mwh": 224.8,
    },
    "LFP": {
        "installed_usd_kwh": 379.32,
        "dc_block_usd_kwh": 190.18,
        "dc_bos_usd_kwh": 42.31,
        "power_equip_usd_kw": 73.53,
        "controls_usd_kw": 6.66,
        "grid_usd_kw": 24.86,
        "system_integration_usd_kwh": 39.58,
        "epc_usd_kwh": 43.97,
        "project_dev_usd_kwh": 52.77,
        "fom_usd_kwyr": 9.87,
        "recycle_usd_kwh": 2.65,
        "rte": 0.83,
        "calendar_life_year": 16,
        "lcos_usd_mwh": 184.5,
    },
}

WACC_REAL = 0.0652
CHARGE_PRICE_USD_KWH = 0.03

FULL_MODEL_REF = {
    "area_m2": 7000.0,
    "stacks": 560.0,
    "electrolyte_m3": 5746.0,
    "v2o5_t": 836.1,
    "rte_20y": 0.7200,
    "rte_dynamic_45d": 0.7213,
    "pump_end_kw": 245.0,
    "thermal_power_mwh_yr": 1130.0,
}

VRFB_BOTTOM_UP = {
    "stack_usd_m2": 851.0,
    "stack_low_usd_m2": 316.0,
    "stack_mid_usd_m2": 525.0,
    "v2o5_usd_kg": 11.07,
    "import_frac": 0.05,
    "process_frac": 0.39,
    "tank_usd_m3": 204.0,
    "tank_headspace": 1.10,
    "auto_transfer_usd": 20_000.0,
    "cooling_incremental_usd": 1_640_000.0,
    "rebalancing_usd_yr": 64_000.0,
}

NREL_2025 = {
    "energy_usd_kwh": 241.0,
    "power_usd_kw": 372.0,
    "rte": 0.85,
    "life_year": 15,
    "fom_frac": 0.04,
}
