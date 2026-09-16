"""Interfaz Streamlit para FORECASTER FUTBOL V10.3 PRO.

V10.3 = V10.1 (motor estadistico completo, sin recortes) + un modulo de
auditoria real (auditoria_v10.py) que registra cada pronostico antes del
kickoff, lo congela, lo resuelve automaticamente contra el resultado oficial
y muestra metricas honestas.

Deliberadamente NO incluye:
  - Un semaforo recalculado en la interfaz con un corte simple (>=60%).
    El semaforo que se muestra es el que ya calculo bet_forecaster_v10 con
    calibracion, Wilson LCB, fiabilidad y soporte. Recalcularlo aqui con un
    if/else destruiria exactamente el rigor que se audito en V10.1.
  - Una "alarma de sistema validado y estable". Una racha de una semana no
    valida estadisticamente un modelo de futbol; fingir lo contrario induce
    a apostar mas justo cuando el sistema tuvo suerte, no habilidad.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import traceback

import numpy as np
import pandas as pd
import streamlit as st

import auditoria_v10 as audit
import bet_builder_v8_1_robust as base
import bet_forecaster_v10 as v10
import model_monitor as monitor


APP_VERSION = "V10.4-TRAZABLE"
DATA_DIR = Path("app_data_v10")
DATA_DIR.mkdir(exist_ok=True)
MATCH_FILE = DATA_DIR / "latest_matches.csv"
MARKET_FILE = DATA_DIR / "latest_markets.csv"
METRIC_FILE = DATA_DIR / "latest_validation.csv"
HISTORY_FILE = DATA_DIR / "historial_apuestas.csv"
PUNTOS_MEDIOS_FILE = DATA_DIR / "historial_puntos_medios.csv"
METRICS_LOG_FILE = DATA_DIR / "model_metrics_log.csv"
META_FILE = DATA_DIR / "meta.json"
AUTO_REFRESH_HOURS = 12

st.set_page_config(
    page_title="Forecaster Futbol V10.4",
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
      .audit-box {padding:.75rem .85rem; border-radius:14px; background:rgba(107,114,128,.08);
                  border:1px solid rgba(107,114,128,.20); margin:.65rem 0; font-size:.86rem;}
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
    return "\u2014" if pd.isna(value) else f"{value * 100:.1f}%"


def number(value, digits=2):
    value = safe_float(value)
    return "\u2014" if pd.isna(value) else f"{value:.{digits}f}"


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


def actualizar_auditoria(matches_df: pd.DataFrame, markets_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Registra los pronosticos nuevos y resuelve los pendientes vencidos,
    tanto para el historial de mercados (VERDE/AMARILLO/ROJO) como para los
    puntos medios (goles/tarjetas esperados vs. reales).

    Cualquier fallo aqui (red, fuente sin datos, etc.) no debe tumbar la
    pantalla principal: el pronostico del dia ya se genero y es lo mas
    importante. Por eso todo el bloque va envuelto en try/except, igual que
    el resto de fuentes opcionales del sistema (context93, h1_context).
    """
    historial = audit.registrar_pronosticos(markets_df, HISTORY_FILE)
    puntos_medios = audit.registrar_puntos_medios(matches_df, PUNTOS_MEDIOS_FILE)
    try:
        history_df = base.descargar_historico_total()
    except Exception:
        history_df = pd.DataFrame()
    try:
        h1_context_df = base.descargar_contexto_h1()
    except Exception:
        h1_context_df = pd.DataFrame()
    historial = audit.resolver_pendientes(historial, history_df, h1_context_df)
    puntos_medios = audit.resolver_puntos_medios(puntos_medios, history_df)
    audit.guardar_historial(historial, HISTORY_FILE)
    audit.guardar_puntos_medios(puntos_medios, PUNTOS_MEDIOS_FILE)
    metricas = audit.calcular_metricas(historial)
    return historial, metricas


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
    try:
        actualizar_auditoria(matches, markets)
    except Exception:
        pass  # el panel de auditoria es un extra; nunca debe tumbar la app
    try:
        monitor.registrar_metricas(metrics, METRICS_LOG_FILE)
    except Exception:
        pass  # el monitor de calidad tampoco debe tumbar la app
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
    historial = audit.cargar_historial(HISTORY_FILE)
    metricas_auditoria = audit.calcular_metricas(historial)
    puntos_medios = audit.cargar_puntos_medios(PUNTOS_MEDIOS_FILE)
    metricas_pm = audit.calcular_metricas_puntos_medios(puntos_medios)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="PRONOSTICOS", index=False)
        markets.to_excel(writer, sheet_name="MERCADOS_DETALLE", index=False)
        metrics.to_excel(writer, sheet_name="VALIDACION_TEMPORAL", index=False)
        if not historial.empty:
            historial.to_excel(writer, sheet_name="HISTORIAL_AUDITORIA", index=False)
            metricas_auditoria.to_excel(writer, sheet_name="METRICAS_AUDITORIA", index=False)
        if not puntos_medios.empty:
            puntos_medios.to_excel(writer, sheet_name="PUNTOS_MEDIOS", index=False)
            metricas_pm.to_excel(writer, sheet_name="METRICAS_PUNTOS_MEDIOS", index=False)

    from openpyxl.styles import PatternFill
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.utils import get_column_letter

    out.seek(0)
    wb_bytes = out.getvalue()
    out2 = BytesIO(wb_bytes)
    try:
        import openpyxl
        wb = openpyxl.load_workbook(out2)
        fills = {
            "VERDE": PatternFill("solid", fgColor="C6EFCE"),
            "AMARILLO": PatternFill("solid", fgColor="FFEB9C"),
            "ROJO": PatternFill("solid", fgColor="FFC7CE"),
        }
        for sheet_name in ("MERCADOS_DETALLE", "PRONOSTICOS", "HISTORIAL_AUDITORIA"):
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            headers = {cell.value: cell.column for cell in ws[1]}
            for name, column in headers.items():
                if str(name).endswith(("_Prob", "Probabilidad")):
                    for row in range(2, ws.max_row + 1):
                        ws.cell(row, column).number_format = "0.0%"
                if str(name).endswith("Semaforo"):
                    letter = get_column_letter(column)
                    target = f"A2:{get_column_letter(ws.max_column)}{ws.max_row}"
                    for status, fill in fills.items():
                        ws.conditional_formatting.add(target, FormulaRule(formula=[f'${letter}2="{status}"'], fill=fill))
        final = BytesIO()
        wb.save(final)
        return final.getvalue()
    except Exception:
        return wb_bytes


