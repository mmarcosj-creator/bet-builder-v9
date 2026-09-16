"""Auditoria V10.3 - Registro, resolucion y metricas de pronosticos.

Objetivo de este modulo (y solo este):

  1. Guardar cada pronostico ANTES del inicio del partido, en un archivo
     append-only. Una vez que el partido arranca (KickoffUTC <= ahora), la
     fila queda congelada: no se vuelve a sobrescribir con un recalculo
     posterior, para que nadie pueda "mejorar" un pronostico ya jugado.
  2. Resolver automaticamente cada fila PENDIENTE contra el resultado oficial
     ya descargado por el motor (history / contexto 1T), sin pedir marcadores
     a mano.
  3. Calcular metricas de auditoria honestas: nunca se muestra "0.0%" cuando
     Evaluados = 0 (se muestra "SIN DATOS"), se separa por mercado y por
     color, se acompana de un intervalo de confianza (Wilson) y de un Brier
     score. No existe ningun "sello de sistema validado": una tasa de acierto
     de una semana no valida nada estadisticamente y este modulo no finge lo
     contrario (ver CRITERIOS_V10.md, seccion 6).

Este modulo NO decide apuestas, NO cambia umbrales de semaforo y NO reentrena
modelos. Eso sigue siendo responsabilidad exclusiva de bet_forecaster_v10.
Mezclar "medir si acertamos" con "decidir el umbral" es exactamente el tipo
de acoplamiento que ya causo el retroceso de la rama V10.2.2 Gatuno.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import bet_builder_v8_1_robust as base

RESULT_LABELS = {0: "LOCAL", 1: "EMPATE", 2: "VISITANTE"}

# Cuanto esperar despues del kickoff antes de intentar resolver. Un partido
# puede alargarse (prorroga, retraso); 3h15 cubre la enorme mayoria de casos
# sin arriesgarse a leer un marcador todavia parcial.
RESOLUTION_DELAY = timedelta(hours=3, minutes=15)

# Si tras esta cantidad de dias desde el kickoff el resultado sigue sin
# aparecer en las fuentes descargadas (partido pospuesto, fuente sin ese
# torneo, etc.) se marca SIN_DATO en vez de dejarlo PENDIENTE para siempre
# o -peor- inventar un resultado.
GRACE_PERIOD = timedelta(days=5)

# Umbral de similitud del resolver de nombres para aceptar un cruce entre el
# nombre mostrado en el pronostico y el nombre tal como aparece en la fuente
# de resultados. Mismo criterio de conservadurismo que el resto del sistema:
# ante la duda, no resuelve (mejor SIN_DATO que un acierto/fallo mal cruzado).
NAME_MATCH_THRESHOLD = 0.80

HISTORIAL_COLUMNS = [
    "EventID",
    "Fecha",
    "KickoffUTC",
    "CompKey",
    "Competicion",
    "Local",
    "Visitante",
    "Mercado",
    "Linea",
    "Pronostico",
    "Probabilidad",
    "Semaforo",
    "Version",
    "RegistradoEn",
    "EstadoResultado",   # PENDIENTE | ACERTADO | FALLADO | SIN_DATO
    "ResultadoReal",
    "ResueltoEn",
]


def _event_id(comp_key: Any, fecha: Any, local: Any, visitante: Any) -> str:
    day = pd.Timestamp(fecha).date().isoformat() if pd.notna(fecha) else "sin-fecha"
    return "|".join([
        str(comp_key or "").strip(),
        day,
        base.norm_texto(local),
        base.norm_texto(visitante),
    ])


def cargar_historial(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=HISTORIAL_COLUMNS)
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=HISTORIAL_COLUMNS)
    for col in HISTORIAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[HISTORIAL_COLUMNS]


def guardar_historial(df: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def registrar_pronosticos(
    markets_df: pd.DataFrame,
    path: str | Path,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Agrega los pronosticos de la corrida actual sin pisar filas congeladas.

    Una fila se considera congelada (no editable) si su KickoffUTC ya paso.
    Antes del kickoff, el recalculo SI puede actualizar la fila (para que
    refleje la ultima calibracion disponible); esto es intencional y distinto
    de "pisar resultados" porque el partido todavia no se juega.
    """
    now = now or pd.Timestamp.now(tz="UTC")
    historial = cargar_historial(path)

    # Se trabaja con un dict (EventID, Mercado) -> fila, y se reconstruye el
    # DataFrame al final. Asignar por .loc con MultiIndex sobre un DataFrame
    # que puede empezar vacio es fragil en pandas (corrompe columnas); un
    # dict explicito no tiene esa trampa.
    registro: dict[tuple[str, str], dict[str, Any]] = {
        (row["EventID"], row["Mercado"]): row.to_dict() for _, row in historial.iterrows()
    }

    if markets_df is not None and not markets_df.empty:
        for _, row in markets_df.iterrows():
            if str(row.get("Pronostico", "")).strip().upper() in {"", "SIN PRONOSTICO", "NAN"}:
                continue  # no se audita lo que el propio motor se abstuvo de decidir
            event_id = _event_id(row.get("CompKey"), row.get("Fecha"), row.get("Local"), row.get("Visitante"))
            key = (event_id, row.get("Mercado"))
            if key in registro:
                kickoff = pd.to_datetime(registro[key].get("KickoffUTC"), utc=True, errors="coerce")
                if pd.notna(kickoff) and kickoff <= now:
                    continue  # congelada: el partido ya empezo, no se toca
            registro[key] = {
                "EventID": event_id,
                "Fecha": row.get("Fecha"),
                "KickoffUTC": row.get("KickoffUTC"),
                "CompKey": row.get("CompKey"),
                "Competicion": row.get("Competicion"),
                "Local": row.get("Local"),
                "Visitante": row.get("Visitante"),
                "Mercado": row.get("Mercado"),
                "Linea": row.get("Linea"),
                "Pronostico": row.get("Pronostico"),
                "Probabilidad": row.get("Probabilidad"),
                "Semaforo": row.get("Semaforo"),
                "Version": row.get("Version"),
                "RegistradoEn": now.isoformat(),
                "EstadoResultado": "PENDIENTE",
                "ResultadoReal": np.nan,
                "ResueltoEn": np.nan,
            }

    if not registro:
        return pd.DataFrame(columns=HISTORIAL_COLUMNS)
    return pd.DataFrame(list(registro.values()), columns=HISTORIAL_COLUMNS)


