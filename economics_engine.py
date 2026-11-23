from __future__ import annotations
import math
import numpy as np
import pandas as pd
from scipy.optimize import brentq

from cost_inputs import (
    POWER_MW, DURATION_H, DELIVERED_MWH_DAY, ANALYSIS_YEARS, CYCLES_PER_YEAR,
    PNNL, WACC_REAL, CHARGE_PRICE_USD_KWH, FULL_MODEL_REF, VRFB_BOTTOM_UP, NREL_2025,
)

def annuity_factor(r=WACC_REAL, years=ANALYSIS_YEARS):
    return float(sum((1.0 + r) ** (-t) for t in range(1, int(years) + 1)))

def pv_delivered_mwh(r=WACC_REAL, years=ANALYSIS_YEARS, daily_mwh=DELIVERED_MWH_DAY):
    return float(daily_mwh * CYCLES_PER_YEAR * annuity_factor(r, years))

def v2o5_mass_kg(electrolyte_m3: float, c_v_mol_m3: float = 1600.0) -> float:
    return float(c_v_mol_m3 * electrolyte_m3 * 0.5 * 0.18188)

def pnnl_soft_capex_usd(power_mw=POWER_MW, duration_h=DURATION_H):
    p = PNNL["VRFB"]; e_kwh = power_mw * duration_h * 1000.0; p_kw = power_mw * 1000.0
    return {
        "DC BOS": p["dc_bos_usd_kwh"] * e_kwh,
        "power equipment": p["power_equip_usd_kw"] * p_kw,
        "controls": p["controls_usd_kw"] * p_kw,
        "grid": p["grid_usd_kw"] * p_kw,
        "system integration": p["system_integration_usd_kwh"] * e_kwh,
        "EPC": p["epc_usd_kwh"] * e_kwh,
        "project development": p["project_dev_usd_kwh"] * e_kwh,
    }

def vrfb_bottom_up_capex(*, area_m2=FULL_MODEL_REF["area_m2"], electrolyte_m3=FULL_MODEL_REF["electrolyte_m3"],
                         stack_usd_m2=VRFB_BOTTOM_UP["stack_usd_m2"], v2o5_usd_kg=VRFB_BOTTOM_UP["v2o5_usd_kg"],
                         import_frac=VRFB_BOTTOM_UP["import_frac"], process_frac=VRFB_BOTTOM_UP["process_frac"],
                         tank_usd_m3=VRFB_BOTTOM_UP["tank_usd_m3"], cooling_mode="included",
                         power_mw=POWER_MW, duration_h=DURATION_H):
    vkg = v2o5_mass_kg(electrolyte_m3)
    vanad = vkg * v2o5_usd_kg * (1.0 + import_frac)
    block = {
        "stack": area_m2 * stack_usd_m2,
        "V2O5": vanad,
        "electrolyte processing": vanad * process_frac,
        "tanks": electrolyte_m3 * VRFB_BOTTOM_UP["tank_headspace"] * tank_usd_m3,
        "auto-transfer hardware": VRFB_BOTTOM_UP["auto_transfer_usd"],
    }
    soft = pnnl_soft_capex_usd(power_mw, duration_h)
    cooling = 0.0 if cooling_mode == "included" else VRFB_BOTTOM_UP["cooling_incremental_usd"]
    total = sum(block.values()) + sum(soft.values()) + cooling
    return total, {**block, **soft, "incremental cooling": cooling}

def _delta_capex_lcos(delta_usd: float, wacc=WACC_REAL, years=ANALYSIS_YEARS, daily_mwh=DELIVERED_MWH_DAY) -> float:
    return float(delta_usd / pv_delivered_mwh(wacc, years, daily_mwh))

def _delta_annual_lcos(delta_usd_yr: float, daily_mwh=DELIVERED_MWH_DAY) -> float:
    return float(delta_usd_yr / (daily_mwh * CYCLES_PER_YEAR))