st.markdown(
    f"""
    <div class="hero">
      <h1>⚽ Forecaster Futbol V10.4</h1>
      <p>Pronosticos individuales por partido, calibracion temporal, abstencion cuando faltan datos
      y auditoria real de resultados.</p>
      <span class="pill blue">SIN CUOTAS INVENTADAS</span>
      <span class="pill green">VERDE = BUENA EVIDENCIA</span>
      <span class="pill red">ROJO = MUY RIESGOSA</span>
      <span class="pill amber">NO ASIATICOS</span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="info-box"><b>Cambio clave:</b> V10.3 mantiene el motor de V10.1 sin recortes
    (calibracion, Wilson LCB, fiabilidad, soporte, abstencion) y agrega una auditoria real:
    cada pronostico se guarda antes del partido, se congela al empezar, y se coteja
    automaticamente contra el resultado oficial. No hay ningun aviso de "sistema validado":
    una racha corta no demuestra nada estadisticamente.</div>
    """,
    unsafe_allow_html=True,
)

meta = load_meta()
try:
    if cache_current(meta):
        matches, markets, metrics = load_data()
    else:
        with st.status("Actualizando datos, calibrando modelos y auditando resultados...", expanded=True):
            st.write("Descargando historico y calendario...")
            st.write("Construyendo posiciones y forma sin usar resultados futuros...")
            st.write("Calibrando cada mercado con cortes temporales...")
            st.write("Registrando pronosticos y resolviendo pendientes vencidos...")
            matches, markets, metrics, meta = run_and_save()
except Exception as exc:
    st.error("No fue posible ejecutar V10.3.")
    st.code(str(exc))
    with st.expander("Detalle tecnico"):
        st.code(traceback.format_exc())
    st.stop()

c1, c2 = st.columns(2)
with c1:
    if st.button("🔄 Actualizar pronosticos y auditoria", use_container_width=True):
        try:
            with st.status("Actualizando V10.3...", expanded=True):
                matches, markets, metrics, meta = run_and_save()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
