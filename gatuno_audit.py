"""Auditoría prospectiva y compuerta adaptativa para V10.3 Gatuno PRO.

Las predicciones se congelan antes del partido y nunca se sobrescriben. Los
resultados oficiales se usan para cerrar cada mercado y medir calibración. El
aprendizaje de auditoría es conservador: solo puede degradar una señal futura;
nunca convierte una señal amarilla o roja en verde.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import bet_builder_v8_1_robust as base


DATA_DIR = Path("app_data_v10")
HISTORY_FILE = DATA_DIR / "historial_pronosticos_v103.csv"
RESOLVED_STATES = {"ACERTADO", "FALLADO"}
ABSTAIN_CODES = {"", "ABSTAIN", "SIN PRONOSTICO", "NAN"}

MIN_GREEN_CERTIFICATION = 300
MIN_CALENDAR_DAYS = 30
MIN_MARKETS_WITH_SUPPORT = 4
MIN_PER_MARKET = 30


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        result = float(value)
        return result if np.isfinite(result) else default
    except Exception:
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "si", "sí", "yes"}


def _atomic_csv(frame: pd.DataFrame, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    os.replace(temporary, target)


def load_history(path: str | Path = HISTORY_FILE) -> pd.DataFrame:
    target = Path(path)
    if not target.exists():
        return pd.DataFrame()
    try:
        history = pd.read_csv(
            target,
            dtype={
                "PredictionID": "string",
                "EventKey": "string",
                "EventID": "string",
                "HomeESPNID": "string",
                "AwayESPNID": "string",
            },
        )
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    return history


def _fallback_market_code(row: pd.Series | dict[str, Any]) -> str:
    market = str(row.get("Mercado", ""))
    if market == "Resultado 1X2":
        return "RESULT_1X2"
    if market == "Goles 1.er tiempo":
        return "H1_GOALS_OU15"
    if market == "Corners 1.er tiempo":
        return "H1_CORNERS_OU45"
    if market == "Tarjetas amarillas totales":
        return "YELLOW_CARDS_OU45"
    if market == f"Goles {row.get('Local', '')}":
        return "HOME_SCORE_OU05"
    if market == f"Goles {row.get('Visitante', '')}":
        return "AWAY_SCORE_OU05"
    return "UNKNOWN"


def _fallback_prediction_code(market_code: str, prediction: Any) -> str:
    value = str(prediction).strip().upper()
    if value in ABSTAIN_CODES:
        return "ABSTAIN"
    if market_code == "RESULT_1X2":
        return {"LOCAL": "HOME", "EMPATE": "DRAW", "VISITANTE": "AWAY"}.get(value, "ABSTAIN")
    if market_code in {"H1_GOALS_OU15", "H1_CORNERS_OU45", "YELLOW_CARDS_OU45"}:
        return "OVER" if value.startswith("MAS") else "UNDER" if value.startswith("MENOS") else "ABSTAIN"
    if market_code in {"HOME_SCORE_OU05", "AWAY_SCORE_OU05"}:
        return "YES" if value.startswith("MARCA") else "NO" if value.startswith("NO MARCA") else "ABSTAIN"
    return "ABSTAIN"


def event_key(row: pd.Series | dict[str, Any]) -> str:
    event_id = str(row.get("EventID", "")).strip()
    if event_id and event_id.lower() != "nan":
        return event_id
    parts = [
        str(row.get("CompKey", "")),
        str(row.get("KickoffUTC", "")),
        str(row.get("Local", "")),
        str(row.get("Visitante", "")),
    ]
    return "|".join(parts)


def prediction_id(row: pd.Series | dict[str, Any]) -> str:
    market_code = str(row.get("MercadoCodigo", "")) or _fallback_market_code(row)
    signal_snapshot = str(
        row.get("SemaforoFinal", row.get("Semaforo", "SIN_SEMAFORO"))
    ).upper()
    material = "|".join(
        [
            event_key(row),
            market_code,
            str(row.get("Linea", "")),
            str(row.get("Version", "V10.3-GATUNO-PRO")),
            signal_snapshot,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def record_predictions(
    markets: pd.DataFrame,
    path: str | Path = HISTORY_FILE,
    now_utc: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Congela la primera predicción prepartido de cada mercado."""
    if markets is None or markets.empty:
        return load_history(path), {"insertados": 0, "omitidos": 0}

    now = now_utc or pd.Timestamp.now(tz="UTC")
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")

    old = load_history(path)
    existing = set(old.get("PredictionID", pd.Series(dtype=str)).astype(str))
    emitted = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []
    omitted = 0

    for _, source in markets.iterrows():
        kickoff = pd.to_datetime(source.get("KickoffUTC"), utc=True, errors="coerce")
        if pd.isna(kickoff) or kickoff <= now:
            omitted += 1
            continue
        market_code = str(source.get("MercadoCodigo", ""))
        if not market_code or market_code == "nan":
            market_code = _fallback_market_code(source)
        prediction_code = str(source.get("PronosticoCodigo", ""))
        if not prediction_code or prediction_code == "nan":
            prediction_code = _fallback_prediction_code(market_code, source.get("Pronostico", ""))
        if prediction_code in ABSTAIN_CODES or market_code == "UNKNOWN":
            omitted += 1
            continue

        pid = prediction_id({**source.to_dict(), "MercadoCodigo": market_code})
        if pid in existing:
            omitted += 1
            continue
        model_signal = str(source.get("SemaforoModelo", source.get("Semaforo", "ROJO")))
        final_signal = str(source.get("SemaforoFinal", source.get("Semaforo", model_signal)))
        records.append(
            {
                "PredictionID": pid,
                "EventKey": event_key(source),
                "EventID": str(source.get("EventID", "")),
                "KickoffUTC": str(source.get("KickoffUTC", "")),
                "Fecha": str(source.get("Fecha", "")),
                "HoraPeru": str(source.get("HoraPeru", "")),
                "CompKey": str(source.get("CompKey", "")),
                "Competicion": str(source.get("Competicion", "")),
                "Local": str(source.get("Local", "")),
                "Visitante": str(source.get("Visitante", "")),
                "HomeESPNID": str(source.get("HomeESPNID", "")),
                "AwayESPNID": str(source.get("AwayESPNID", "")),
                "Mercado": str(source.get("Mercado", "")),
                "MercadoCodigo": market_code,
                "Linea": str(source.get("Linea", "")),
                "Pronostico": str(source.get("Pronostico", "")),
                "PronosticoCodigo": prediction_code,
                "Probabilidad": _safe_float(source.get("Probabilidad")),
                "PConservadora": _safe_float(source.get("PConservadora")),
                "Fiabilidad": _safe_float(source.get("Fiabilidad")),
                "Soporte": int(_safe_float(source.get("Soporte"), 0)),
                "ModeloSuperaBase": _as_bool(source.get("ModeloSuperaBase", False)),
                "SemaforoModelo": model_signal,
                "SemaforoFinal": final_signal,
                "Motivo": str(source.get("Motivo", "")),
                "Version": str(source.get("Version", "")),
                "EmitidoEnUTC": emitted,
                "EstadoResultado": "PENDIENTE",
                "ResultadoReal": "",
                "CerradoEnUTC": "",
                "FuenteResultado": "",
                "MotivoCierre": "",
                "GolesLocal": np.nan,
                "GolesVisitante": np.nan,
                "Goles1T": np.nan,
                "Corners1T": np.nan,
                "TarjetasAmarillas": np.nan,
            }
        )
        existing.add(pid)

    if records:
        new = pd.DataFrame(records)
        combined = pd.concat([old, new], ignore_index=True, sort=False) if not old.empty else new
        combined = combined.drop_duplicates(subset=["PredictionID"], keep="first")
        _atomic_csv(combined, path)
    else:
        combined = old
    return combined, {"insertados": len(records), "omitidos": omitted}