def _delta_rte_lcos(new_rte: float, ref_rte: float, price: float) -> float:
    return float(1000.0 * price * (1.0/new_rte - 1.0/ref_rte))

def vrfb_lcos(*, rte=FULL_MODEL_REF["rte_20y"], area_m2=FULL_MODEL_REF["area_m2"],
              electrolyte_m3=FULL_MODEL_REF["electrolyte_m3"], cost_mode="bottom_up",
              stack_usd_m2=VRFB_BOTTOM_UP["stack_usd_m2"], v2o5_usd_kg=VRFB_BOTTOM_UP["v2o5_usd_kg"],
              process_frac=VRFB_BOTTOM_UP["process_frac"], charge_price=CHARGE_PRICE_USD_KWH,
              wacc=WACC_REAL, cooling_mode="included", replacement_year=12,
              include_rebalancing=True, terminal_adjustment_usd=0.0):
    ref = PNNL["VRFB"]; parts = {"PNNL v2024 reference": ref["lcos_usd_mwh"]}
    parts["RTE delta"] = _delta_rte_lcos(rte, ref["rte"], charge_price)
    if cost_mode == "PNNL":
        cap_new = ref["installed_usd_kwh"] * POWER_MW * DURATION_H * 1000.0
        cap_parts = {"PNNL installed cost": cap_new}
    elif cost_mode == "bottom_up":
        cap_new, cap_parts = vrfb_bottom_up_capex(area_m2=area_m2, electrolyte_m3=electrolyte_m3,
            stack_usd_m2=stack_usd_m2, v2o5_usd_kg=v2o5_usd_kg, process_frac=process_frac,
            cooling_mode=cooling_mode)
    else:
        raise ValueError("cost_mode must be 'PNNL' or 'bottom_up'")
    cap_ref = ref["installed_usd_kwh"] * POWER_MW * DURATION_H * 1000.0
    parts["CAPEX delta"] = _delta_capex_lcos(cap_new - cap_ref, wacc)
    repl_nominal = ref["stack_repl_usd_kw"] * POWER_MW * 1000.0
    pv_ref = repl_nominal / (1.0 + wacc) ** ref["stack_life_year"]
    pv_new = 0.0 if replacement_year is None or replacement_year > ANALYSIS_YEARS else repl_nominal / (1.0 + wacc) ** replacement_year
    parts["replacement timing delta"] = _delta_capex_lcos(pv_new - pv_ref, wacc)
    parts["rebalancing service"] = _delta_annual_lcos(VRFB_BOTTOM_UP["rebalancing_usd_yr"] if include_rebalancing else 0.0)
    parts["terminal adjustment"] = _delta_capex_lcos(terminal_adjustment_usd / (1.0+wacc)**ANALYSIS_YEARS, wacc)
    total = float(sum(parts.values()))
    return total, parts, {"capex_usd": cap_new, "capex_parts": cap_parts, "rte": rte,
        "service": f"{POWER_MW:g} MW x {DURATION_H:g} h = {DELIVERED_MWH_DAY:g} MWh AC delivered/day",
        "method": "PNNL-anchored delta-LCOS"}

def lfp_lcos(*, capex_mult=1.0, rte=None, charge_price=CHARGE_PRICE_USD_KWH, wacc=WACC_REAL, fom_mult=1.0):
    ref = PNNL["LFP"]; rte = ref["rte"] if rte is None else float(rte)
    parts = {"PNNL v2024 reference": ref["lcos_usd_mwh"]}
    cap_ref = ref["installed_usd_kwh"] * POWER_MW * DURATION_H * 1000.0
    parts["CAPEX delta"] = _delta_capex_lcos(cap_ref * (capex_mult - 1.0), wacc)
    parts["RTE delta"] = _delta_rte_lcos(rte, ref["rte"], charge_price)
    annual_fom = ref["fom_usd_kwyr"] * POWER_MW * 1000.0
    parts["FOM delta"] = _delta_annual_lcos(annual_fom * (fom_mult - 1.0))
    return float(sum(parts.values())), parts, {"rte": rte, "capex_mult": capex_mult}

