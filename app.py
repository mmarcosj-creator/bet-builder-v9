"""Interfaz Streamlit para FORECASTER FUTBOL V10 PRO."""

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


APP_VERSION = v10.VERSION
DATA_DIR = Path("app_data_v10")
DATA_DIR.mkdir(exist_ok=True)
MATCH_FILE = DATA_DIR / "latest_matches.csv"
MARKET_FILE = DATA_DIR / "latest_markets.csv"
METRIC_FILE = DATA_DIR / "latest_validation.csv"
META_FILE = DATA_DIR / "meta.json"
AUTO_REFRESH_HOURS = 12

st.set_page_config(
    page_title="Forecaster Fútbol V10 PRO",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {padding-top:.65rem; padding-bottom:3rem; max-width:1120px;}
      .hero {padding:1rem 1.05rem; border-radius:20px; border:1px solid rgba(128,128,128,.20);
             background:linear-gradient(135deg,rgba(37,99,235,.12),rgba(16,185,129,.10)); margin-bottom:.75rem;}
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
      .sub {opacity:.68; font-size:.84rem;}
      .kpis {display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.42rem; margin:.62rem 0;}
      .kpis div {border-radius:11px; padding:.50rem; background:rgba(128,128,128,.06);}
      .kpis b {display:block; font-size:.67rem; opacity:.64;}
      .kpis span {font-weight:900; font-size:.91rem;}
      .market-row {display:grid; grid-template-columns:1.45fr 1.05fr .62fr .78fr; gap:.42rem;
                   align-items:center; padding:.54rem .58rem; margin:.31rem 0; border-radius:11px;
                   background:rgba(128,128,128,.055); border-left:5px solid #6b7280;}
      .market-row.verde {border-left-color:#22c55e; background:rgba(34,197,94,.07);}
      .market-row.amarillo {border-left-color:#f59e0b; background:rgba(245,158,11,.07);}
      .market-row.rojo {border-left-color:#ef4444; background:rgba(239,68,68,.065);}
      .market-name {font-weight:780;}
      .pick {font-weight:900;}
      .prob {font-weight:900; text-align:right;}
      .risk {text-align:right; font-size:.75rem; font-weight:900;}
      .info-box {padding:.75rem .85rem; border-radius:14px; background:rgba(59,130,246,.08);
                 border:1px solid rgba(59,130,246,.18); margin:.65rem 0;}
      .stButton button,.stDownloadButton button {min-height:45px; border-radius:13px; font-weight:800;}
      @media(max-width:700px){
        .kpis {grid-template-columns:repeat(2,minmax(0,1fr));}
        .market-row {grid-template-columns:1.15fr .95fr .55fr;}
        .risk {grid-column:1/-1; text-align:left;}
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


def pct(value):
    value = safe_float(value)
    return "—" if pd.isna(value) else f"{value * 100:.1f}%"


def number(value, digits=2):
    value = safe_float(value)
    return "—" if pd.isna(value) else f"{value:.{digits}f}"


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
    market_order = [
        "Resultado 1X2",
        "Goles 1.er tiempo",
        "Corners 1.er tiempo",
        "Tarjetas amarillas totales",
    ]
    for market in market_order:
        sub = markets[markets["Mercado"] == market][keys + ["Pronostico", "Probabilidad", "Semaforo"]].copy()
        slug = {
            "Resultado 1X2": "Resultado",
            "Goles 1.er tiempo": "Goles1T",
            "Corners 1.er tiempo": "Corners1T",
            "Tarjetas amarillas totales": "Tarjetas",
        }[market]
        sub = sub.rename(columns={
            "Pronostico": f"{slug}_Pronostico",
            "Probabilidad": f"{slug}_Prob",
            "Semaforo": f"{slug}_Semaforo",
        })
        wide = wide.merge(sub, on=keys, how="left")

    team_goals = markets[markets["Mercado"].astype(str).str.startswith("Goles ") & (markets["Mercado"] != "Goles 1.er tiempo")].copy()
    for _, match in matches.iterrows():
        mask = (
            (wide["Fecha"] == match["Fecha"])
            & (wide["HoraPeru"].astype(str) == str(match["HoraPeru"]))
            & (wide["Local"].astype(str) == str(match["Local"]))
            & (wide["Visitante"].astype(str) == str(match["Visitante"]))
        )
        tm = team_goals[
            (team_goals["Fecha"] == match["Fecha"])
            & (team_goals["HoraPeru"].astype(str) == str(match["HoraPeru"]))
            & (team_goals["Local"].astype(str) == str(match["Local"]))
            & (team_goals["Visitante"].astype(str) == str(match["Visitante"]))
        ]
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
    methodology = pd.DataFrame([
        ["Producto", "Pronosticos individuales; no genera combinadas ni cuotas estimadas"],
        ["Resultado", "Clasificacion local/empate/visitante calibrada temporalmente"],
        ["Goles 1T", "Mas/menos de 1.5"],
        ["Corners 1T", "Mas/menos de 4.5 solo con conteos 1T reales; si falta cobertura, no modelable"],
        ["Tarjetas", "Tarjetas amarillas totales mas/menos de 4.5; comprobar reglas de la casa"],
        ["Goles equipo", "Cada equipo marca o no marca sobre linea 0.5"],
        ["Cruce argentino", "Interaccion separada en Libertadores/Sudamericana; solo ajusta corners 1T con 30+ antecedentes y validacion temporal"],
        ["VERDE", "Alta/buena evidencia: probabilidad, soporte, calibracion y contexto superan umbrales"],
        ["AMARILLO", "Evidencia media; no tratar como alta confianza"],
        ["ROJO", "Muy riesgosa, baja cobertura o mercado no modelable"],
        ["Cuotas", "No se estiman. Una cuota real solo se analiza con el mercado completo y sin margen"],
    ], columns=["Campo", "Descripcion"])

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="PRONOSTICOS", index=False)
        markets.to_excel(writer, sheet_name="MERCADOS_DETALLE", index=False)
        metrics.to_excel(writer, sheet_name="VALIDACION_TEMPORAL", index=False)
        methodology.to_excel(writer, sheet_name="METODO", index=False)

        from openpyxl.formatting.rule import FormulaRule
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = writer.book
        fills = {
            "VERDE": PatternFill("solid", fgColor="C6EFCE"),
            "AMARILLO": PatternFill("solid", fgColor="FFF2CC"),
            "ROJO": PatternFill("solid", fgColor="F4CCCC"),
        }
        for ws in wb.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.fill = PatternFill("solid", fgColor="17365D")
                cell.font = Font(color="FFFFFF", bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            for column in range(1, ws.max_column + 1):
                values = [str(ws.cell(row, column).value or "") for row in range(1, min(ws.max_row, 80) + 1)]
                ws.column_dimensions[get_column_letter(column)].width = min(48, max(10, max(map(len, values), default=10) + 2))
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=False)

        detail = wb["MERCADOS_DETALLE"]
        headers = {cell.value: cell.column for cell in detail[1]}
        for name in ("Probabilidad", "ProbAlternativa", "PConservadora", "Fiabilidad"):
            if name in headers:
                for row in range(2, detail.max_row + 1):
                    detail.cell(row, headers[name]).number_format = "0.0%"
        if "Semaforo" in headers:
            col = get_column_letter(headers["Semaforo"])
            target = f"A2:{get_column_letter(detail.max_column)}{detail.max_row}"
            for status, fill in fills.items():
                detail.conditional_formatting.add(target, FormulaRule(formula=[f'${col}2="{status}"'], fill=fill))

        summary_ws = wb["PRONOSTICOS"]
        summary_headers = {cell.value: cell.column for cell in summary_ws[1]}
        for name, column in summary_headers.items():
            if str(name).endswith("_Prob"):
                for row in range(2, summary_ws.max_row + 1):
                    summary_ws.cell(row, column).number_format = "0.0%"
            if str(name).endswith("_Semaforo"):
                letter = get_column_letter(column)
                target = f"A2:{get_column_letter(summary_ws.max_column)}{summary_ws.max_row}"
                for status, fill in fills.items():
                    summary_ws.conditional_formatting.add(target, FormulaRule(formula=[f'${letter}2="{status}"'], fill=fill))
    out.seek(0)
    return out.getvalue()


st.markdown(
    f"""
    <div class="hero">
      <h1>⚽ Forecaster Fútbol V10 PRO</h1>
      <p>Pronósticos individuales por partido, calibración temporal y abstención cuando faltan datos.</p>
      <span class="pill blue">SIN CUOTAS INVENTADAS</span>
      <span class="pill green">VERDE = BUENA EVIDENCIA</span>
      <span class="pill red">ROJO = MUY RIESGOSA</span>
      <span class="pill amber">NO ASIÁTICOS</span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="info-box"><b>Cambio clave:</b> V10 muestra todos los encuentros y agrupa seis mercados por partido.
    Ya no decide quién es “favorito” con una regla aproximada, no fabrica una cuota y no convierte los pronósticos
    en una combinada. Las tarjetas son <b>amarillas</b>; comprueba que la regla de la casa sea equivalente.
    Los cruces de clubes argentinos con otras ligas CONMEBOL se modelan por separado y no reciben una penalización fija.</div>
    """,
    unsafe_allow_html=True,
)

meta = load_meta()
try:
    if cache_current(meta):
        matches, markets, metrics = load_data()
    else:
        with st.status("Actualizando datos y validando modelos…", expanded=True):
            st.write("Descargando histórico y calendario…")
            st.write("Construyendo posiciones y forma sin usar resultados futuros…")
            st.write("Calibrando cada mercado con cortes temporales…")
            matches, markets, metrics, meta = run_and_save()
except Exception as exc:
    st.error("No fue posible ejecutar V10.")
    st.code(str(exc))
    with st.expander("Detalle técnico"):
        st.code(traceback.format_exc())
    st.stop()

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 Actualizar pronósticos", use_container_width=True):
        try:
            with st.status("Actualizando V10…", expanded=True):
                matches, markets, metrics, meta = run_and_save()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
with c2:
    if not matches.empty:
        st.download_button(
            "📊 Descargar Excel V10",
            data=excel_bytes(matches, markets, metrics),
            file_name="PRONOSTICOS_FUTBOL_V10.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

generated = meta.get("generated_at", "")
if generated:
    try:
        generated = datetime.fromisoformat(generated).strftime("%d/%m/%Y %H:%M PET")
    except Exception:
        pass
st.caption(
    f"Actualizado: {generated or '—'} · Ventana: {meta.get('window_start','—')} → {meta.get('window_end','—')} · {APP_VERSION}"
)

if matches.empty:
    st.warning("No hay partidos futuros sin iniciar en la ventana actual.")
    st.stop()

f1, f2 = st.columns(2)
with f1:
    dates = sorted(pd.to_datetime(matches["Fecha"]).dt.date.unique())
    chosen_dates = st.multiselect("Fecha", dates, default=dates)
with f2:
    competitions = sorted(matches["Competicion"].dropna().astype(str).unique())
    chosen_competitions = st.multiselect("Competición", competitions, default=competitions)

visible_matches = matches[
    pd.to_datetime(matches["Fecha"]).dt.date.isin(chosen_dates)
    & matches["Competicion"].astype(str).isin(chosen_competitions)
]

green_count = int((markets["Semaforo"] == "VERDE").sum()) if "Semaforo" in markets else 0
red_count = int((markets["Semaforo"] == "ROJO").sum()) if "Semaforo" in markets else 0
m1, m2, m3 = st.columns(3)
m1.metric("Partidos", len(visible_matches))
m2.metric("Mercados verdes", green_count)
m3.metric("Mercados rojos/no modelables", red_count)

for _, match in visible_matches.iterrows():
    date_value = pd.Timestamp(match["Fecha"]).strftime("%d/%m/%Y")
    subset = markets[
        (markets["Fecha"].dt.date == pd.Timestamp(match["Fecha"]).date())
        & (markets["HoraPeru"].astype(str) == str(match["HoraPeru"]))
        & (markets["Local"].astype(str) == str(match["Local"]))
        & (markets["Visitante"].astype(str) == str(match["Visitante"]))
    ]
    arg_value = match.get("CruceArgentinoInterliga", False)
    arg_cross = str(arg_value).strip().lower() in {"true", "1", "si", "sí"}
    arg_badge = (
        '<span class="pill amber">Cruce argentino interliga</span>'
        if arg_cross
        else ""
    )
    st.markdown(
        f"""
        <div class="match-card">
          <span class="pill blue">{match.get('Competicion','')}</span>
          <span class="pill gray">Rotación: {match.get('RiesgoRotacion','—')}</span>
          {arg_badge}
          <div class="match-title">{match.get('Local','')} vs {match.get('Visitante','')}</div>
          <div class="sub">{date_value} · {match.get('HoraPeru','')} PET · Alineación: {match.get('EstadoAlineacion','—')}</div>
          <div class="kpis">
            <div><b>GOLES ESP. LOCAL</b><span>{number(match.get('GolesEsperadosLocal'))}</span></div>
            <div><b>GOLES ESP. VISITA</b><span>{number(match.get('GolesEsperadosVisitante'))}</span></div>
            <div><b>GOLES ESP. 1T</b><span>{number(match.get('GolesEsperados1T'))}</span></div>
            <div><b>TARJETAS ESP.</b><span>{number(match.get('TarjetasEsperadas'))}</span></div>
          </div>
        """,
        unsafe_allow_html=True,
    )
    for _, row in subset.iterrows():
        color = str(row.get("Semaforo", "ROJO")).lower()
        st.markdown(
            f"""
            <div class="market-row {color}">
              <div class="market-name">{row.get('Mercado','')} <small>({row.get('Linea','')})</small></div>
              <div class="pick">{row.get('Pronostico','')}</div>
              <div class="prob">{pct(row.get('Probabilidad'))}</div>
              <div class="risk">{row.get('Semaforo','')} · {row.get('Nivel','')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    note = str(match.get("NotaContexto", "") or "")
    if note:
        st.caption("Contexto: " + note)
    st.markdown("</div>", unsafe_allow_html=True)

with st.expander("📐 Validación temporal y fiabilidad"):
    st.caption(
        "Las métricas se calculan sobre el tramo más reciente reservado y nunca usado para entrenar ese corte. "
        "Un color verde exige además soporte local, calibración y contexto; no basta con que P sea alta."
    )
    columns = [c for c in ["Modelo", "EstadoValidacion", "SuperaBase", "N_Validacion", "Brier", "BrierBase", "MejoraBrier", "LogLoss", "Exactitud", "ExactitudBase", "ECE", "MAE", "MAEBase", "MejoraMAE", "CalidadModelo"] if c in metrics.columns]
    st.dataframe(metrics[columns], use_container_width=True, hide_index=True)

with st.expander("ℹ️ Cómo leer V10"):
    st.markdown(
        """
        - **VERDE:** buena evidencia estadística; no significa certeza ni rentabilidad automática.
        - **AMARILLO:** señal intermedia; requiere prudencia y revisión de alineación.
        - **ROJO:** muy riesgosa, insuficiente o no modelable. V10 no fuerza una selección.
        - Los seis pronósticos aparecen juntos para analizar el partido, **no para apostar una combinada**.
        - No hay hándicap asiático ni cuota estimada. Si luego se analiza valor, debe usarse la cuota real completa de la casa y retirarse su margen.
        """
    )

st.caption("Herramienta experimental de análisis. No garantiza aciertos ni ganancias; apuesta solo dinero que puedas perder.")