@dataclass
class _MatchOutcome:
    hg: float
    ag: float
    hthg: float
    htag: float
    hy: float
    ay: float
    h1_corners: float | None


def _buscar_resultado(
    local: str,
    visitante: str,
    fecha: Any,
    comp_key: Any,
    history_df: pd.DataFrame,
    h1_context_df: pd.DataFrame | None,
) -> _MatchOutcome | None:
    if history_df is None or history_df.empty:
        return None
    fecha_ts = pd.Timestamp(fecha)
    ventana = history_df[
        (history_df["Date"] >= fecha_ts - pd.Timedelta(days=1))
        & (history_df["Date"] <= fecha_ts + pd.Timedelta(days=2))
    ]
    if comp_key:
        acotado = ventana[ventana["CompKey"].astype(str) == str(comp_key)]
        if not acotado.empty:
            ventana = acotado
    if ventana.empty:
        return None

    candidatos = pd.unique(pd.concat([ventana["HomeTeam"], ventana["AwayTeam"]]).astype(str))
    local_resuelto, score_l = base.resolver_nombre(local, list(candidatos))
    visita_resuelto, score_v = base.resolver_nombre(visitante, list(candidatos))
    if score_l < NAME_MATCH_THRESHOLD or score_v < NAME_MATCH_THRESHOLD:
        return None

    fila = ventana[
        (ventana["HomeTeam"].astype(str) == local_resuelto)
        & (ventana["AwayTeam"].astype(str) == visita_resuelto)
    ]
    if fila.empty:
        return None
    fila = fila.iloc[0]

    h1_corners = None
    if h1_context_df is not None and not h1_context_df.empty and "H1CornersTotal" in h1_context_df.columns:
        ventana_c = h1_context_df[
            (pd.to_datetime(h1_context_df["Date"]) >= fecha_ts - pd.Timedelta(days=1))
            & (pd.to_datetime(h1_context_df["Date"]) <= fecha_ts + pd.Timedelta(days=2))
        ]
        fila_c = ventana_c[
            (ventana_c["HomeTeam"].astype(str).apply(base.norm_texto) == base.norm_texto(local_resuelto))
            & (ventana_c["AwayTeam"].astype(str).apply(base.norm_texto) == base.norm_texto(visita_resuelto))
        ]
        if not fila_c.empty and pd.notna(fila_c.iloc[0].get("H1CornersTotal")):
            h1_corners = float(fila_c.iloc[0]["H1CornersTotal"])

    def num(v):
        try:
            v = float(v)
            return v if math.isfinite(v) else np.nan
        except Exception:
            return np.nan

    return _MatchOutcome(
        hg=num(fila.get("FTHG")),
        ag=num(fila.get("FTAG")),
        hthg=num(fila.get("HTHG")),
        htag=num(fila.get("HTAG")),
        hy=num(fila.get("HY")),
        ay=num(fila.get("AY")),
        h1_corners=h1_corners,
    )