def nrel_lfp_engineering_lcos(*, charge_price=CHARGE_PRICE_USD_KWH, wacc=WACC_REAL, rte=NREL_2025["rte"]):
    e_kwh = POWER_MW * DURATION_H * 1000.0; p_kw = POWER_MW * 1000.0
    capex = NREL_2025["energy_usd_kwh"]*e_kwh + NREL_2025["power_usd_kw"]*p_kw
    annual_fom = NREL_2025["fom_frac"] * capex; pvE = pv_delivered_mwh(wacc)
    lcos = capex/pvE + annual_fom/(DELIVERED_MWH_DAY*CYCLES_PER_YEAR) + 1000*charge_price/rte
    return float(lcos), {"capex": capex/pvE, "FOM": annual_fom/(DELIVERED_MWH_DAY*CYCLES_PER_YEAR), "charging": 1000*charge_price/rte}

def pair_delta(**kwargs):
    vk={k:v for k,v in kwargs.items() if k in {"rte","area_m2","electrolyte_m3","cost_mode","stack_usd_m2","v2o5_usd_kg","process_frac","charge_price","wacc","cooling_mode","replacement_year","include_rebalancing","terminal_adjustment_usd"}}
    lk={k:v for k,v in kwargs.items() if k in {"capex_mult","lfp_rte","charge_price","wacc","fom_mult"}}
    if "lfp_rte" in lk: lk["rte"]=lk.pop("lfp_rte")
    v=vrfb_lcos(**vk)[0]; l=lfp_lcos(**lk)[0]
    return v,l,v-l

def break_even_v2o5(**kwargs):
    def f(x): return pair_delta(**dict(kwargs,v2o5_usd_kg=x))[2]
    xs=np.linspace(0.5,50.0,100); ys=np.array([f(x) for x in xs])
    ids=np.where(np.sign(ys[:-1])*np.sign(ys[1:])<=0)[0]
    return np.nan if not len(ids) else float(brentq(f,xs[ids[0]],xs[ids[0]+1]))

def break_even_lfp_capex(**kwargs):
    def f(x): return pair_delta(**dict(kwargs,capex_mult=x))[2]
    xs=np.linspace(0.4,2.0,100); ys=np.array([f(x) for x in xs])
    ids=np.where(np.sign(ys[:-1])*np.sign(ys[1:])<=0)[0]
    return np.nan if not len(ids) else float(brentq(f,xs[ids[0]],xs[ids[0]+1]))

def decision_map(v2_grid=None, lfp_capex_grid=None, **kwargs):
    v2_grid=np.linspace(5,30,41) if v2_grid is None else v2_grid
    lfp_capex_grid=np.linspace(0.7,1.5,33) if lfp_capex_grid is None else lfp_capex_grid
    rows=[]
    for v2 in v2_grid:
        for cm in lfp_capex_grid:
            v,l,d=pair_delta(**dict(kwargs,v2o5_usd_kg=float(v2),capex_mult=float(cm)))
            rows.append({"V2O5_USD_kg":v2,"LFP_capex_mult":cm,"LCOS_VRFB":v,"LCOS_LFP":l,"Delta":d})
    return pd.DataFrame(rows)

def live_projected_lcos(design_lcos: float, design_rte: float, live_rte: float, charge_price=CHARGE_PRICE_USD_KWH) -> float:
    live_rte=float(np.clip(live_rte,0.35,0.95)); design_rte=float(np.clip(design_rte,0.35,0.95))
    return float(design_lcos + 1000*charge_price*(1/live_rte - 1/design_rte))

def baseline_summary():
    v,vp,vi=vrfb_lcos(); l,lp,li=lfp_lcos()
    return {"VRFB":v,"LFP":l,"Delta":v-l,"BE_V2O5":break_even_v2o5(),"BE_LFP_CAPEX":break_even_lfp_capex(),
            "VRFB_info":vi,"LFP_info":li}
