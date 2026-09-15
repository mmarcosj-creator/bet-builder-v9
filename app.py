
# ============================================================
# BET BUILDER V9.3.1 CONTEXT PRO - STREAMLIT MOBILE
# ============================================================

from io import BytesIO
from pathlib import Path
from datetime import datetime
import json
import traceback

import numpy as np
import pandas as pd
import streamlit as st

import bet_builder_v9_3_context_optimizer as v9
import bet_builder_v8_1_robust as base


APP_VERSION = "V9.3.1 CONTEXT REALTIME GUARD"
DATA_DIR = Path("app_data_v9_3")
DATA_DIR.mkdir(exist_ok=True)

DATA_FILE = DATA_DIR / "latest_v9_3.csv"
META_FILE = DATA_DIR / "meta_v9_3.json"
QUOTE_FILE = DATA_DIR / "cotizaciones_reales.csv"

AUTO_REFRESH_HOURS = 12

st.set_page_config(
    page_title="Bet Builder V9.3.1 CONTEXT PRO",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {
        padding-top: .7rem;
        padding-bottom: 3rem;
        max-width: 1080px;
      }

      .hero {
        padding: 1rem 1.05rem;
        border-radius: 20px;
        border: 1px solid rgba(128,128,128,.18);
        background: linear-gradient(135deg, rgba(16,185,129,.13), rgba(59,130,246,.10));
        margin-bottom: .7rem;
      }

      .hero h1 {
        margin: 0;
        font-size: clamp(1.55rem, 6vw, 2.25rem);
      }

      .hero p {
        margin: .4rem 0 0 0;
        opacity: .80;
      }

      .pill {
        display: inline-block;
        padding: .26rem .60rem;
        border-radius: 999px;
        font-weight: 800;
        font-size: .77rem;
        margin-right: .3rem;
        margin-top: .35rem;
      }

      .green { background: rgba(34,197,94,.17); color:#16a34a; }
      .amber { background: rgba(245,158,11,.18); color:#d97706; }
      .blue  { background: rgba(59,130,246,.16); color:#2563eb; }
      .red   { background: rgba(239,68,68,.15); color:#dc2626; }
      .gray  { background: rgba(107,114,128,.15); color:#6b7280; }

      .match-card {
        border: 1px solid rgba(128,128,128,.20);
        border-radius: 18px;
        padding: .95rem 1rem;
        margin: .8rem 0;
        background: rgba(128,128,128,.035);
      }

      .match-title {
        font-weight: 900;
        font-size: 1.12rem;
        margin: .35rem 0 .2rem 0;
      }

      .sub {
        opacity: .68;
        font-size: .84rem;
      }

      .leg {
        padding: .42rem .55rem;
        margin: .30rem 0;
        border-radius: 10px;
        background: rgba(128,128,128,.06);
        font-weight: 750;
      }

      .numbers {
        display:grid;
        grid-template-columns: repeat(3,minmax(0,1fr));
        gap:.42rem;
        margin-top:.65rem;
      }

      .numbers > div {
        border-radius:12px;
        padding:.5rem;
        background:rgba(128,128,128,.06);
      }

      .numbers b {
        display:block;
        font-size:.70rem;
        opacity:.63;
      }

      .numbers span {
        font-weight:900;
        font-size:.96rem;
      }

      .info-box {
        padding:.75rem .85rem;
        border-radius:14px;
        background:rgba(59,130,246,.09);
        border:1px solid rgba(59,130,246,.18);
        margin-bottom:.7rem;
      }

      .stButton button, .stDownloadButton button {
        min-height:46px;
        border-radius:13px;
        font-weight:800;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def safe_float(v, default=np.nan):
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def pct(v):
    x = safe_float(v)
    return "—" if pd.isna(x) else f"{x*100:.1f}%"


def num(v, d=2):
    x = safe_float(v)
    return "—" if pd.isna(x) else f"{x:.{d}f}"


def save_real_quote(row, bookmaker, actual_quote, validation):
    record = {
        "RegistradoEn": datetime.now(base.TZ_PERU).isoformat(),
        "Casa": bookmaker,
        "FechaPartido": str(pd.Timestamp(row["Fecha"]).date()),
        "Competicion": row["Competicion"],
        "Local": row["Local"],
        "Visitante": row["Visitante"],
        "Variante": row["Variante"],
        "Patas": row["Patas"],
        "CodigosPatas": row.get("CodigosPatas", ""),
        "FirmaCombinacion": row.get("FirmaCombinacion", ""),
        "P_Modelo": safe_float(row["P_Conjunta"]),
        "P_LCB": safe_float(row["P_LCB"]),
        "CuotaRequerida": safe_float(row["CuotaRequerida"]),
        "CuotaReal": float(actual_quote),
        "EV_Modelo": safe_float(validation.get("ev")),
        "EV_LCB": safe_float(validation.get("ev_lcb")),
        "Estado": validation.get("status", ""),
        "Version": APP_VERSION,
    }

    new = pd.DataFrame([record])
    if QUOTE_FILE.exists():
        old = pd.read_csv(QUOTE_FILE)
        new = pd.concat([old, new], ignore_index=True)

    new.to_csv(QUOTE_FILE, index=False, encoding="utf-8-sig")


def load_meta():
    if not META_FILE.exists():
        return {}
    try:
        return json.loads(META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def cache_current(meta):
    if not meta or not DATA_FILE.exists():
        return False

    try:
        now = datetime.now(base.TZ_PERU)
        end = pd.Timestamp(meta["window_end"]).date()
        generated = datetime.fromisoformat(meta["generated_at"])

        if generated.tzinfo is None:
            return False

        age = (now - generated).total_seconds() / 3600.0

        return now.date() <= end and age <= AUTO_REFRESH_HOURS
    except Exception:
        return False


def load_data():
    df = pd.read_csv(DATA_FILE)
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    return filtrar_salida_desde_ahora(df)


def filtrar_salida_desde_ahora(df):
    """También limpia la caché: nunca muestra un partido ya iniciado."""
    if df is None or df.empty:
        return df
    now = datetime.now(base.TZ_PERU)

    if "KickoffUTC" in df.columns:
        kickoff = pd.to_datetime(df["KickoffUTC"], utc=True, errors="coerce")
        now_utc = pd.Timestamp(now).tz_convert("UTC")
        known = kickoff.notna()
        keep = (~known) | (kickoff > now_utc)
    else:
        hours = (
            df["HoraPeru"].astype(str)
            if "HoraPeru" in df.columns
            else pd.Series("", index=df.index)
        )
        local_text = (
            pd.to_datetime(df["Fecha"], errors="coerce").dt.strftime("%Y-%m-%d")
            + " "
            + hours
        )
        kickoff_local = pd.to_datetime(local_text, errors="coerce")
        now_local = pd.Timestamp(now.replace(tzinfo=None))
        known = kickoff_local.notna()
        keep = (~known) | (kickoff_local > now_local)

    return df.loc[keep].reset_index(drop=True)


def run_and_save():
    df, start, end = v9.run_v9()
    df = filtrar_salida_desde_ahora(df)

    df.to_csv(
        DATA_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    meta = {
        "generated_at": datetime.now(base.TZ_PERU).isoformat(),
        "window_start": str(pd.Timestamp(start).date()),
        "window_end": str(pd.Timestamp(end).date()),
        "rows": int(len(df)),
        "version": APP_VERSION,
    }

    META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return df, meta


def excel_bytes(df):
    out = BytesIO()

    display_cols = [
        "RankingPartido",
        "Fecha",
        "HoraPeru",
        "Competicion",
        "Local",
        "Visitante",
        "VarianteRank",
        "Variante",
        "Patas",
        "CodigosPatas",
        "FirmaCombinacion",
        "P_Conjunta",
        "P_LCB",
        "CuotaJustaModelo",
        "CuotaMinROI29",
        "CuotaRequerida",
        "CuotaReal",
        "ZonaPrecio",
        "RiesgoCombinado",
        "Fiabilidad",
        "Soporte",
        "SoporteEfectivo",
        "Dependencia",
        "PhiMaxAbs",
        "LiftConjunto",
        "TasaReciente",
        "TasaAnterior",
        "BrechaRegimen",
        "RegimenEstable",
        "FaseCompetitiva",
        "ImportanciaPartido",
        "RiesgoRotacion",
        "EstadoAlineacion",
        "EstadoOnceLocal",
        "EstadoOnceVisitante",
        "BaselineOnceLocal",
        "BaselineOnceVisitante",
        "ContinuidadOnceLocal",
        "ContinuidadOnceVisitante",
        "FactorContexto",
        "CupoCartera",
        "EstadoPreCuota",
    ]

    cols = [c for c in display_cols if c in df.columns]

    simple = df[cols].copy()

    simple["ESTADO_REAL"] = "PENDIENTE"
    simple["EV_REAL"] = ""

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        simple.to_excel(
            writer,
            sheet_name="COTIZAR_4_20",
            index=False,
            startrow=4,
        )

        df.to_excel(
            writer,
            sheet_name="TECNICO_V9_3",
            index=False,
        )

        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        wb = writer.book
        ws = wb["COTIZAR_4_20"]

        max_col = len(simple.columns)

        ws.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=max_col,
        )
        ws["A1"] = "BET BUILDER V9.3.1 CONTEXT PRO — COTIZAR Y VALIDAR CUOTA REAL"
        ws["A1"].font = Font(bold=True, color="FFFFFF", size=17)
        ws["A1"].fill = PatternFill("solid", fgColor="102A43")
        ws["A1"].alignment = Alignment(horizontal="center")

        ws.merge_cells(
            start_row=2,
            start_column=1,
            end_row=2,
            end_column=max_col,
        )
        ws["A2"] = (
            "Ninguna fila es APOSTAR hasta ingresar la CUOTA REAL. "
            "Regla dura: cuota real >= 4.20 y >= CuotaRequerida."
        )
        ws["A2"].fill = PatternFill("solid", fgColor="D9EAF7")
        ws["A2"].font = Font(bold=True)
        ws["A2"].alignment = Alignment(wrap_text=True)

        header_row = 5

        headers = {
            c.value: c.column
            for c in ws[header_row]
        }

        for c in ws[header_row]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")
            c.alignment = Alignment(horizontal="center", wrap_text=True)

        ws.freeze_panes = "A6"

        if "CuotaReal" in headers and "CuotaRequerida" in headers:
            cr = get_column_letter(headers["CuotaReal"])
            cq = get_column_letter(headers["CuotaRequerida"])

            for rr in range(6, ws.max_row + 1):
                ws.cell(rr, headers["CuotaReal"]).fill = PatternFill(
                    "solid", fgColor="FFF2CC"
                )

                if "ESTADO_REAL" in headers:
                    ce = headers["ESTADO_REAL"]
                    ws.cell(rr, ce).value = (
                        f'=IF({cr}{rr}="","PENDIENTE",'
                        f'IF({cr}{rr}<4.2,"DESCARTAR <4.20",'
                        f'IF({cr}{rr}<{cq}{rr},"NO ALCANZA ROI","VALIDA")))'
                    )

                if "EV_REAL" in headers and "P_Conjunta" in headers:
                    cp = get_column_letter(headers["P_Conjunta"])
                    ws.cell(rr, headers["EV_REAL"]).value = (
                        f'=IF({cr}{rr}="","",{cp}{rr}*{cr}{rr}-1)'
                    )
                    ws.cell(rr, headers["EV_REAL"]).number_format = "0.0%"

                if "P_Conjunta" in headers:
                    ws.cell(rr, headers["P_Conjunta"]).number_format = "0.0%"
                if "P_LCB" in headers:
                    ws.cell(rr, headers["P_LCB"]).number_format = "0.0%"
                if "Fiabilidad" in headers:
                    ws.cell(rr, headers["Fiabilidad"]).number_format = "0.0%"
                for pct_col in ("TasaReciente", "TasaAnterior", "BrechaRegimen"):
                    if pct_col in headers:
                        ws.cell(rr, headers[pct_col]).number_format = "0.0%"
                for dec_col in ("PhiMaxAbs", "LiftConjunto"):
                    if dec_col in headers:
                        ws.cell(rr, headers[dec_col]).number_format = "0.00"

                ws.row_dimensions[rr].height = 44

        width_by_header = {
            "RankingPartido": 9,
            "Fecha": 12,
            "HoraPeru": 9,
            "Competicion": 22,
            "Local": 22,
            "Visitante": 22,
            "VarianteRank": 9,
            "Variante": 25,
            "Patas": 80,
            "P_Conjunta": 13,
            "P_LCB": 13,
            "CuotaJustaModelo": 14,
            "CuotaMinROI29": 14,
            "CuotaRequerida": 14,
            "CuotaReal": 13,
            "ZonaPrecio": 14,
            "RiesgoCombinado": 16,
            "Fiabilidad": 12,
            "Soporte": 11,
            "SoporteEfectivo": 14,
            "Dependencia": 13,
            "PhiMaxAbs": 12,
            "LiftConjunto": 12,
            "TasaReciente": 13,
            "TasaAnterior": 13,
            "BrechaRegimen": 13,
            "RegimenEstable": 14,
            "EstadoPreCuota": 15,
            "ESTADO_REAL": 18,
            "EV_REAL": 12,
        }

        for name, idx in headers.items():
            ws.column_dimensions[get_column_letter(idx)].width = width_by_header.get(name, 14)

        # Técnico
        tech = wb["TECNICO_V9_3"]
        tech.freeze_panes = "A2"
        tech.auto_filter.ref = tech.dimensions

        for c in tech[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1F4E78")

    out.seek(0)
    return out.getvalue()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
      <h1>⚽ Bet Builder V9.3.1 CONTEXT PRO</h1>
      <p><b>Rotación, fase competitiva, calendario y once confirmado.</b></p>
      <span class="pill blue">CUOTA REAL ≥ 4.20</span>
      <span class="pill amber">COTIZAR</span>
      <span class="pill green">VALIDAR EV</span>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="info-box">
      <b>Cambio clave:</b> V9.3.1 no supone que Champions, Libertadores u otro
      torneo garantice el once principal. Evalúa fase, descanso, carga y el
      siguiente compromiso; exige alineación confirmada antes de habilitar
      una apuesta y bloquea builders distintos del generado por el modelo.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATA
# ============================================================

meta = load_meta()

try:
    if cache_current(meta):
        data = load_data()
    else:
        with st.status(
            "Construyendo V9.3.1 para los próximos 7 días…",
            expanded=True,
        ) as status:
            st.write("Descargando histórico y calendario…")
            data, meta = run_and_save()
            status.update(
                label="V9.3.1 actualizado",
                state="complete",
                expanded=False,
            )

except Exception as e:
    st.error("No fue posible ejecutar V9.3.1.")
    st.code(str(e))

    with st.expander("Detalle técnico"):
        st.code(traceback.format_exc())

    if DATA_FILE.exists():
        data = load_data()
    else:
        data = pd.DataFrame()


# ============================================================
# CONTROLES
# ============================================================

c1, c2 = st.columns(2)

with c1:
    if st.button(
        "🔄 Actualizar V9.3.1",
        use_container_width=True,
        type="primary",
    ):
        try:
            with st.status(
                "Recalculando mercado y riesgo…",
                expanded=True,
            ) as status:
                data, meta = run_and_save()
                status.update(
                    label="Actualización terminada",
                    state="complete",
                    expanded=False,
                )
            st.rerun()
        except Exception as e:
            st.error(str(e))

with c2:
    if not data.empty:
        st.download_button(
            "📊 Excel V9.3.1 para cotizar",
            data=excel_bytes(data),
            file_name="BET_BUILDER_V9_3_COTIZAR_4_20.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

if meta:
    st.caption(
        f"Ventana: {meta.get('window_start','—')} → "
        f"{meta.get('window_end','—')} · "
        f"Versión: {meta.get('version',APP_VERSION)}"
    )
    st.caption(
        "Incluye partidos de hoy que todavía no comenzaron; los iniciados "
        "se eliminan usando la hora oficial de Perú."
    )


# ============================================================
# LISTA
# ============================================================

if data.empty:
    st.warning("No hay candidatos V9.3.1 modelables en esta ventana.")
else:
    # Resumen
    matches = data["RankingPartido"].nunique()
    ideal = int(
        data["ZonaPrecio"].isin(["IDEAL", "PRECIO_ALTO"]).sum()
    )

    a, b, c = st.columns(3)
    a.metric("Partidos", matches)
    b.metric("Builders a cotizar", len(data))
    c.metric("Zona precio útil", ideal)

    # Filtros
    zones = ["TODAS"] + sorted(data["ZonaPrecio"].dropna().unique().tolist())
    risk = ["TODOS"] + sorted(data["RiesgoCombinado"].dropna().unique().tolist())

    f1, f2, f3 = st.columns(3)

    zone_sel = f1.selectbox("Zona de precio", zones)
    risk_sel = f2.selectbox("Riesgo combinado", risk)
    bookmaker = f3.selectbox(
        "Casa para registrar cuota",
        ["Betsafe", "Betano", "Betsson", "Apuesta Total", "Otra"],
    )

    if QUOTE_FILE.exists():
        st.download_button(
            "Descargar historial de cuotas reales",
            data=QUOTE_FILE.read_bytes(),
            file_name="COTIZACIONES_REALES_V9_3.csv",
            mime="text/csv",
            use_container_width=True,
        )

    view = data.copy()

    if zone_sel != "TODAS":
        view = view[view["ZonaPrecio"] == zone_sel]

    if risk_sel != "TODOS":
        view = view[view["RiesgoCombinado"] == risk_sel]

    for match_rank, group in view.groupby("RankingPartido", sort=True):
        first = group.iloc[0]

        try:
            date_txt = pd.Timestamp(first["Fecha"]).strftime("%d/%m")
        except Exception:
            date_txt = str(first["Fecha"])

        st.markdown(
            f"""
            <div class="match-card">
              <span class="pill blue">#{int(match_rank)}</span>
              <span class="pill gray">{first['Competicion']}</span>
              <div class="match-title">{first['Local']} vs {first['Visitante']}</div>
              <div class="sub">{date_txt} · {first.get('HoraPeru','')} PET</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for _, row in group.iterrows():
            zone = str(row["ZonaPrecio"])
            zone_color = (
                "green"
                if zone == "IDEAL"
                else "amber"
                if zone in ("CORTA", "PRECIO_ALTO")
                else "red"
            )

            st.markdown(
                f"""
                <span class="pill {zone_color}">{zone}</span>
                <span class="pill blue">{row['Variante']}</span>
                <span class="pill gray">Riesgo {row['RiesgoCombinado']}</span>
                """,
                unsafe_allow_html=True,
            )

            for leg in str(row["Patas"]).split(" | "):
                st.markdown(
                    f'<div class="leg">{leg}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                f"""
                <div class="numbers">
                  <div><b>PROB. MODELO</b><span>{pct(row['P_Conjunta'])}</span></div>
                  <div><b>CUOTA JUSTA</b><span>{num(row['CuotaJustaModelo'])}</span></div>
                  <div><b>CUOTA REQUERIDA</b><span>{num(row['CuotaRequerida'])}</span></div>
                  <div><b>LCB</b><span>{pct(row['P_LCB'])}</span></div>
                  <div><b>FIABILIDAD</b><span>{pct(row['Fiabilidad'])}</span></div>
                  <div><b>SOPORTE</b><span>{int(row['Soporte']) if pd.notna(row['Soporte']) else '—'}</span></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.caption(str(row["ZonaPrecioTexto"]))

            key = (
                f"q_{int(row['RankingPartido'])}_"
                f"{int(row['VarianteRank'])}"
            )

            actual = st.number_input(
                "Cuota REAL de la casa para este builder",
                min_value=0.0,
                max_value=50.0,
                value=0.0,
                step=0.05,
                key=key,
            )

            st.code(
                f"FIRMA {row.get('FirmaCombinacion', '—')} · "
                f"{row.get('CodigosPatas', '')}",
                language=None,
            )
            exact_confirmed = st.checkbox(
                "Confirmo que la casa muestra exactamente estas selecciones y líneas",
                value=False,
                key=f"exact_{key}",
            )

            validation = v9.validate_real_quote(
                row,
                actual,
                exact_confirmed=exact_confirmed,
                quoted_signature=row.get("FirmaCombinacion", ""),
            )

            if actual > 0 and st.button(
                "Guardar esta cotización",
                key=f"save_{key}",
                use_container_width=True,
            ):
                save_real_quote(row, bookmaker, actual, validation)
                st.success("Cotización guardada para validar precios reales del modelo.")

            if validation["status"] == "PENDIENTE":
                st.info(
                    "Cotiza esta combinación en la casa. "
                    "No es APOSTAR hasta ingresar la cuota real."
                )

            elif validation["status"] == "DESCARTAR_CUOTA":
                st.error(
                    "❌ DESCARTAR POR CUOTA — "
                    + validation["message"]
                )

            elif validation["status"] == "NO_ALCANZA_ROI":
                st.warning(
                    "⚠️ CUOTA ≥4.20, PERO NO HAY MARGEN SUFICIENTE — "
                    + validation["message"]
                )

            elif validation["status"] == "VALIDA":
                st.success(
                    "✅ APUESTA VÁLIDA SEGÚN V9.3.1 — "
                    + validation["message"]
                )
            else:
                st.warning("⚠️ NO AUTORIZADA — " + validation["message"])

            with st.expander("Riesgo y contexto"):
                st.write(
                    f"**Riesgo combinado:** {row['RiesgoCombinado']}"
                )
                st.write(
                    f"**Fase:** Local {row['FaseLocal']} · "
                    f"Visita {row['FaseVisitante']}"
                )
                st.write(
                    f"**Descanso:** Local {row['DescansoLocal']} días · "
                    f"Visita {row['DescansoVisitante']} días"
                )
                st.write(
                    f"**Disponibilidad:** {row['NotaDisponibilidad']}"
                )
                st.write(
                    f"**Fase competitiva:** {row.get('FaseCompetitiva','—')} · "
                    f"importancia {row.get('ImportanciaPartido','—')}/100"
                )
                st.write(
                    f"**Rotación:** {row.get('RiesgoRotacion','—')} · "
                    f"alineación {row.get('EstadoAlineacion','—')} · "
                    f"estado {row.get('EstadoPreCuota','—')}"
                )
                st.write(
                    f"**Once habitual:** local {row.get('EstadoOnceLocal','—')} "
                    f"({pct(row.get('ContinuidadOnceLocal'))}) · visita "
                    f"{row.get('EstadoOnceVisitante','—')} "
                    f"({pct(row.get('ContinuidadOnceVisitante'))})"
                )
                st.write(f"**Contexto:** {row.get('NotaContexto','—')}")
                st.write(
                    f"**Dependencia:** {row.get('Dependencia','—')} · "
                    f"Phi máx. {num(row.get('PhiMaxAbs'))} · "
                    f"lift {num(row.get('LiftConjunto'))}"
                )
                gap = safe_float(row.get("BrechaRegimen"))
                if pd.notna(gap):
                    st.write(
                        f"**Estabilidad temporal:** brecha {gap*100:.1f} pp · "
                        f"estable: {'sí' if bool(row.get('RegimenEstable', True)) else 'no'}"
                    )
                if str(row.get("NotaFatiga", "")).strip():
                    st.write(
                        f"**Fatiga:** {row['NotaFatiga']}"
                    )

            st.divider()



# ============================================================
# BACKTEST ÚLTIMOS 7 DÍAS
# ============================================================

st.markdown("---")
st.markdown("## 🧪 Backtest temporal configurable")

st.info(
    "Reconstruye V9.3.1 como si estuviéramos antes de cada partido. "
    "La cuota es de simulación; no afirma que la casa la ofreciera históricamente."
)

bt_c1, bt_c2, bt_c3, bt_c4 = st.columns(4)

bt_stake = bt_c1.number_input(
    "Stake por apuesta (S/)",
    min_value=1.0,
    max_value=10000.0,
    value=100.0,
    step=10.0,
    key="bt_stake",
)

bt_odds = bt_c2.number_input(
    "Cuota simulada",
    min_value=1.01,
    max_value=20.0,
    value=4.20,
    step=0.05,
    key="bt_odds",
)

default_end = (
    datetime.now(base.TZ_PERU).date()
    - pd.Timedelta(days=1)
)

bt_days = bt_c3.selectbox(
    "Ventana (días)",
    [7, 30, 60, 90],
    index=1,
    key="bt_days",
)

bt_end = bt_c4.date_input(
    "Último día",
    value=default_end,
    key="bt_end",
)

bt_max_bets = st.slider(
    "Máximo de apuestas simuladas",
    min_value=10,
    max_value=200,
    value=60,
    step=10,
)

if st.button(
    "▶️ EJECUTAR BACKTEST TEMPORAL",
    use_container_width=True,
):
    try:
        with st.status(
            "Ejecutando walk-forward V9.3.1…",
            expanded=True,
        ) as bt_status:

            st.write("Usando solo información previa a cada partido…")

            bt_bets, bt_summary, bt_comp, bt_niche = v9.backtest_v9_window(
                stake=bt_stake,
                settlement_odds=bt_odds,
                max_bets=bt_max_bets,
                end_date=bt_end,
                days=bt_days,
            )

            st.session_state["v9_2_backtest"] = (
                bt_bets,
                bt_summary,
                bt_comp,
                bt_niche,
            )

            bt_status.update(
                label="Backtest terminado",
                state="complete",
                expanded=False,
            )

    except Exception:
        st.error("No fue posible ejecutar el backtest.")
        with st.expander("Detalle técnico"):
            st.code(traceback.format_exc())


if "v9_2_backtest" in st.session_state:

    bt_bets, bt_summary, bt_comp, bt_niche = st.session_state["v9_2_backtest"]

    st.caption(
        f"Ventana: {bt_summary.get('start','—')} → "
        f"{bt_summary.get('end','—')}"
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Apuestas", bt_summary.get("bets", 0))
    m2.metric("Ganadas", bt_summary.get("wins", 0))

    hit = bt_summary.get("hit_rate", np.nan)
    m3.metric(
        "Hit rate",
        "—" if pd.isna(hit) else f"{hit*100:.1f}%",
    )

    roi_bt = bt_summary.get("roi", np.nan)
    m4.metric(
        "ROI",
        "—" if pd.isna(roi_bt) else f"{roi_bt*100:.1f}%",
    )

    d1, d2, d3, d4 = st.columns(4)

    d1.metric(
        "Apostado",
        f"S/ {bt_summary.get('staked',0):,.0f}",
    )

    d2.metric(
        "Ganancia neta",
        f"S/ {bt_summary.get('net',0):,.0f}",
    )

    d3.metric(
        "Max drawdown",
        f"S/ {bt_summary.get('max_drawdown',0):,.0f}",
    )

    d4.metric(
        "Racha perdedora",
        bt_summary.get("longest_losing_streak", 0),
    )

    st.warning(
        "La cuota usada aquí es hipotética. El ROI real requiere las cuotas "
        "históricas exactas del Bet Builder de la casa."
    )

    if bt_bets is None or bt_bets.empty:
        st.info(bt_summary.get("note", "No hubo apuestas modelables."))

    else:
        cols = [
            c
            for c in [
                "Fecha",
                "Competicion",
                "Local",
                "Visitante",
                "Variante",
                "Patas",
                "P_Modelo",
                "P_LCB",
                "CuotaRequerida",
                "Resultado",
                "Stake",
                "CuotaSimulada",
                "GananciaNeta",
            ]
            if c in bt_bets.columns
        ]

        st.dataframe(
            bt_bets[cols],
            use_container_width=True,
            hide_index=True,
        )

        if bt_comp is not None and not bt_comp.empty:
            with st.expander("Rendimiento por competición"):
                st.dataframe(
                    bt_comp,
                    use_container_width=True,
                    hide_index=True,
                )

        if bt_niche is not None and not bt_niche.empty:
            with st.expander("Validación por nicho"):
                st.caption(
                    "Un nicho necesita al menos 20 apuestas en la ventana y un "
                    "límite inferior de acierto superior al punto de equilibrio."
                )
                st.dataframe(
                    bt_niche,
                    use_container_width=True,
                    hide_index=True,
                )

        bt_out = BytesIO()

        with pd.ExcelWriter(
            bt_out,
            engine="openpyxl",
        ) as writer:

            bt_bets.to_excel(
                writer,
                sheet_name="APUESTAS",
                index=False,
            )

            pd.DataFrame([bt_summary]).to_excel(
                writer,
                sheet_name="RESUMEN",
                index=False,
            )

            if bt_comp is not None and not bt_comp.empty:
                bt_comp.to_excel(
                    writer,
                    sheet_name="POR_COMPETICION",
                    index=False,
                )

            if bt_niche is not None and not bt_niche.empty:
                bt_niche.to_excel(
                    writer,
                    sheet_name="POR_NICHO",
                    index=False,
                )

        bt_out.seek(0)

        st.download_button(
            "📥 Descargar backtest temporal",
            data=bt_out.getvalue(),
            file_name=f"BET_BUILDER_V9_3_BACKTEST_{bt_summary.get('days', bt_days)}_DIAS.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

with st.expander("ℹ️ Qué cambió en V9.3.1"):
    st.markdown(
        """
        - **4.20 ya no se supone.** Es un filtro de la cuota real.
        - Evalúa **fase competitiva, descanso, congestión y el siguiente
          compromiso** antes de priorizar un partido.
        - Una competición grande **no se interpreta automáticamente como
          once principal**: para habilitar `COTIZAR` exige alineación confirmada.
        - Bloquea mercados sensibles cuando hay riesgo de rotación: ganador,
          goleada, córners altos del favorito y varias líneas de primer tiempo.
        - El modo operativo usa **máximo tres selecciones reales**. Rangos,
          empates y córners 1T suspendidos quedan fuera de la recomendación.
        - Cada builder lleva una **firma exacta** para impedir sustituir +1.5
          por +1.75, 6+ córners por 7+, o asiático por hándicap de tres opciones.
        - La probabilidad es de la **combinación completa**, calculada
          directamente sobre partidos históricos similares.
        - Muestra **dependencia, lift y correlación Phi** para detectar
          patas redundantes o inestables.
        - El límite conservador usa **Wilson**, penaliza la búsqueda entre
          muchas plantillas y compara el régimen reciente con el anterior.
        - **No se multiplican probabilidades marginales** para fingir que
          los mercados son independientes.
        - El backtest puede cubrir 7, 30, 60 o 90 días y resume resultados
          por competición y por nicho.
        - El riesgo de rotación en vivo se valida prospectivamente; no se
          introduce retroactivamente en el backtest cuando no había datos.
        - Puedes guardar las cuotas reales para dejar de depender, con el
          tiempo, de una cuota histórica simulada.
        - Ninguna combinación se marca válida sin ingresar la cuota real.
        """
    )

st.caption(
    "Herramienta estadística experimental. La cuota y la compatibilidad "
    "final dependen de la casa y del evento. No garantiza ganancias. "
    "No uses crédito, dinero de gastos esenciales ni aumentes el monto para recuperar pérdidas."
)