def _score(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("value", value.get("displayValue"))
    return _safe_float(value)


def _period_number(play: dict[str, Any]) -> int | None:
    period = play.get("period")
    if isinstance(period, dict):
        period = period.get("number", period.get("value"))
    value = _safe_float(period)
    return int(value) if np.isfinite(value) else None


def _h1_corners_with_zero(summary: dict[str, Any], home_id: str, away_id: str) -> float:
    parsed = base.parse_h1_corners_from_summary(summary, home_id, away_id)
    value = _safe_float(parsed.get("H1CornersTotal"))
    if np.isfinite(value):
        return value
    plays = [play for play in (summary.get("plays") or []) if isinstance(play, dict)]
    if plays and any(_period_number(play) == 1 for play in plays):
        return 0.0
    return np.nan


def _parse_event(ev: dict[str, Any]) -> dict[str, Any] | None:
    status = ((ev.get("status") or {}).get("type") or {})
    completed = bool(status.get("completed")) or str(status.get("state", "")).lower() == "post"
    if not completed:
        return None
    competitions = ev.get("competitions") or []
    if not competitions:
        return None
    competitors = competitions[0].get("competitors") or []
    sides = {str(item.get("homeAway")): item for item in competitors}
    if "home" not in sides or "away" not in sides:
        return None
    home, away = sides["home"], sides["away"]
    home_team, away_team = home.get("team") or {}, away.get("team") or {}
    home_score, away_score = _score(home.get("score")), _score(away.get("score"))
    if not np.isfinite(home_score) or not np.isfinite(away_score):
        return None
    return {
        "EventID": str(ev.get("id", "")),
        "HomeID": str(home_team.get("id", "")),
        "AwayID": str(away_team.get("id", "")),
        "HomeName": str(home_team.get("displayName", home_team.get("shortDisplayName", ""))),
        "AwayName": str(away_team.get("displayName", away_team.get("shortDisplayName", ""))),
        "HomeGoals": int(home_score),
        "AwayGoals": int(away_score),
    }


def _grade(row: pd.Series, observed: dict[str, Any]) -> tuple[str | None, str]:
    market = str(row.get("MercadoCodigo", ""))
    prediction = str(row.get("PronosticoCodigo", ""))
    home_goals = int(observed["HomeGoals"])
    away_goals = int(observed["AwayGoals"])
    actual = ""

    if market == "RESULT_1X2":
        actual = "HOME" if home_goals > away_goals else "DRAW" if home_goals == away_goals else "AWAY"
    elif market == "H1_GOALS_OU15":
        value = _safe_float(observed.get("H1Goals"))
        if not np.isfinite(value):
            return None, "Falta marcador del primer tiempo"
        actual = "OVER" if value > 1.5 else "UNDER"
    elif market == "H1_CORNERS_OU45":
        value = _safe_float(observed.get("H1Corners"))
        if not np.isfinite(value):
            return None, "Falta conteo verificable de córners 1T"
        actual = "OVER" if value > 4.5 else "UNDER"
    elif market == "YELLOW_CARDS_OU45":
        value = _safe_float(observed.get("YellowCards"))
        if not np.isfinite(value):
            return None, "Falta conteo de tarjetas amarillas"
        actual = "OVER" if value > 4.5 else "UNDER"
    elif market == "HOME_SCORE_OU05":
        actual = "YES" if home_goals > 0 else "NO"
    elif market == "AWAY_SCORE_OU05":
        actual = "YES" if away_goals > 0 else "NO"
    else:
        return None, "Mercado no reconocido"
    return ("ACERTADO" if prediction == actual else "FALLADO"), actual


def resolve_pending(
    path: str | Path = HISTORY_FILE,
    lookback_days: int = 45,
    max_events: int = 140,
    now_utc: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Cierra predicciones pendientes usando marcadores y resúmenes ESPN."""
    history = load_history(path)
    stats: dict[str, Any] = {"cerrados": 0, "no_evaluables": 0, "eventos_consultados": 0, "errores": []}
    if history.empty or "EstadoResultado" not in history:
        return history, stats

    now = now_utc or pd.Timestamp.now(tz="UTC")
    now = pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    kickoff = pd.to_datetime(history.get("KickoffUTC"), utc=True, errors="coerce")
    pending_mask = history["EstadoResultado"].astype(str).eq("PENDIENTE")
    candidates = history[
        pending_mask
        & kickoff.notna()
        & (kickoff < now - pd.Timedelta(minutes=100))
        & (kickoff >= now - pd.Timedelta(days=int(lookback_days)))
    ].copy()
    if candidates.empty:
        return history, stats

    candidates["_date"] = pd.to_datetime(candidates["KickoffUTC"], utc=True).dt.tz_convert(base.TZ_PERU).dt.date
    event_cache: dict[tuple[str, str], dict[str, Any]] = {}
    for comp_key, group in candidates.groupby("CompKey"):
        info = base.COMPETICIONES.get(str(comp_key))
        if not info:
            stats["errores"].append(f"Competición no configurada: {comp_key}")
            continue
        start = pd.Timestamp(group["_date"].min())
        end = pd.Timestamp(group["_date"].max())
        try:
            events = base.eventos_scoreboard_espn(info["espn"], start, end)
        except Exception as exc:
            stats["errores"].append(f"{comp_key}: {exc}")
            continue
        for ev in events:
            parsed = _parse_event(ev)
            if parsed:
                event_cache[(str(comp_key), parsed["EventID"])] = {"event": ev, "result": parsed, "league": info["espn"]}

    event_groups = list(candidates.groupby(["CompKey", "EventID"], dropna=False))[: int(max_events)]
    for (comp_key, event_id), group in event_groups:
        key = (str(comp_key), str(event_id))
        payload = event_cache.get(key)
        if not payload:
            continue
        stats["eventos_consultados"] += 1
        observed = dict(payload["result"])
        need_detail = group["MercadoCodigo"].isin(
            ["H1_GOALS_OU15", "H1_CORNERS_OU45", "YELLOW_CARDS_OU45"]
        ).any()
        if need_detail:
            try:
                summary = base.resumen_evento_espn(payload["league"], observed["EventID"], cache_hours=0.1)
                detail = base.parse_summary_stats(summary, observed["HomeID"], observed["AwayID"])
                h1_home, h1_away = _safe_float(detail.get("HTHG")), _safe_float(detail.get("HTAG"))
                observed["H1Goals"] = h1_home + h1_away if np.isfinite(h1_home) and np.isfinite(h1_away) else np.nan
                yellow_home, yellow_away = _safe_float(detail.get("HY")), _safe_float(detail.get("AY"))
                observed["YellowCards"] = yellow_home + yellow_away if np.isfinite(yellow_home) and np.isfinite(yellow_away) else np.nan
                observed["H1Corners"] = _h1_corners_with_zero(summary, observed["HomeID"], observed["AwayID"])
            except Exception as exc:
                stats["errores"].append(f"Resumen {observed['EventID']}: {exc}")

        for index in group.index:
            status, actual = _grade(history.loc[index], observed)
            kickoff_value = pd.to_datetime(history.at[index, "KickoffUTC"], utc=True, errors="coerce")
            old_enough = pd.notna(kickoff_value) and kickoff_value < now - pd.Timedelta(hours=48)
            if status is None and not old_enough:
                continue
            if status is None:
                history.at[index, "EstadoResultado"] = "NO_EVALUABLE"
                history.at[index, "MotivoCierre"] = actual
                stats["no_evaluables"] += 1
            else:
                history.at[index, "EstadoResultado"] = status
                history.at[index, "ResultadoReal"] = actual
                history.at[index, "MotivoCierre"] = "Resultado oficial completado"
                stats["cerrados"] += 1
            history.at[index, "CerradoEnUTC"] = datetime.now(timezone.utc).isoformat()
            history.at[index, "FuenteResultado"] = "ESPN"
            history.at[index, "GolesLocal"] = observed.get("HomeGoals", np.nan)
            history.at[index, "GolesVisitante"] = observed.get("AwayGoals", np.nan)
            history.at[index, "Goles1T"] = observed.get("H1Goals", np.nan)
            history.at[index, "Corners1T"] = observed.get("H1Corners", np.nan)
            history.at[index, "TarjetasAmarillas"] = observed.get("YellowCards", np.nan)

    if stats["cerrados"] or stats["no_evaluables"]:
        _atomic_csv(history, path)
    return history, stats


def wilson_lower(successes: int, total: int, z: float = 1.959963984540054) -> float:
    if total <= 0:
        return np.nan
    p = successes / total
    z2 = z * z
    center = p + z2 / (2 * total)
    radius = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total))
    return max(0.0, (center - radius) / (1 + z2 / total))


def audit_summary(history: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    if history is None or history.empty:
        return {
            "total": 0,
            "pending": 0,
            "evaluated": 0,
            "green_evaluated": 0,
            "green_accuracy": np.nan,
            "green_lcb95": np.nan,
            "state": "SIN_DATOS",
            "message": "Aún no hay predicciones prospectivas congeladas.",
        }, pd.DataFrame()

    status = history.get("EstadoResultado", pd.Series("PENDIENTE", index=history.index)).astype(str)
    evaluated = history[status.isin(RESOLVED_STATES)].copy()
    pending = int(status.eq("PENDIENTE").sum())
    if evaluated.empty:
        return {
            "total": int(len(history)),
            "pending": pending,
            "evaluated": 0,
            "green_evaluated": 0,
            "green_accuracy": np.nan,
            "green_lcb95": np.nan,
            "state": "RECOLECTANDO",
            "message": "SIN RESULTADOS EVALUADOS: no se publica una tasa ficticia de 0%.",
        }, pd.DataFrame()

    evaluated["Correcto"] = evaluated["EstadoResultado"].eq("ACERTADO")
    evaluated["ErrorBrierSeleccion"] = (
        pd.to_numeric(evaluated["Probabilidad"], errors="coerce") - evaluated["Correcto"].astype(float)
    ) ** 2
    rows: list[dict[str, Any]] = []
    for (market, signal), group in evaluated.groupby(["MercadoCodigo", "SemaforoFinal"], dropna=False):
        n = int(len(group))
        hits = int(group["Correcto"].sum())
        rows.append(
            {
                "MercadoCodigo": market,
                "Semaforo": signal,
                "N": n,
                "Aciertos": hits,
                "TasaAcierto": hits / n,
                "LCB95": wilson_lower(hits, n),
                "BrierSeleccion": float(group["ErrorBrierSeleccion"].mean()),
            }
        )
    detail = pd.DataFrame(rows).sort_values(["Semaforo", "MercadoCodigo"]).reset_index(drop=True)

    green = evaluated[evaluated["SemaforoFinal"].astype(str).eq("VERDE")]
    green_n = int(len(green))
    green_hits = int(green["Correcto"].sum()) if green_n else 0
    green_accuracy = green_hits / green_n if green_n else np.nan
    green_lcb = wilson_lower(green_hits, green_n) if green_n else np.nan
    emitted = pd.to_datetime(evaluated.get("EmitidoEnUTC"), utc=True, errors="coerce")
    elapsed_days = int((emitted.max() - emitted.min()).total_seconds() // 86400) + 1 if emitted.notna().sum() >= 2 else 1
    green_market_counts = green.groupby("MercadoCodigo").size() if green_n else pd.Series(dtype=int)
    supported_markets = int((green_market_counts >= MIN_PER_MARKET).sum())

    certified = bool(
        green_n >= MIN_GREEN_CERTIFICATION
        and elapsed_days >= MIN_CALENDAR_DAYS
        and np.isfinite(green_accuracy)
        and green_accuracy >= 0.65
        and np.isfinite(green_lcb)
        and green_lcb >= 0.60
        and supported_markets >= MIN_MARKETS_WITH_SUPPORT
    )
    if certified:
        state = "CONSISTENCIA_PREDICTIVA"
        message = "Consistencia predictiva prospectiva alcanzada. No equivale a rentabilidad sin cuotas reales."
    elif green_n < MIN_GREEN_CERTIFICATION or elapsed_days < MIN_CALENDAR_DAYS:
        state = "RECOLECTANDO"
        message = f"Se requieren al menos {MIN_GREEN_CERTIFICATION} verdes resueltos y {MIN_CALENDAR_DAYS} días."
    else:
        state = "EN_OBSERVACION"
        message = "La evidencia acumulada todavía no supera la meta estadística de estabilidad."

    return {
        "total": int(len(history)),
        "pending": pending,
        "evaluated": int(len(evaluated)),
        "green_evaluated": green_n,
        "green_accuracy": green_accuracy,
        "green_lcb95": green_lcb,
        "elapsed_days": elapsed_days,
        "supported_markets": supported_markets,
        "state": state,
        "message": message,
    }, detail


def adaptive_safety_gate(markets: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Aplica un cortacircuito histórico sin promocionar señales."""
    if markets is None or markets.empty:
        return markets
    result = markets.copy()
    if "SemaforoModelo" not in result:
        result["SemaforoModelo"] = result.get("Semaforo", "ROJO")
    result["SemaforoFinal"] = result["SemaforoModelo"].astype(str)
    result["Semaforo"] = result["SemaforoFinal"]
    result["AjusteAuditoria"] = "SIN AJUSTE"

    resolved = pd.DataFrame()
    if history is not None and not history.empty and "EstadoResultado" in history:
        resolved = history[history["EstadoResultado"].astype(str).isin(RESOLVED_STATES)].copy()
        if not resolved.empty:
            resolved["Correcto"] = resolved["EstadoResultado"].eq("ACERTADO")

    for index, row in result.iterrows():
        original = str(row.get("SemaforoModelo", "ROJO"))
        passes = _as_bool(row.get("ModeloSuperaBase", False))
        if not passes or original == "ROJO":
            result.at[index, "SemaforoFinal"] = "ROJO"
            result.at[index, "Semaforo"] = "ROJO"
            result.at[index, "AjusteAuditoria"] = "BLOQUEADO: MODELO/COBERTURA NO SUPERA BASE"
            continue
        lineup_status = str(row.get("EstadoAlineacion", "NO_DISPONIBLE")).upper()
        rotation_risk = str(row.get("RiesgoRotacion", "")).upper()
        if original == "VERDE" and lineup_status != "CONFIRMADA":
            result.at[index, "SemaforoFinal"] = "AMARILLO"
            result.at[index, "Semaforo"] = "AMARILLO"
            result.at[index, "AjusteAuditoria"] = "ESPERAR ALINEACION CONFIRMADA"
            continue
        if original == "VERDE" and rotation_risk == "ALTO":
            result.at[index, "SemaforoFinal"] = "AMARILLO"
            result.at[index, "Semaforo"] = "AMARILLO"
            result.at[index, "AjusteAuditoria"] = "DEGRADADO: RIESGO DE ROTACION ALTO"
            continue
        if original != "VERDE" or resolved.empty:
            continue
        market_code = str(row.get("MercadoCodigo", ""))
        sample = resolved[
            (resolved["MercadoCodigo"].astype(str) == market_code)
            & (resolved["SemaforoFinal"].astype(str) == "VERDE")
        ].tail(120)
        if len(sample) < 60:
            continue
        hits = int(sample["Correcto"].sum())
        accuracy = hits / len(sample)
        lower = wilson_lower(hits, len(sample))
        if len(sample) >= 100 and accuracy < 0.48:
            new_signal = "ROJO"
        elif accuracy < 0.55 or lower < 0.45:
            new_signal = "AMARILLO"
        else:
            continue
        result.at[index, "SemaforoFinal"] = new_signal
        result.at[index, "Semaforo"] = new_signal
        result.at[index, "AjusteAuditoria"] = (
            f"DEGRADADO POR AUDITORIA: n={len(sample)}, acierto={accuracy:.1%}, LCB95={lower:.1%}"
        )

    result["MejorOpcion"] = False
    group_columns = [c for c in ["EventID", "KickoffUTC", "Local", "Visitante"] if c in result]
    if group_columns:
        for _, group in result.groupby(group_columns, dropna=False):
            candidates = group[group["SemaforoFinal"].eq("VERDE")]
            if candidates.empty:
                continue
            conservative = (
                pd.to_numeric(candidates["PConservadora"], errors="coerce").fillna(0)
                if "PConservadora" in candidates
                else pd.Series(0.0, index=candidates.index)
            )
            reliability = (
                pd.to_numeric(candidates["Fiabilidad"], errors="coerce").fillna(0)
                if "Fiabilidad" in candidates
                else pd.Series(0.0, index=candidates.index)
            )
            support = (
                pd.to_numeric(candidates["Soporte"], errors="coerce").fillna(0)
                if "Soporte" in candidates
                else pd.Series(0.0, index=candidates.index)
            )
            score = (
                0.45 * conservative
                + 0.35 * reliability
                + 0.20 * (support / 100).clip(upper=1)
            )
            result.at[score.idxmax(), "MejorOpcion"] = True
    return result
