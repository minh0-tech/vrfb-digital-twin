from pathlib import Path
import os
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplcache"))
Path(os.environ["MPLCONFIGDIR"]).mkdir(exist_ok=True)

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import gradio as gr

from vrfb_backend import VRFBSimulator
import economics_engine as econ
from cost_inputs import PNNL, VRFB_BOTTOM_UP, CHARGE_PRICE_USD_KWH

BASE = Path(__file__).resolve().parent
SIM = VRFBSimulator(BASE / "model_core_1.z64")

def design(T, flow, m, ve, crmode, crmanual):
    r=SIM.evaluate(temperature_c=float(T),flow_cm_min=float(flow),m=float(m),ve_target=float(ve),
                   use_optimal_cr=(crmode=="자동 최적"),cr_manual=float(crmanual)/100)
    s=r["stack"]
    txt=(f"### VRFB 설계 결과\n"
         f"- CR: **{100*r['cr']:.2f}%** (최적 {100*r['cr_opt']:.2f}%)\n"
         f"- i*: **{1e3*r['i_star']:.2f} mA/cm²**\n"
         f"- Pnet: **{1e3*r['p_net']:.2f} mW/cm²**\n"
         f"- 설치면적: **{s['area_m2']:.0f} m²** / 스택 **{s['stacks']}개**\n"
         f"- 전해액: **{s['electrolyte_m3']:.0f} m³**\n"
         f"- 20년 기준 AC RTE: **{100*s['rte_ac']:.2f}%**\n"
         f"- 방전끝 펌프: **{s['pump_end_kw']:.1f} kW** / ΔP **{s['dp_end_kpa']:.1f} kPa**")
    df=pd.DataFrame({
        "항목":["RΩ","RCT","RMT charge","RMT discharge","공극률(%)","투과도(m²)","Vcharge","Vdischarge"],
        "값":[r["R_ohm"],r["R_CT"],r["R_MT_chg"],r["R_MT_dis"],100*r["porosity"],r["permeability"],r["vchg"],r["vdis"]]
    })
    crs=np.linspace(0.10,0.50,17); rows=[]
    for c in crs:
        rr=SIM.evaluate(temperature_c=float(T),flow_cm_min=float(flow),m=float(m),ve_target=float(ve),
                        use_optimal_cr=False,cr_manual=float(c))
        rows.append((100*c,1e3*rr["p_net"],rr["stack"]["area_m2"]))
    a=np.array(rows)
    fig,ax=plt.subplots(figsize=(7,4)); ax.plot(a[:,0],a[:,1]); ax.set_xlabel("CR (%)"); ax.set_ylabel("Pnet (mW/cm²)"); ax.grid(alpha=.25)
    ax2=ax.twinx(); ax2.plot(a[:,0],a[:,2],"--"); ax2.set_ylabel("Area (m²)"); fig.tight_layout()
    return txt,df,fig

def economics(T, flow, m, ve, crmode, crmanual, v2, stackcost, proc, cooling, lfp_cap, lfp_rte):
    r=SIM.evaluate(temperature_c=float(T),flow_cm_min=float(flow),m=float(m),ve_target=float(ve),
                   use_optimal_cr=(crmode=="자동 최적"),cr_manual=float(crmanual)/100)
    v,vp,_=econ.vrfb_lcos(rte=r["stack"]["rte_ac"],area_m2=r["stack"]["area_m2"],electrolyte_m3=r["stack"]["electrolyte_m3"],
        stack_usd_m2=float(stackcost),v2o5_usd_kg=float(v2),process_frac=float(proc),cooling_mode=cooling)
    l,lp,_=econ.lfp_lcos(capex_mult=float(lfp_cap),rte=float(lfp_rte))
    be_v=econ.break_even_v2o5(rte=r["stack"]["rte_ac"],area_m2=r["stack"]["area_m2"],electrolyte_m3=r["stack"]["electrolyte_m3"],
        stack_usd_m2=float(stackcost),process_frac=float(proc),cooling_mode=cooling,capex_mult=float(lfp_cap),lfp_rte=float(lfp_rte))
    be_l=econ.break_even_lfp_capex(rte=r["stack"]["rte_ac"],area_m2=r["stack"]["area_m2"],electrolyte_m3=r["stack"]["electrolyte_m3"],
        stack_usd_m2=float(stackcost),v2o5_usd_kg=float(v2),process_frac=float(proc),cooling_mode=cooling,lfp_rte=float(lfp_rte))
    txt=(f"### 20년 LCOS\n- VRFB: **{v:.1f} $/MWh**\n- LFP: **{l:.1f} $/MWh**\n- Δ(VRFB−LFP): **{v-l:+.1f} $/MWh**\n"
         f"- V₂O₅ break-even: **{'범위 밖' if np.isnan(be_v) else f'{be_v:.2f} $/kg'}**\n"
         f"- LFP CAPEX break-even: **{'범위 밖' if np.isnan(be_l) else f'×{be_l:.3f}'}**\n\n"
         f"PNNL v2024 기준점: VRFB {PNNL['VRFB']['lcos_usd_mwh']:.1f}, LFP {PNNL['LFP']['lcos_usd_mwh']:.1f} $/MWh.")
    df=pd.DataFrame({"VRFB":vp,"LFP":lp}).fillna(0).reset_index().rename(columns={"index":"항목"})
    return txt,df

