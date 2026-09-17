from pathlib import Path
import pandas as pd

def registrar_metricas(metrics, path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    if metrics is None or metrics.empty:return
    old=pd.read_csv(p) if p.exists() else pd.DataFrame()
    out=pd.concat([old,metrics],ignore_index=True).drop_duplicates()
    out.to_csv(p,index=False,encoding="utf-8-sig")

def detectar_degradacion(metrics_log):
    if metrics_log is None or metrics_log.empty:return []
    warnings=[]
    if "Modelo" not in metrics_log:return warnings
    for model,g in metrics_log.groupby("Modelo"):
        if len(g)<2:continue
        recent=g.tail(2)
        if "Brier" in recent and recent["Brier"].notna().all():
            vals=recent["Brier"].astype(float).tolist()
            if vals[-1] > vals[0] + 0.025:
                warnings.append({"Modelo":model,"Motivo":"Brier empeoró en las dos últimas mediciones."})
    return warnings