with c2:
    if not matches.empty:
        st.download_button(
            "📊 Descargar Excel V10.3",
            data=excel_bytes(matches, markets, metrics),
            file_name="PRONOSTICOS_FUTBOL_V10_3.xlsx",
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
    f"Actualizado: {generated or '\u2014'} \u00b7 Ventana: {meta.get('window_start','\u2014')} \u2192 {meta.get('window_end','\u2014')} \u00b7 {APP_VERSION}"
)

try:
    metrics_log = pd.read_csv(METRICS_LOG_FILE) if METRICS_LOG_FILE.exists() else pd.DataFrame()
    avisos = monitor.detectar_degradacion(metrics_log) if not metrics_log.empty else []
except Exception:
    avisos = []
if avisos:
    st.warning(
        "⚠️ Posible degradacion de modelo detectada frente a corridas anteriores. "
        "Tratar las senales de hoy con mas cautela hasta revisar:\n\n"
        + "\n".join(f"- **{a['Modelo']}** ({a['Severidad']}): {a['Motivo']}" for a in avisos)
    )

# ---------------------------------------------------------------------------
# Panel de auditoria: metricas reales, sin badges de "sistema validado".
# ---------------------------------------------------------------------------
with st.expander("📋 Auditoria real de pronosticos (aciertos/fallos por color y mercado)", expanded=False):
    historial = audit.cargar_historial(HISTORY_FILE)
    if historial.empty:
        st.info("Todavia no hay pronosticos registrados para auditar.")
    else:
        metricas = audit.calcular_metricas(historial)
        st.caption(
            "Cada fila se registro antes del kickoff y se congelo al empezar el partido. "
            "'SIN DATOS' significa evaluados = 0: nunca se muestra 0.0% en ese caso. "
            "Con menos de 30 casos evaluados, la tasa se marca como no concluyente: "
            "la varianza en muestras chicas es demasiado alta para sacar conclusiones."
        )
        tabla = metricas.copy()
        tabla["TasaAcierto"] = tabla.apply(lambda r: audit.formatear_tasa(r["TasaAcierto"], r["N_Evaluado"]), axis=1)
        tabla["IC95"] = metricas.apply(
            lambda r: "\u2014" if pd.isna(r["IC95_Bajo"]) else f"[{r['IC95_Bajo']*100:.0f}%, {r['IC95_Alto']*100:.0f}%]",
            axis=1,
        )
        st.dataframe(
            tabla[["Mercado", "Semaforo", "N_Registrado", "N_Pendiente", "N_SinDato", "N_Evaluado", "TasaAcierto", "IC95", "Brier"]],
            use_container_width=True,
            hide_index=True,
        )
        total_evaluado = int((historial["EstadoResultado"].isin(["ACERTADO", "FALLADO"])).sum())
        total_verde_evaluado = int(
            historial[(historial["Semaforo"] == "VERDE") & historial["EstadoResultado"].isin(["ACERTADO", "FALLADO"])].shape[0]
        )
        st.markdown(
            f"""
            <div class="audit-box">
              <b>Lectura honesta:</b> {total_evaluado} pronosticos evaluados en total
              ({total_verde_evaluado} de ellos en VERDE). Esta tabla mide calibracion pasada,
              no promete resultados futuros. Un mercado necesita muchas decenas de casos evaluados,
              idealmente cientos, antes de que su tasa de acierto sea informativa.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("**¿La calibracion prometida coincide con la realidad?**")
        st.caption(
            "VERDE promete probabilidad minima 68%; AMARILLO, 59% (CRITERIOS_V10.md, seccion 6). "
            "Esto solo compara; nunca ajusta umbrales automaticamente."
        )
        brecha = monitor.comparar_calibracion_real(metricas)
        if brecha.empty:
            st.caption("Sin filas VERDE/AMARILLO evaluadas todavia para comparar.")
        else:
            brecha_fmt = brecha.copy()
            for col in ("PromesaMinima", "TasaReal", "Brecha"):
                brecha_fmt[col] = brecha_fmt[col].apply(lambda v: "\u2014" if pd.isna(v) else f"{v*100:.1f}%")
            st.dataframe(brecha_fmt, use_container_width=True, hide_index=True)

    st.markdown("**Puntos medios: error real de goles y tarjetas esperados**")
    st.caption(
        "Esto no es un acierto/fallo binario: compara el numero que el modelo predijo "
        "(p. ej. \"4.8 tarjetas esperadas\") contra el numero real del partido, y promedia "
        "el error absoluto (MAE). Un MAE mas bajo es mejor; no existe un umbral universal "
        "de \"bueno\", depende del mercado."
    )
    puntos_medios = audit.cargar_puntos_medios(PUNTOS_MEDIOS_FILE)
    if puntos_medios.empty:
        st.info("Todavia no hay partidos registrados para auditar puntos medios.")
    else:
        metricas_pm = audit.calcular_metricas_puntos_medios(puntos_medios)
        tabla_pm = metricas_pm.copy()
        tabla_pm["MAE"] = tabla_pm["MAE"].apply(lambda v: "SIN DATOS" if pd.isna(v) else f"{v:.2f}")
        st.dataframe(tabla_pm, use_container_width=True, hide_index=True)

if matches.empty:
    st.warning("No hay partidos futuros sin iniciar en la ventana actual.")
    st.stop()

f1, f2 = st.columns(2)
with f1:
    dates = sorted(pd.to_datetime(matches["Fecha"]).dt.date.unique())
    chosen_dates = st.multiselect("Fecha", dates, default=dates)
with f2:
    competitions = sorted(matches["Competicion"].dropna().astype(str).unique())
    chosen_competitions = st.multiselect("Competicion", competitions, default=competitions)

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
    arg_cross = str(arg_value).strip().lower() in {"true", "1", "si", "s\u00ed"}
    arg_badge = (
        '<span class="pill amber">Cruce argentino interliga</span>'
        if arg_cross
        else ""
    )
    st.markdown(
        f"""
        <div class="match-card">
          <span class="pill blue">{match.get('Competicion','')}</span>
          <span class="pill gray">Rotacion: {match.get('RiesgoRotacion','\u2014')}</span>
          {arg_badge}
          <div class="match-title">{match.get('Local','')} vs {match.get('Visitante','')}</div>
          <div class="sub">{date_value} \u00b7 {match.get('HoraPeru','')} PET \u00b7 Alineacion: {match.get('EstadoAlineacion','\u2014')}</div>
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
              <div class="risk">{row.get('Semaforo','')} \u00b7 {row.get('Nivel','')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    note = str(match.get("NotaContexto", "") or "")
    if note:
        st.caption("Contexto: " + note)
    st.markdown("</div>", unsafe_allow_html=True)

with st.expander("📐 Validacion temporal y fiabilidad"):
    st.caption(
        "Las metricas se calculan sobre el tramo mas reciente reservado y nunca usado para entrenar ese corte. "
        "Un color verde exige ademas soporte local, calibracion y contexto; no basta con que P sea alta."
    )
    columns = [c for c in ["Modelo", "EstadoValidacion", "SuperaBase", "N_Validacion", "Brier", "BrierBase", "MejoraBrier", "LogLoss", "Exactitud", "ExactitudBase", "ECE", "MAE", "MAEBase", "MejoraMAE", "CalidadModelo"] if c in metrics.columns]
    st.dataframe(metrics[columns], use_container_width=True, hide_index=True)

with st.expander("ℹ️ Como leer V10.3"):
    st.markdown(
        """
        - **VERDE:** buena evidencia estadistica; no significa certeza ni rentabilidad automatica.
        - **AMARILLO:** senal intermedia; requiere prudencia y revision de alineacion.
        - **ROJO:** muy riesgosa, insuficiente o no modelable. V10.3 no fuerza una seleccion.
        - Los seis pronosticos aparecen juntos para analizar el partido, **no para apostar una combinada**.
        - No hay handicap asiatico ni cuota estimada. Si luego se analiza valor, debe usarse la cuota real completa de la casa y retirarse su margen.
        - El panel de auditoria mide como se comporto el modelo en el pasado; no es una promesa sobre el proximo partido.
        """
    )

st.caption("Herramienta experimental de analisis. No garantiza aciertos ni ganancias; apuesta solo dinero que puedas perder.")
