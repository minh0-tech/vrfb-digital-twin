from __future__ import annotations

import contextlib, io, json, os, tempfile, zlib, base64
from pathlib import Path
from typing import Any, Dict
import numpy as np
import pandas as pd

FULL_REF = {
    "area_m2": 7000.0,
    "stacks": 560.0,
    "electrolyte_m3": 5746.0,
    "rte_ac": 0.7200,
    "pump_end_kw": 245.0,
}

def _clean(src: str) -> str:
    return src.replace("%matplotlib inline", "")

def load_reduced_model(core_path: str | Path) -> Dict[str, Any]:
    core_path = Path(core_path)
    root = core_path.parent
    chunks = [root / f"model_core_{i}.z64" for i in range(1, 5)]
    packed = "".join(p.read_text(encoding="ascii") for p in chunks)
    core_src = zlib.decompress(base64.b64decode(packed)).decode("utf-8")
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    old_show = plt.show
    plt.show = lambda *a, **k: None
    ns: Dict[str, Any] = {"__name__": "vrfb_v24_runtime"}
    cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exec(compile(_clean(core_src), str(core_path), "exec"), ns)
            finally:
                os.chdir(cwd)
                plt.close("all")
    finally:
        if os.getcwd() != cwd:
            os.chdir(cwd)
        plt.show = old_show
        plt.close("all")
    return ns

