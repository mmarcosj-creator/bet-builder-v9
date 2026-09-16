"""Interfaz Streamlit para FORECASTER FUTBOL V10 GATUNO."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import traceback

import numpy as np
import pandas as pd
import streamlit as st

import bet_builder_v8_1_robust as base
import bet_forecaster_v10 as v10

APP_VERSION = "V10 Gatuno"
DATA_DIR = Path("app_data_v10")
DATA_DIR.mkdir(exist_ok=True)
MATCH_FILE = DATA_DIR / "latest_matches.csv"
MARKET_FILE = DATA_DIR / "latest_markets.csv"
METRIC_FILE = DATA_DIR / "latest_validation.csv"
META_FILE = DATA_DIR / "meta.json"
AUTO_REFRESH_HOURS = 12

st.set_page_config(
    page_title="Forecaster Fútbol V10 Gatuno",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {padding-top:.65rem; padding-bottom:3rem; max-width:1120px;}
      .hero {padding:1rem 1.05rem; border-radius:20px; border:1px solid rgba(128,128,128,.20);
             background:linear-gradient(135deg,rgba(245,158,11,.12),rgba(34,197,94,.10)); margin-bottom:.75rem;}
      .hero h1 {margin:0; font-size:clamp(1.45rem,6vw,2.15rem);}
      .hero p {margin:.42rem 0 0; opacity:.78;}
      .pill {display:inline-block; padding:.27rem .61rem; border-radius:999px; font-weight:850;
             font-size:.75rem; margin:.35rem .28rem 0 0;}
      .green {background:rgba(34,197,94,.17); color:#16a34a;}
      .amber {background:rgba(245,158,11,.18); color:#d97706;}
      .red {background:rgba(239,68,68,.16); color:#dc2626;}
      .blue {background:rgba(59,130,246,.15); color:#2563eb;}
      .gray {background:rgba(107,114,128,.15); color:#6b7280;}
      .match-card {border:1px solid rgba(128,128,128,.20); border-radius:18px; padding:.95rem 1rem;
                   margin:.85rem 0; background:rgba(128,128,128,.035);}
      .match-title {font-weight:900; font-size:1.13rem; margin:.28rem 0 .15rem;}
      .sub {opacity:.68; font-size:.84rem; margin-bottom:.5rem;}
      .market-row {display:grid; grid-template-columns:1fr auto auto; gap:.6rem;
                   align-items:center; padding:.65rem .75rem; margin:.35rem 0; border-radius:11px;
                   background:rgba(128,128,128,.055); border-left:5px solid #6b7280;}
      .market-row.verde {border-left-color:#22c55e; background:rgba(34,197,94,.07);}
      .market-row.amarillo {border-left-color:#f59e0b; background:rgba(245,158,11,.07);}
      .market-row.rojo {border-left-color:#ef4444; background:rgba(239,68,68,.065);}
      .market-name {font-weight:780;}
      .pick {font-weight:900;}
      .status-emoji {font-size:1.35rem;}
      .info-box {padding:.75rem .85rem; border-radius:14px; background:rgba(59,130,246,.08);
                 border:1px solid rgba(59,130,246,.18); margin:.65rem 0;}
      .stButton button,.stDownloadButton button {min-height:45px; border-radius:13px; font-weight:800;}
      @media(max-width:700px){
        .market-row {grid-template-columns:1fr auto auto;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)

def safe_float(value, default=np.nan):
    try:
        value = float(value)
        return value if np.isfinite(value) else default
    except Exception:
        return default

def apply_gatuno_criteria(markets_df):
    """Aplica los umbrales dinámicos antes de mostrar los datos en pantalla o guardarlos."""
    if markets_df is None or markets_df.empty:
        return markets_df
    df = markets_df.copy()
    for idx, row in df.iterrows():
        prob = safe_float(row.get('Probabilidad', 0))
        pronostico = str(row.get('Pronostico', '')).strip().upper()
        # Si no hay datos, es nulo, o dice SIN PRONOSTICO
        if pd.isna(prob) or pronostico in ["", "SIN PRONOSTICO", "NAN"]:
            df.at[idx, 'Semaforo'] = "ROJO"
        elif prob >= 0.60:
            df.at[idx, 'Semaforo'] = "VERDE"
        elif prob >= 0.50:
            df.at[idx, 'Semaforo'] = "AMARILLO"
        else:
            df.at[idx, 'Semaforo'] = "ROJO"
    return df

def load_meta():
    if not META_FILE.exists():
        return {}
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def cache_current(meta):
    if not meta or not MATCH_FILE.exists() or not MARKET_FILE.exists() or not METRIC_FILE.exists():
        return False
    try:
        now = datetime.now(base.TZ_PERU)
        generated = datetime.fromisoformat(meta["generated_at"])
        end = pd.Timestamp(meta["window_end"]).date()
        return generated.tzinfo is not None and (now - generated).total_seconds() / 3600 <= AUTO_REFRESH_HOURS and now.date() <= end
    except Exception:
        return False

def filter_not_started(frame):
    if frame is None or frame.empty:
        return frame
    result = frame.copy()
    if "KickoffUTC" in result.columns:
        kickoff = pd.to_datetime(result["KickoffUTC"], utc=True, errors="coerce")
        now_utc = pd.Timestamp.now(tz="UTC")
        result = result[(kickoff.isna()) | (kickoff > now_utc)]
    return result.reset_index(drop=True)

def run_and_save():
    matches, markets, metrics, start, end = v10.run_v10()
    matches = filter_not_started(matches)
    markets = filter_not_started(markets)
    
    # Interceptamos y aplicamos la nueva lógica Gatuna antes de guardar
    markets = apply_gatuno_criteria(markets)
    
    matches.to_csv(MATCH_FILE, index=False, encoding="utf-8-sig")
    markets.to_csv(MARKET_FILE, index=False, encoding="utf-8-sig")
    metrics.to_csv(METRIC_FILE, index=False, encoding="utf-8-sig")
    meta = {
        "generated_at": datetime.now(base.TZ_PERU).isoformat(),
        "window_start": str(pd.Timestamp(start).date()),
        "window_end": str(pd.Timestamp(end).date()),
        "matches": int(len(matches)),
        "markets": int(len(markets)),
        "version": APP_VERSION,
    }
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return matches, markets, metrics, meta

def load_data():
    matches = pd.read_csv(MATCH_FILE)
    markets = pd.read_csv(MARKET_FILE)
    metrics = pd.read_csv(METRIC_FILE)
    for frame in (matches, markets):
        frame["Fecha"] = pd.to_datetime(frame["Fecha"], errors="coerce")
    return filter_not_started(matches), filter_not_started(markets), metrics

def wide_forecasts(matches, markets):
    if matches.empty:
        return matches.copy()
    keys = ["Fecha", "HoraPeru", "Competicion", "Local", "Visitante"]
    base_cols = [c for c in keys + ["GolesEsperadosLocal", "GolesEsperadosVisitante", "RiesgoRotacion", "EstadoAlineacion"] if c in matches.columns]
    wide = matches[base_cols].copy()
    market_order = ["Resultado 1X2", "Goles 1.er tiempo", "Corners 1.er tiempo", "Tarjetas amarillas totales"]
    for market in market_order:
        sub = markets[markets["Mercado"] == market][keys + ["Pronostico", "Probabilidad", "Semaforo"]].copy()
        slug = {"Resultado 1X2": "Resultado", "Goles 1.er tiempo": "Goles1T", "Corners 1.er tiempo": "Corners1T", "Tarjetas amarillas totales": "Tarjetas"}[market]
        sub = sub.rename(columns={"Pronostico": f"{slug}_Pronostico", "Probabilidad": f"{slug}_Prob", "Semaforo": f"{slug}_Semaforo"})
        wide = wide.merge(sub, on=keys, how="left")

    team_goals = markets[markets["Mercado"].astype(str).str.startswith("Goles ") & (markets["Mercado"] != "Goles 1.er tiempo")].copy()
    for _, match in matches.iterrows():
        mask = (wide["Fecha"] == match["Fecha"]) & (wide["HoraPeru"].astype(str) == str(match["HoraPeru"])) & (wide["Local"].astype(str) == str(match["Local"])) & (wide["Visitante"].astype(str) == str(match["Visitante"]))
        tm = team_goals[(team_goals["Fecha"] == match["Fecha"]) & (team_goals["HoraPeru"].astype(str) == str(match["HoraPeru"])) & (team_goals["Local"].astype(str) == str(match["Local"])) & (team_goals["Visitante"].astype(str) == str(match["Visitante"]))]
        for side, team in (("Local", match["Local"]), ("Visitante", match["Visitante"])):
            selected = tm[tm["Mercado"] == f"Goles {team}"]
            if not selected.empty:
                row = selected.iloc[0]
                wide.loc[mask, f"{side}Gol_Pronostico"] = row["Pronostico"]
                wide.loc[mask, f"{side}Gol_Prob"] = row["Probabilidad"]
                wide.loc[mask, f"{side}Gol_Semaforo"] = row["Semaforo"]
    return wide

def excel_bytes(matches, markets, metrics):
    out = BytesIO()
    summary = wide_forecasts(matches, markets)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="PRONOSTICOS", index=False)
        markets.to_excel(writer, sheet_name="MERCADOS_DETALLE", index=False)
        metrics.to_excel(writer, sheet_name="VALIDACION_TEMPORAL", index=False)
    out.seek(0)
    return out.getvalue()

st.markdown(
    f"""
    <div class="hero">
      <h1>🐾 Forecaster Fútbol V10 Gatuno</h1>
      <p>Decisiones ágiles, sin miedo al éxito. Evaluando probabilidades reales.</p>
      <span class="pill green">🟢 🤩 ALTA EVIDENCIA (>60%)</span>
      <span class="pill amber">🟡 🧐 PRECAUCIÓN (50-60%)</span>
      <span class="pill red">🔴 🙀 RIESGOSO (&lt;50%)</span>
    </div>
    """,
    unsafe_allow_html=True,
)

meta = load_meta()
try:
    if cache_current(meta):
        matches, markets, metrics = load_data()
    else:
        with st.status("🐾 Afilando garras y preparando análisis…", expanded=True):
            matches, markets, metrics, meta = run_and_save()
        st.toast("✅ ¡Cacería terminada! Pronósticos actualizados.", icon="🐾")
except Exception as exc:
    st.error("Error al ejecutar V10 Gatuno.")
    st.code(str(exc))
    st.stop()

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 Forzar recálculo completo", use_container_width=True):
        try:
            with st.status("🐾 Recalibrando instintos y motores…", expanded=True):
                matches, markets, metrics, meta = run_and_save()
            st.toast("✅ ¡Cacería terminada! Pronósticos actualizados.", icon="🐾")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
with c2:
    if not matches.empty:
        st.download_button(
            "📊 Descargar Datos (Excel)",
            data=excel_bytes(matches, markets, metrics),
            file_name="V10_GATUNO_TECNICO.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

if matches.empty:
    st.warning("No hay partidos futuros sin iniciar en la ventana actual.")
    st.stop()

f1, f2 = st.columns(2)
with f1:
    dates = sorted(pd.to_datetime(matches["Fecha"]).dt.date.unique())
    chosen_dates = st.multiselect("Filtrar por Fecha", dates, default=dates)
with f2:
    competitions = sorted(matches["Competicion"].dropna().astype(str).unique())
    chosen_competitions = st.multiselect("Filtrar por Competición", competitions, default=competitions)

visible_matches = matches[
    pd.to_datetime(matches["Fecha"]).dt.date.isin(chosen_dates)
    & matches["Competicion"].astype(str).isin(chosen_competitions)
]

for _, match in visible_matches.iterrows():
    date_value = pd.Timestamp(match["Fecha"]).strftime("%d/%m/%Y")
    subset = markets[
        (markets["Fecha"].dt.date == pd.Timestamp(match["Fecha"]).date())
        & (markets["HoraPeru"].astype(str) == str(match["HoraPeru"]))
        & (markets["Local"].astype(str) == str(match["Local"]))
        & (markets["Visitante"].astype(str) == str(match["Visitante"]))
    ]
    
    st.markdown(
        f"""
        <div class="match-card">
          <span class="pill blue">{match.get('Competicion','')}</span>
          <div class="match-title">{match.get('Local','')} vs {match.get('Visitante','')}</div>
          <div class="sub">{date_value} · {match.get('HoraPeru','')} PET</div>
        """,
        unsafe_allow_html=True,
    )
    for _, row in subset.iterrows():
        color_class = str(row.get("Semaforo", "ROJO")).lower()
        
        # Asignación de emojis según el sentimiento del color
        if color_class == "verde":
            emoji = "🟢 🤩"
        elif color_class == "amarillo":
            emoji = "🟡 🧐"
        else:
            emoji = "🔴 🙀"
            
        st.markdown(
            f"""
            <div class="market-row {color_class}">
              <div class="market-name">{row.get('Mercado','')} <small>({row.get('Linea','')})</small></div>
              <div class="pick">{row.get('Pronostico','')}</div>
              <div class="status-emoji">{emoji}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