def _evaluar_mercado(mercado: str, pronostico: str, local: str, visitante: str, outcome: _MatchOutcome) -> bool | None:
    pronostico = str(pronostico).strip().upper()

    if mercado == "Resultado 1X2":
        if pd.isna(outcome.hg) or pd.isna(outcome.ag):
            return None
        actual = RESULT_LABELS[0] if outcome.hg > outcome.ag else RESULT_LABELS[1] if outcome.hg == outcome.ag else RESULT_LABELS[2]
        return pronostico == actual

    if mercado == "Goles 1.er tiempo":
        if pd.isna(outcome.hthg) or pd.isna(outcome.htag):
            return None
        total = outcome.hthg + outcome.htag
        actual = "MAS DE 1.5" if total > 1.5 else "MENOS DE 1.5"
        return pronostico == actual

    if mercado == "Corners 1.er tiempo":
        if outcome.h1_corners is None:
            return None
        actual = "MAS DE 4.5" if outcome.h1_corners > 4.5 else "MENOS DE 4.5"
        return pronostico == actual

    if mercado == "Tarjetas amarillas totales":
        if pd.isna(outcome.hy) or pd.isna(outcome.ay):
            return None
        total = outcome.hy + outcome.ay
        actual = "MAS DE 4.5" if total > 4.5 else "MENOS DE 4.5"
        return pronostico == actual

    if mercado == f"Goles {local}":
        if pd.isna(outcome.hg):
            return None
        actual = "MARCA 1+" if outcome.hg >= 1 else "NO MARCA"
        return pronostico == actual

    if mercado == f"Goles {visitante}":
        if pd.isna(outcome.ag):
            return None
        actual = "MARCA 1+" if outcome.ag >= 1 else "NO MARCA"
        return pronostico == actual

    return None