class VRFBSimulator:
    def __init__(self, core_path: str | Path):
        self.core_path = Path(core_path)
        self.ns = load_reduced_model(self.core_path)
        self.ns["OPS"]["E_SIZE"] = 1.0
        self._calibrate_full_reference()

    def _configure(self, *, temperature_c: float, flow_cm_min: float, m: float,
                   ve_target: float, basis: str, ohm_mode: str,
                   power_mw: float = 10.0, hours: float = 10.0):
        n = self.ns
        if not (10.0 <= temperature_c <= 40.0):
            raise ValueError("Fig.5 기반 검증 온도 범위는 10–40 °C입니다.")
        if not (14.5 <= flow_cm_min <= 58.0):
            raise ValueError("유속은 Charvát 데이터 범위 14.5–58 cm/min 안에서 사용하세요.")
        if basis not in ("C1", "C2"):
            raise ValueError("basis must be C1 or C2")
        if ohm_mode not in ("anchored", "raw", "fit_only"):
            raise ValueError("invalid ohm_mode")
        n["ASSEMBLY_BASIS"] = basis
        n["OHM_MODE"] = ohm_mode
        n["VE_TARGET"] = float(ve_target)
        n["FLOW_MAIN_CM_MIN"] = float(flow_cm_min)
        n["m"] = float(m)
        n["OPS"]["E_SIZE"] = 1.0
        n["set_temperature"](float(temperature_c))
        n["SD"]["P_AC"] = float(power_mw) * 1e6
        n["SD"]["HOURS"] = float(hours)
        n["P_DC_DIS"] = n["SD"]["P_AC"] * (1 + n["SD"]["AUX_FRAC"]) / n["SD"]["ETA_PCS"]
        n["P_DC_CHG"] = n["SD"]["P_AC"] * n["SD"]["ETA_PCS"]
        n["SOC_LO_OP"] = n["SD"]["SOC_LO"]
        n["SOC_TOP"] = n["SD"]["SOC_HI"]

    def _raw_design(self, *, temperature_c=25.0, flow_cm_min=29.0, m=1.0,
                    ve_target=0.90, basis="C2", ohm_mode="anchored",
                    cr=None, power_mw=10.0, hours=10.0):
        self._configure(temperature_c=temperature_c, flow_cm_min=flow_cm_min, m=m,
                        ve_target=ve_target, basis=basis, ohm_mode=ohm_mode,
                        power_mw=power_mw, hours=hours)
        n = self.ns
        res = n["Resist"](ohm_mode=ohm_mode, basis=basis)
        cr_opt = float(n["optimal_cr"](m=m, ve=ve_target, ohm_mode=ohm_mode))
        cr_use = cr_opt if cr is None else float(cr)
        out, prof = n["design_stack"]("reduced-runtime", res, cr_use, m)
        return res, cr_opt, cr_use, out, prof

    def _calibrate_full_reference(self):
        _, _, _, out, _ = self._raw_design()
        self.cal = {
            "area": FULL_REF["area_m2"] / float(out["설치 면적 (m²)"]),
            "stacks": FULL_REF["stacks"] / float(out["총 스택"]),
            "electrolyte": FULL_REF["electrolyte_m3"] / float(out["전해액 합계 (m³)"]),
            "rte": FULL_REF["rte_ac"] / (float(out["왕복효율 AC (PCS 왕복·펌프·보조 포함, %)"]) / 100.0),
            "pump": FULL_REF["pump_end_kw"] / float(out["펌프 동력 @방전 끝 (kW, 펠트+배관)"]),
        }

    def evaluate(self, *, temperature_c=25.0, flow_cm_min=29.0, m=1.0, ve_target=0.90,
                 basis="C2", ohm_mode="anchored", use_optimal_cr=True, cr_manual=0.30,
                 power_mw=10.0, hours=10.0) -> Dict[str, Any]:
        res, cr_opt, cr, raw, prof = self._raw_design(
            temperature_c=temperature_c, flow_cm_min=flow_cm_min, m=m,
            ve_target=ve_target, basis=basis, ohm_mode=ohm_mode,
            cr=None if use_optimal_cr else cr_manual, power_mw=power_mw, hours=hours)
        n = self.ns
        i_star, p_net = n["net_power_density"](cr, res, m=m, ve=ve_target)
        ro, rct, rmtc, rmtd = n["main_resistances"](res, cr)
        vchg = n["v_charge"](i_star, cr, res, m=m)
        vdis = n["v_discharge"](i_star, cr, res, m=m)
        area = float(raw["설치 면적 (m²)"]) * self.cal["area"]
        el = float(raw["전해액 합계 (m³)"]) * self.cal["electrolyte"]
        rte_raw = float(raw["왕복효율 AC (PCS 왕복·펌프·보조 포함, %)"]) / 100.0
        rte = float(np.clip(rte_raw * self.cal["rte"], 0.45, 0.92))
        stacks = int(round(float(raw["총 스택"]) * self.cal["stacks"] / 14.0) * 14)
        pump_kw = float(raw["펌프 동력 @방전 끝 (kW, 펠트+배관)"]) * self.cal["pump"]
        return {
            "temperature_c": float(temperature_c), "flow_cm_min": float(flow_cm_min), "m": float(m),
            "ve_target": float(ve_target), "basis": basis, "ohm_mode": ohm_mode,
            "cr": cr, "cr_opt": cr_opt, "i_star": float(i_star), "p_net": float(p_net),
            "vchg": float(vchg), "vdis": float(vdis), "ve": float(vdis/vchg),
            "R_ohm": float(ro), "R_CT": float(rct), "R_MT_chg": float(rmtc), "R_MT_dis": float(rmtd),
            "porosity": float(n["eps"](cr)), "permeability": float(n["kappa"](cr)),
            "pump_wcm2": float(n["pump_main_Wcm2"](cr)),
            "stack_raw": raw, "stack_profile": prof.copy(),
            "stack": {
                "area_m2": area, "stacks": stacks, "electrolyte_m3": el, "rte_ac": rte,
                "pump_end_kw": pump_kw, "service_mwh": power_mw*hours,
                "all_constraints_ok": bool(raw["모든 SoC 제약 통과"]),
                "charge_h": float(raw["충전 시간 (h, CE 반영)"]),
                "dp_end_kpa": float(raw["스택 ΔP @방전 끝 (kPa)"]),
                "heat_end_kw": float(raw["발열 @방전 끝 (kW)"]),
            },
            "calibration": dict(self.cal),
        }

    def cr_scan(self, **kwargs) -> pd.DataFrame:
        rows=[]
        for cr in np.linspace(0.10,0.50,81):
            r=self.evaluate(use_optimal_cr=False,cr_manual=float(cr),**kwargs)
            rows.append({"CR (%)":100*cr,"Pnet (mW/cm²)":1e3*r["p_net"],"i* (mA/cm²)":1e3*r["i_star"],
                         "RΩ":r["R_ohm"],"RCT":r["R_CT"],"RMTdis":r["R_MT_dis"],
                         "Area (m²)":r["stack"]["area_m2"],"RTE (%)":100*r["stack"]["rte_ac"]})
        return pd.DataFrame(rows)

    def temperature_scan(self, temperatures=None, **kwargs) -> pd.DataFrame:
        if temperatures is None:
            temperatures=np.arange(10.0,40.1,2.5)
        rows=[]
        for t in temperatures:
            r=self.evaluate(temperature_c=float(t),**kwargs)
            rows.append({"T (°C)":float(t),"CRopt (%)":100*r["cr_opt"],"i* (mA/cm²)":1e3*r["i_star"],
                         "Pnet (mW/cm²)":1e3*r["p_net"],"Area (m²)":r["stack"]["area_m2"],"RTE (%)":100*r["stack"]["rte_ac"]})
        return pd.DataFrame(rows)

    def twin_profile(self, *, scenario="normal", n_points=61, **kwargs) -> pd.DataFrame:
        if scenario not in ("normal","flow_restriction","thermal_drift","ohmic_degradation"):
            raise ValueError("invalid scenario")
        base=self.evaluate(**kwargs)
        cr=base["cr"]; prof=base["stack_profile"].sort_values("SOC")
        soc_grid=prof["SOC"].to_numpy(float); i_grid=prof["i_dis"].to_numpy(float); f_grid=prof["v_dis"].to_numpy(float)
        hours=float(kwargs.get("hours",10.0)); tc=float(kwargs.get("temperature_c",25.0)); m=float(kwargs.get("m",1.0))
        basis=kwargs.get("basis","C2"); ohm=kwargs.get("ohm_mode","anchored"); ve=float(kwargs.get("ve_target",0.90)); power=float(kwargs.get("power_mw",10.0))
        rng=np.random.default_rng(24024); rows=[]
        for th in np.linspace(0,hours,n_points):
            f=th/max(hours,1e-9); soc=0.90-0.70*f
            i=float(np.interp(soc,soc_grid,i_grid)); flow_cmd=float(np.interp(soc,soc_grid,f_grid))
            t_true=tc+2.0*(1-np.exp(-3*f))
            if scenario=="thermal_drift" and f>0.55: t_true += 10.0*(f-0.55)/0.45
            flow_true=flow_cmd
            if scenario=="flow_restriction" and f>0.58: flow_true *= 1-0.28*min(1,(f-0.58)/0.25)
            t_s=float(np.clip(t_true+rng.normal(0,0.05),10,40)); flow_s=float(np.clip(flow_true+rng.normal(0,0.18),14.5,58))
            soc_s=float(np.clip(soc+rng.normal(0,0.001),0.2,0.9)); i_s=max(1e-6,i*(1+rng.normal(0,0.0015)))
            self._configure(temperature_c=t_s,flow_cm_min=29,m=m,ve_target=ve,basis=basis,ohm_mode=ohm,power_mw=power,hours=hours)
            n=self.ns; res=n["Resist"](ohm_mode=ohm,basis=basis)
            _,v_pred,state=n["voltage_at_soc_flow"](res,cr,soc_s,flow_s,i_s,m)
            dp_pred=float(n["stack_dp"](cr,flow_s)/1e3)
            v_bias=0.0; dp_factor=1.0
            if scenario=="ohmic_degradation" and f>0.58: v_bias -= i_s*0.10*min(1,(f-0.58)/0.30)
            if scenario=="flow_restriction" and f>0.58: dp_factor += 0.35*min(1,(f-0.58)/0.25)
            v_sensor=float(v_pred+v_bias+rng.normal(0,0.0012)); dp_sensor=float(dp_pred*dp_factor+rng.normal(0,0.35))
            v_res=1e3*(v_sensor-v_pred); dp_res=dp_sensor-dp_pred
            flow_err=100*(flow_s-flow_cmd)/max(flow_cmd,1e-9)
            alarms=[]
            if abs(v_res)>5: alarms.append("전압 잔차")
            if abs(dp_res)>5: alarms.append("압력 잔차")
            if flow_err<-10: alarms.append("유량 저하")
            if t_s>=37: alarms.append("고온")
            p_ratio=max(0.65,min(1.05,(v_sensor/max(float(v_pred),1e-9))*(flow_s/max(flow_cmd,1e-9))**0.03))
            rte_live=float(np.clip(base["stack"]["rte_ac"]*p_ratio,0.45,0.92))
            rows.append({"time_h":th,"SOC":soc_s,"T_C":t_s,"flow_cmd":flow_cmd,"flow_sensor":flow_s,
                         "current_mAcm2":1e3*i_s,"V_sensor":v_sensor,"V_twin":float(v_pred),"V_residual_mV":v_res,
                         "dP_sensor_kPa":dp_sensor,"dP_twin_kPa":dp_pred,"dP_residual_kPa":dp_res,
                         "R_ohm":float(state["R_ohm"]),"R_CT":float(state["R_CT"]),"R_MT_dis":float(state["R_MT_dis"]),
                         "RTE_live":rte_live,"alarm":"정상" if not alarms else " / ".join(alarms)})
        return pd.DataFrame(rows)