def twin(scenario,T,flow,m,ve,crmode,crmanual):
    sm={"정상":"normal","유량 저하":"flow_restriction","온도 상승":"thermal_drift","옴저항 열화":"ohmic_degradation"}[scenario]
    r=SIM.evaluate(temperature_c=float(T),flow_cm_min=float(flow),m=float(m),ve_target=float(ve),
                   use_optimal_cr=(crmode=="자동 최적"),cr_manual=float(crmanual)/100)
    df=SIM.twin_profile(scenario=sm,temperature_c=float(T),flow_cm_min=float(flow),m=float(m),ve_target=float(ve),
                        use_optimal_cr=(crmode=="자동 최적"),cr_manual=float(crmanual)/100)
    design_lcos=econ.vrfb_lcos(rte=r["stack"]["rte_ac"],area_m2=r["stack"]["area_m2"],electrolyte_m3=r["stack"]["electrolyte_m3"])[0]
    live_rte=float(df.iloc[-1]["RTE_live"])
    live_lcos=econ.live_projected_lcos(design_lcos,r["stack"]["rte_ac"],live_rte)
    txt=(f"### Digital Twin\n- 시나리오: **{scenario}**\n- 최종 상태: **{df.iloc[-1]['alarm']}**\n"
         f"- RTE: {100*r['stack']['rte_ac']:.2f}% → **{100*live_rte:.2f}%**\n"
         f"- Projected LCOS: {design_lcos:.1f} → **{live_lcos:.1f} $/MWh**\n"
         f"- 최대 |전압 잔차|: **{df['V_residual_mV'].abs().max():.2f} mV**\n"
         f"- 최대 |압력 잔차|: **{df['dP_residual_kPa'].abs().max():.2f} kPa**")
    fig,axs=plt.subplots(2,1,figsize=(8,6),sharex=True)
    axs[0].plot(df.time_h,df.V_sensor,label="sensor"); axs[0].plot(df.time_h,df.V_twin,"--",label="twin"); axs[0].set_ylabel("Cell V"); axs[0].legend(); axs[0].grid(alpha=.25)
    axs[1].plot(df.time_h,df.V_residual_mV,label="V residual (mV)"); axs[1].plot(df.time_h,df.dP_residual_kPa,label="dP residual (kPa)"); axs[1].set_xlabel("time (h)"); axs[1].legend(); axs[1].grid(alpha=.25)
    fig.tight_layout()
    return txt,fig,df[["time_h","SOC","T_C","flow_cmd","flow_sensor","V_sensor","V_twin","V_residual_mV","dP_residual_kPa","RTE_live","alarm"]]

with gr.Blocks(title="VRFB Digital Twin & LCOS") as demo:
    gr.Markdown("# 🔋 VRFB Digital Twin & LCOS Platform\n문헌 기반 물리모델 + 10 MW × 10 h 설계 + 20년 LCOS + reduced-order Digital Twin")
    with gr.Row():
        T=gr.Slider(10,40,value=25,step=.5,label="온도 (°C)")
        flow=gr.Slider(14.5,58,value=29,step=.5,label="유속 (cm/min)")
        m=gr.Slider(.5,3,value=1,step=.1,label="전극 개질 m")
        ve=gr.Slider(.80,.95,value=.90,step=.01,label="VE 목표")
    with gr.Row():
        crmode=gr.Radio(["자동 최적","수동"],value="자동 최적",label="CR")
        crmanual=gr.Slider(10,50,value=30,step=.5,label="수동 CR (%)")

    with gr.Tab("설계"):
        b1=gr.Button("설계 계산")
        o1=gr.Markdown(); o2=gr.Dataframe(); o3=gr.Plot()
        b1.click(design,[T,flow,m,ve,crmode,crmanual],[o1,o2,o3])

    with gr.Tab("LCOS"):
        with gr.Row():
            v2=gr.Number(value=11.07,label="V₂O₅ ($/kg)")
            sc=gr.Number(value=851,label="Stack ($/m²)")
            proc=gr.Slider(.1,.8,value=.39,step=.01,label="전해액 process fraction")
        with gr.Row():
            cool=gr.Radio(["included","incremental"],value="included",label="냉각 CAPEX")
            lcap=gr.Slider(.7,1.5,value=1,step=.01,label="LFP CAPEX multiplier")
            lrte=gr.Slider(.75,.90,value=.83,step=.01,label="LFP RTE")
        b2=gr.Button("LCOS 계산"); e1=gr.Markdown(); e2=gr.Dataframe()
        b2.click(economics,[T,flow,m,ve,crmode,crmanual,v2,sc,proc,cool,lcap,lrte],[e1,e2])

    with gr.Tab("Digital Twin"):
        scen=gr.Radio(["정상","유량 저하","온도 상승","옴저항 열화"],value="정상",label="시나리오")
        b3=gr.Button("Twin 실행"); t1=gr.Markdown(); t2=gr.Plot(); t3=gr.Dataframe()
        b3.click(twin,[scen,T,flow,m,ve,crmode,crmanual],[t1,t2,t3])

    gr.Markdown("**주의:** Projected LCOS는 현재 효율 상태가 지속된다고 가정해 에너지효율 항만 실시간 갱신하는 screening 지표입니다.")

if __name__ == "__main__":
    port=int(os.environ.get("PORT","7860"))
    demo.launch(server_name="0.0.0.0",server_port=port,show_error=True)