def resolver_pendientes(
    historial: pd.DataFrame,
    history_df: pd.DataFrame,
    h1_context_df: pd.DataFrame | None = None,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Cruza cada fila PENDIENTE con el resultado oficial ya descargado.

    No hace peticiones de red propias: recibe el `history` y el contexto 1T
    que `run_v10()` ya trajo en la corrida actual, para no duplicar descargas
    ni depender de una fuente distinta a la que entrena el modelo.
    """
    now = now or pd.Timestamp.now(tz="UTC")
    if historial.empty:
        return historial

    historial = historial.copy()
    # Si el CSV se acaba de crear, estas columnas pueden inferirse como
    # float64 (todo NaN); forzarlas a object evita que pandas rechace la
    # escritura de un string (p.ej. "2-1" o "ACERTADO") con LossySetitemError.
    for col in ("EstadoResultado", "ResultadoReal", "ResueltoEn"):
        historial[col] = historial[col].astype(object)
    pendientes = historial["EstadoResultado"] == "PENDIENTE"
    for idx in historial[pendientes].index:
        row = historial.loc[idx]
        kickoff = pd.to_datetime(row.get("KickoffUTC"), utc=True, errors="coerce")
        fecha = pd.to_datetime(row.get("Fecha"), errors="coerce")
        referencia = kickoff if pd.notna(kickoff) else fecha
        if pd.isna(referencia):
            continue
        if referencia.tzinfo is None:
            referencia = referencia.tz_localize("UTC")
        if now - referencia < RESOLUTION_DELAY:
            continue  # el partido probablemente sigue en juego

        outcome = _buscar_resultado(
            str(row["Local"]), str(row["Visitante"]), row["Fecha"], row.get("CompKey"),
            history_df, h1_context_df,
        )
        if outcome is None:
            if now - referencia > GRACE_PERIOD:
                historial.at[idx, "EstadoResultado"] = "SIN_DATO"
                historial.at[idx, "ResueltoEn"] = now.isoformat()
            continue

        acierto = _evaluar_mercado(row["Mercado"], row["Pronostico"], str(row["Local"]), str(row["Visitante"]), outcome)
        if acierto is None:
            if now - referencia > GRACE_PERIOD:
                historial.at[idx, "EstadoResultado"] = "SIN_DATO"
                historial.at[idx, "ResueltoEn"] = now.isoformat()
            continue

        historial.at[idx, "EstadoResultado"] = "ACERTADO" if acierto else "FALLADO"
        historial.at[idx, "ResultadoReal"] = (
            f"{outcome.hg:.0f}-{outcome.ag:.0f}"
            if not (pd.isna(outcome.hg) or pd.isna(outcome.ag)) else ""
        )
        historial.at[idx, "ResueltoEn"] = now.isoformat()

    return historial


def _wilson_interval(aciertos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = aciertos / n
    z2 = z * z
    centro = p + z2 / (2 * n)
    radio = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)
    denom = 1 + z2 / n
    return ((centro - radio) / denom, (centro + radio) / denom)


def calcular_metricas(historial: pd.DataFrame) -> pd.DataFrame:
    """Metricas por Mercado x Semaforo. Nunca reporta 0.0% con Evaluados=0."""
    if historial.empty:
        return pd.DataFrame(columns=[
            "Mercado", "Semaforo", "N_Registrado", "N_Pendiente", "N_SinDato",
            "N_Evaluado", "Aciertos", "TasaAcierto", "IC95_Bajo", "IC95_Alto", "Brier",
        ])

    filas = []
    for (mercado, semaforo), grupo in historial.groupby(["Mercado", "Semaforo"], dropna=False):
        evaluado = grupo[grupo["EstadoResultado"].isin(["ACERTADO", "FALLADO"])]
        aciertos = int((evaluado["EstadoResultado"] == "ACERTADO").sum())
        n_eval = int(len(evaluado))
        if n_eval > 0:
            tasa = aciertos / n_eval
            ic_bajo, ic_alto = _wilson_interval(aciertos, n_eval)
            probs = pd.to_numeric(evaluado["Probabilidad"], errors="coerce").to_numpy()
            outcomes = (evaluado["EstadoResultado"] == "ACERTADO").astype(float).to_numpy()
            valid = ~np.isnan(probs)
            brier = float(np.mean((probs[valid] - outcomes[valid]) ** 2)) if valid.any() else np.nan
        else:
            tasa, ic_bajo, ic_alto, brier = np.nan, np.nan, np.nan, np.nan
        filas.append({
            "Mercado": mercado,
            "Semaforo": semaforo,
            "N_Registrado": int(len(grupo)),
            "N_Pendiente": int((grupo["EstadoResultado"] == "PENDIENTE").sum()),
            "N_SinDato": int((grupo["EstadoResultado"] == "SIN_DATO").sum()),
            "N_Evaluado": n_eval,
            "Aciertos": aciertos,
            "TasaAcierto": tasa,
            "IC95_Bajo": ic_bajo,
            "IC95_Alto": ic_alto,
            "Brier": brier,
        })
    return pd.DataFrame(filas).sort_values(["Mercado", "Semaforo"]).reset_index(drop=True)


def formatear_tasa(tasa: float, n: int, minimo_fiable: int = 30) -> str:
    """Nunca devuelve '0.0%' para N=0; y avisa cuando la muestra es chica."""
    if n == 0 or pd.isna(tasa):
        return "SIN DATOS"
    texto = f"{tasa * 100:.1f}% (n={n})"
    if n < minimo_fiable:
        texto += " · muestra pequena, no concluyente"
    return texto


# ===========================================================================
# Puntos medios (goles esperados, tarjetas esperadas) vs. resultado real
# ===========================================================================
#
# Esto es distinto de auditar VERDE/AMARILLO/ROJO: aqui no hay un umbral que
# cruzar ("MAS DE 4.5"), sino un numero continuo (p. ej. "4.8 tarjetas
# esperadas") que se compara contra el numero real del partido ("6 tarjetas").
# El error (MAE) es la metrica honesta aqui; no existen aciertos/fallos
# binarios para un promedio.

PUNTOS_MEDIOS_COLUMNS = [
    "EventID",
    "Fecha",
    "KickoffUTC",
    "CompKey",
    "Competicion",
    "Local",
    "Visitante",
    "GolesEsperadosLocal",
    "GolesEsperadosVisitante",
    "GolesEsperados1T",
    "TarjetasEsperadas",
    "Version",
    "RegistradoEn",
    "EstadoResultado",  # PENDIENTE | RESUELTO | SIN_DATO
    "GolesRealesLocal",
    "GolesRealesVisitante",
    "GolesReales1T",
    "TarjetasReales",
    "ErrorGolesLocal",
    "ErrorGolesVisitante",
    "ErrorGoles1T",
    "ErrorTarjetas",
    "ResueltoEn",
]


def cargar_puntos_medios(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=PUNTOS_MEDIOS_COLUMNS)
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=PUNTOS_MEDIOS_COLUMNS)
    for col in PUNTOS_MEDIOS_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df[PUNTOS_MEDIOS_COLUMNS]


def guardar_puntos_medios(df: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def registrar_puntos_medios(
    matches_df: pd.DataFrame,
    path: str | Path,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Guarda, por partido, los 4 valores esperados antes del kickoff.

    Un partido = una fila (a diferencia del historial de mercados, aqui no
    hay un color ni un umbral; solo el numero predicho y, mas tarde, el
    numero real). Se congela igual que el historial de mercados: una vez
    que el partido empieza, el pronostico registrado no se toca.
    """
    now = now or pd.Timestamp.now(tz="UTC")
    historial = cargar_puntos_medios(path)
    registro: dict[str, dict[str, Any]] = {
        row["EventID"]: row.to_dict() for _, row in historial.iterrows()
    }

    if matches_df is not None and not matches_df.empty:
        for _, row in matches_df.iterrows():
            if "ErrorDatos" in row and pd.notna(row.get("ErrorDatos")) and str(row.get("ErrorDatos")).strip():
                continue  # partido no modelable; no tiene sentido auditar un numero que no existe
            event_id = _event_id(row.get("CompKey"), row.get("Fecha"), row.get("Local"), row.get("Visitante"))
            if event_id in registro:
                kickoff = pd.to_datetime(registro[event_id].get("KickoffUTC"), utc=True, errors="coerce")
                if pd.notna(kickoff) and kickoff <= now:
                    continue  # congelado
            registro[event_id] = {
                "EventID": event_id,
                "Fecha": row.get("Fecha"),
                "KickoffUTC": row.get("KickoffUTC"),
                "CompKey": row.get("CompKey"),
                "Competicion": row.get("Competicion"),
                "Local": row.get("Local"),
                "Visitante": row.get("Visitante"),
                "GolesEsperadosLocal": row.get("GolesEsperadosLocal"),
                "GolesEsperadosVisitante": row.get("GolesEsperadosVisitante"),
                "GolesEsperados1T": row.get("GolesEsperados1T"),
                "TarjetasEsperadas": row.get("TarjetasEsperadas"),
                "Version": row.get("Version"),
                "RegistradoEn": now.isoformat(),
                "EstadoResultado": "PENDIENTE",
                "GolesRealesLocal": np.nan,
                "GolesRealesVisitante": np.nan,
                "GolesReales1T": np.nan,
                "TarjetasReales": np.nan,
                "ErrorGolesLocal": np.nan,
                "ErrorGolesVisitante": np.nan,
                "ErrorGoles1T": np.nan,
                "ErrorTarjetas": np.nan,
                "ResueltoEn": np.nan,
            }

    if not registro:
        return pd.DataFrame(columns=PUNTOS_MEDIOS_COLUMNS)
    return pd.DataFrame(list(registro.values()), columns=PUNTOS_MEDIOS_COLUMNS)


def resolver_puntos_medios(
    historial_pm: pd.DataFrame,
    history_df: pd.DataFrame,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Cruza cada fila PENDIENTE contra el marcador y las tarjetas reales, y
    calcula el error absoluto de cada punto medio. No usa contexto 1T porque
    los goles/tarjetas totales ya vienen completos en el historico principal.
    """
    now = now or pd.Timestamp.now(tz="UTC")
    if historial_pm.empty:
        return historial_pm

    historial_pm = historial_pm.copy()
    for col in ("EstadoResultado", "ResueltoEn"):
        historial_pm[col] = historial_pm[col].astype(object)

    pendientes = historial_pm["EstadoResultado"] == "PENDIENTE"
    for idx in historial_pm[pendientes].index:
        row = historial_pm.loc[idx]
        kickoff = pd.to_datetime(row.get("KickoffUTC"), utc=True, errors="coerce")
        fecha = pd.to_datetime(row.get("Fecha"), errors="coerce")
        referencia = kickoff if pd.notna(kickoff) else fecha
        if pd.isna(referencia):
            continue
        if referencia.tzinfo is None:
            referencia = referencia.tz_localize("UTC")
        if now - referencia < RESOLUTION_DELAY:
            continue

        outcome = _buscar_resultado(
            str(row["Local"]), str(row["Visitante"]), row["Fecha"], row.get("CompKey"),
            history_df, None,
        )
        if outcome is None or pd.isna(outcome.hg) or pd.isna(outcome.ag):
            if now - referencia > GRACE_PERIOD:
                historial_pm.at[idx, "EstadoResultado"] = "SIN_DATO"
                historial_pm.at[idx, "ResueltoEn"] = now.isoformat()
            continue

        goles_1t_real = (
            outcome.hthg + outcome.htag if not (pd.isna(outcome.hthg) or pd.isna(outcome.htag)) else np.nan
        )
        tarjetas_real = outcome.hy + outcome.ay if not (pd.isna(outcome.hy) or pd.isna(outcome.ay)) else np.nan

        def err(pred, real):
            pred = pd.to_numeric(pred, errors="coerce")
            return float(abs(pred - real)) if pd.notna(pred) and pd.notna(real) else np.nan

        historial_pm.at[idx, "GolesRealesLocal"] = outcome.hg
        historial_pm.at[idx, "GolesRealesVisitante"] = outcome.ag
        historial_pm.at[idx, "GolesReales1T"] = goles_1t_real
        historial_pm.at[idx, "TarjetasReales"] = tarjetas_real
        historial_pm.at[idx, "ErrorGolesLocal"] = err(row.get("GolesEsperadosLocal"), outcome.hg)
        historial_pm.at[idx, "ErrorGolesVisitante"] = err(row.get("GolesEsperadosVisitante"), outcome.ag)
        historial_pm.at[idx, "ErrorGoles1T"] = err(row.get("GolesEsperados1T"), goles_1t_real)
        historial_pm.at[idx, "ErrorTarjetas"] = err(row.get("TarjetasEsperadas"), tarjetas_real)
        historial_pm.at[idx, "EstadoResultado"] = "RESUELTO"
        historial_pm.at[idx, "ResueltoEn"] = now.isoformat()

    return historial_pm


def calcular_metricas_puntos_medios(historial_pm: pd.DataFrame) -> pd.DataFrame:
    """MAE real, partido a partido, de cada punto medio. 'SIN DATOS' si N=0,
    nunca un MAE de 0.0 fabricado.
    """
    columnas = ["Metrica", "N_Registrado", "N_Pendiente", "N_SinDato", "N_Evaluado", "MAE"]
    if historial_pm.empty:
        return pd.DataFrame(columns=columnas)

    pares = [
        ("Goles esperados local", "ErrorGolesLocal"),
        ("Goles esperados visitante", "ErrorGolesVisitante"),
        ("Goles esperados 1T", "ErrorGoles1T"),
        ("Tarjetas esperadas", "ErrorTarjetas"),
    ]
    filas = []
    for etiqueta, columna_error in pares:
        errores = pd.to_numeric(historial_pm[columna_error], errors="coerce").dropna()
        filas.append({
            "Metrica": etiqueta,
            "N_Registrado": int(len(historial_pm)),
            "N_Pendiente": int((historial_pm["EstadoResultado"] == "PENDIENTE").sum()),
            "N_SinDato": int((historial_pm["EstadoResultado"] == "SIN_DATO").sum()),
            "N_Evaluado": int(len(errores)),
            "MAE": float(errores.mean()) if len(errores) > 0 else np.nan,
        })
    return pd.DataFrame(filas, columns=columnas)
