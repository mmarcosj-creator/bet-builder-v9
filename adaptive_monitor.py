"""Control adaptativo trazable para Forecaster Futbol V10.4 Gatuno.

La ventana de siete dias es una alarma temprana, no una certificacion. Un
ajuste solo se activa despues de que el usuario elige APLICAR. Todos los
ajustes son temporales, reversibles y unidireccionales: pueden degradar VERDE
a AMARILLO, pero nunca promover una senal.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DATA_DIR = Path("app_data_v10")
POLICY_FILE = DATA_DIR / "politica_adaptativa.json"
PROPOSALS_FILE = DATA_DIR / "propuestas_ajuste.csv"
DECISIONS_FILE = DATA_DIR / "historial_ajustes.csv"

WINDOW_DAYS = 7
COMPARISON_DAYS = 28
MIN_RECENT_GREEN = 20
MIN_ACTIVE_DAYS = 4
MIN_PRIOR_GREEN = 30

MARKET_LABELS = {
    "RESULT_1X2": "Resultado 1X2",
    "H1_GOALS_OU15": "Goles 1.er tiempo",
    "H1_CORNERS_OU45": "Corners 1.er tiempo",
    "YELLOW_CARDS_OU45": "Tarjetas amarillas totales",
    "HOME_SCORE_OU05": "Gol del local",
    "AWAY_SCORE_OU05": "Gol del visitante",
}

# Pisos del motor original. La capa adaptativa solo puede endurecerlos.
BASE_GREEN_RULES = {
    "RESULT_1X2": {"probability": 0.49, "lcb": 0.40, "reliability": 0.67, "support": 70},
    "H1_GOALS_OU15": {"probability": 0.68, "lcb": 0.59, "reliability": 0.66, "support": 55},
    "H1_CORNERS_OU45": {"probability": 0.68, "lcb": 0.59, "reliability": 0.66, "support": 55},
    "YELLOW_CARDS_OU45": {"probability": 0.68, "lcb": 0.59, "reliability": 0.66, "support": 55},
    "HOME_SCORE_OU05": {"probability": 0.68, "lcb": 0.59, "reliability": 0.66, "support": 55},
    "AWAY_SCORE_OU05": {"probability": 0.68, "lcb": 0.59, "reliability": 0.66, "support": 55},
}

PROPOSAL_COLUMNS = [
    "ProposalID", "MercadoCodigo", "Mercado", "VentanaInicio", "VentanaFin",
    "N", "DiasActivos", "Aciertos", "TasaAcierto", "ProbMedia", "Brecha",
    "Brier", "Severidad", "AccionPropuesta", "Motivo", "Estado",
    "CreadoEnUTC", "DecididoEnUTC", "RevisarDespuesUTC",
]

DECISION_COLUMNS = [
    "DecisionID", "ProposalID", "MercadoCodigo", "Decision", "Modo",
    "PoliticaAntes", "PoliticaDespues", "Motivo", "DecididoEnUTC",
]


def _safe_float(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if np.isfinite(number) else default
    except Exception:
        return default


def _utc_now(value: Any = None) -> pd.Timestamp:
    stamp = pd.Timestamp.now(tz="UTC") if value is None else pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _atomic_csv(frame: pd.DataFrame, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    os.replace(temporary, target)


def _atomic_json(payload: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def market_code(row: pd.Series | dict[str, Any]) -> str:
    explicit = str(row.get("MercadoCodigo", "")).strip()
    if explicit and explicit.lower() != "nan":
        return explicit
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


def normalize_history(history: pd.DataFrame) -> pd.DataFrame:
    """Acepta tanto el historial de auditoria_v10 como el de gatuno_audit."""
    columns = [
        "MercadoCodigo", "Mercado", "Semaforo", "EstadoResultado",
        "Probabilidad", "FechaResultado", "Correcto", "Pronostico", "Competicion",
    ]
    if history is None or history.empty:
        return pd.DataFrame(columns=columns)
    frame = history.copy()
    frame["MercadoCodigo"] = frame.apply(market_code, axis=1)
    if "SemaforoFinal" in frame:
        fallback = frame["Semaforo"] if "Semaforo" in frame else "ROJO"
        frame["Semaforo"] = frame["SemaforoFinal"].fillna(fallback)
    elif "Semaforo" not in frame:
        frame["Semaforo"] = "ROJO"
    frame["FechaResultado"] = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]")
    for column in ("KickoffUTC", "CerradoEnUTC", "ResueltoEn", "Fecha"):
        if column in frame:
            parsed = pd.to_datetime(frame[column], utc=True, errors="coerce")
            frame["FechaResultado"] = frame["FechaResultado"].fillna(parsed)
    probability_source = frame["Probabilidad"] if "Probabilidad" in frame else pd.Series(np.nan, index=frame.index)
    status_source = frame["EstadoResultado"] if "EstadoResultado" in frame else pd.Series("PENDIENTE", index=frame.index)
    frame["Probabilidad"] = pd.to_numeric(probability_source, errors="coerce")
    frame["EstadoResultado"] = status_source.astype(str).str.upper()
    frame["Semaforo"] = frame["Semaforo"].astype(str).str.upper()
    frame = frame[frame["EstadoResultado"].isin(["ACERTADO", "FALLADO"])].copy()
    frame["Correcto"] = frame["EstadoResultado"].eq("ACERTADO").astype(int)
    for column in columns:
        if column not in frame:
            frame[column] = ""
    return frame[columns]


def _window_metrics(group: pd.DataFrame) -> dict[str, Any]:
    n = int(len(group))
    if n == 0:
        return {
            "N": 0, "Aciertos": 0, "TasaAcierto": np.nan, "ProbMedia": np.nan,
            "Brecha": np.nan, "Brier": np.nan, "ZCalibracion": np.nan,
            "DiasActivos": 0, "DiasDebiles": 0,
        }
    outcomes = pd.to_numeric(group["Correcto"], errors="coerce").fillna(0).to_numpy(float)
    probabilities = pd.to_numeric(group["Probabilidad"], errors="coerce").to_numpy(float)
    valid = np.isfinite(probabilities)
    mean_probability = float(np.mean(probabilities[valid])) if valid.any() else np.nan
    accuracy = float(np.mean(outcomes))
    gap = accuracy - mean_probability if np.isfinite(mean_probability) else np.nan
    brier = float(np.mean((probabilities[valid] - outcomes[valid]) ** 2)) if valid.any() else np.nan
    if valid.any():
        expected = float(np.sum(probabilities[valid]))
        variance = float(np.sum(probabilities[valid] * (1 - probabilities[valid])))
        z_score = (float(np.sum(outcomes[valid])) - expected) / math.sqrt(variance) if variance > 0 else np.nan
    else:
        z_score = np.nan
    dated = group.dropna(subset=["FechaResultado"]).copy()
    active_days = int(dated["FechaResultado"].dt.date.nunique()) if not dated.empty else 0
    weak_days = 0
    if not dated.empty:
        dated["Dia"] = dated["FechaResultado"].dt.date
        for _, day in dated.groupby("Dia"):
            if len(day) < 2:
                continue
            expected_day = pd.to_numeric(day["Probabilidad"], errors="coerce").mean()
            if np.isfinite(expected_day) and float(day["Correcto"].mean()) <= expected_day - 0.10:
                weak_days += 1
    return {
        "N": n,
        "Aciertos": int(np.sum(outcomes)),
        "TasaAcierto": accuracy,
        "ProbMedia": mean_probability,
        "Brecha": gap,
        "Brier": brier,
        "ZCalibracion": z_score,
        "DiasActivos": active_days,
        "DiasDebiles": weak_days,
    }


def _worst_pattern(group: pd.DataFrame, column: str, minimum: int = 5) -> str:
    if group.empty or column not in group:
        return "SIN PATRON CONCLUYENTE"
    candidates: list[tuple[float, str]] = []
    for value, segment in group.groupby(column, dropna=False):
        if len(segment) < minimum:
            continue
        metrics = _window_metrics(segment)
        gap = metrics["Brecha"]
        if not np.isfinite(gap):
            continue
        label = (
            f"{value}: {metrics['Aciertos']}/{metrics['N']} aciertos, "
            f"brecha {gap:+.0%}"
        )
        candidates.append((float(gap), label))
    return min(candidates, key=lambda item: item[0])[1] if candidates else "SIN PATRON CONCLUYENTE"


def analyze_markets(
    history: pd.DataFrame,
    now: Any = None,
    window_days: int = WINDOW_DAYS,
    comparison_days: int = COMPARISON_DAYS,
) -> pd.DataFrame:
    """Diagnostica cada mercado verde con cuatro senales independientes."""
    columns = [
        "MercadoCodigo", "Mercado", "Estado", "N", "DiasActivos", "DiasDebiles",
        "Aciertos", "TasaAcierto", "ProbMedia", "Brecha", "Brier", "ZCalibracion",
        "NPrevio", "TasaPrevia", "BrierPrevio", "SenalesFallo", "AccionPropuesta",
        "PatronPronostico", "PatronCompeticion", "Motivo", "VentanaInicio", "VentanaFin",
    ]
    frame = normalize_history(history)
    if frame.empty:
        return pd.DataFrame(columns=columns)
    reference = _utc_now(now)
    recent_start = reference - pd.Timedelta(days=int(window_days))
    previous_start = recent_start - pd.Timedelta(days=int(comparison_days))
    recent_all = frame[
        frame["FechaResultado"].notna()
        & frame["FechaResultado"].between(recent_start, reference, inclusive="both")
    ]
    previous_all = frame[
        frame["FechaResultado"].notna()
        & frame["FechaResultado"].between(previous_start, recent_start, inclusive="left")
    ]
    codes = sorted(set(frame["MercadoCodigo"].astype(str)) - {"UNKNOWN"})
    rows: list[dict[str, Any]] = []
    for code in codes:
        recent = recent_all[(recent_all["MercadoCodigo"] == code) & recent_all["Semaforo"].eq("VERDE")]
        previous = previous_all[(previous_all["MercadoCodigo"] == code) & previous_all["Semaforo"].eq("VERDE")]
        current = _window_metrics(recent)
        prior = _window_metrics(previous)
        prediction_pattern = _worst_pattern(recent, "Pronostico")
        competition_pattern = _worst_pattern(recent, "Competicion")
        enough = current["N"] >= MIN_RECENT_GREEN and current["DiasActivos"] >= MIN_ACTIVE_DAYS
        failed_calibration = bool(
            enough and np.isfinite(current["Brecha"]) and current["Brecha"] <= -0.12
            and np.isfinite(current["ZCalibracion"]) and current["ZCalibracion"] <= -1.64
        )
        persistent = bool(enough and current["DiasDebiles"] >= 3)
        bad_brier = bool(
            enough and np.isfinite(current["Brier"]) and current["Brier"] >= 0.25
            and (not np.isfinite(prior["Brier"]) or current["Brier"] >= prior["Brier"] + 0.04)
        )
        drift = bool(
            enough and prior["N"] >= MIN_PRIOR_GREEN and np.isfinite(prior["TasaAcierto"])
            and current["TasaAcierto"] <= prior["TasaAcierto"] - 0.12
        )
        signals = sum([failed_calibration, persistent, bad_brier, drift])
        critical = bool(
            current["N"] >= 30
            and (
                (np.isfinite(current["Brecha"]) and current["Brecha"] <= -0.18
                 and np.isfinite(current["ZCalibracion"]) and current["ZCalibracion"] <= -2.0)
                or (current["TasaAcierto"] < 0.45 and np.isfinite(current["ProbMedia"])
                    and current["ProbMedia"] >= 0.65)
            )
        )
        if not enough:
            state, action = "SIN_MUESTRA", "SEGUIR_RECOLECTANDO"
            reason = f"Faltan datos: {current['N']}/{MIN_RECENT_GREEN} verdes y {current['DiasActivos']}/{MIN_ACTIVE_DAYS} dias."
        elif critical:
            state, action = "CRITICA", "PAUSAR_VERDES_7_DIAS"
            reason = f"Deterioro fuerte. Patron principal: {prediction_pattern}."
        elif signals >= 2:
            state, action = "ALERTA", "ENDURECER_VERDE"
            reason = f"Coinciden {signals} senales de deterioro. Patron principal: {prediction_pattern}."
        elif signals == 1 or (np.isfinite(current["Brecha"]) and current["Brecha"] < -0.08):
            state, action = "OBSERVAR", "OBSERVAR_7_DIAS"
            reason = "Hay una senal temprana, pero no evidencia suficiente para ajustar."
        else:
            state, action = "ESTABLE", "SIN_CAMBIO"
            reason = "No hay deterioro consistente en la ventana reciente."
        rows.append({
            "MercadoCodigo": code,
            "Mercado": MARKET_LABELS.get(code, code),
            "Estado": state,
            **current,
            "NPrevio": prior["N"],
            "TasaPrevia": prior["TasaAcierto"],
            "BrierPrevio": prior["Brier"],
            "SenalesFallo": int(signals),
            "AccionPropuesta": action,
            "PatronPronostico": prediction_pattern,
            "PatronCompeticion": competition_pattern,
            "Motivo": reason,
            "VentanaInicio": recent_start.isoformat(),
            "VentanaFin": reference.isoformat(),
        })
    return pd.DataFrame(rows, columns=columns)


def _load_csv(path: str | Path, columns: list[str]) -> pd.DataFrame:
    target = Path(path)
    if not target.exists():
        return pd.DataFrame(columns=columns)
    try:
        frame = pd.read_csv(target)
    except Exception:
        return pd.DataFrame(columns=columns)
    for column in columns:
        if column not in frame:
            frame[column] = np.nan
    return frame[columns]


def load_proposals(path: str | Path = PROPOSALS_FILE) -> pd.DataFrame:
    frame = _load_csv(path, PROPOSAL_COLUMNS)
    for column in (
        "ProposalID", "MercadoCodigo", "Mercado", "VentanaInicio", "VentanaFin",
        "Severidad", "AccionPropuesta", "Motivo", "Estado", "CreadoEnUTC",
        "DecididoEnUTC", "RevisarDespuesUTC",
    ):
        frame[column] = frame[column].fillna("").astype(str)
    return frame


def _proposal_id(row: pd.Series) -> str:
    day = pd.Timestamp(row["VentanaFin"]).date().isoformat()
    material = f"{row['MercadoCodigo']}|{day}|{row['AccionPropuesta']}"
    return hashlib.sha256(material.encode()).hexdigest()[:18]


def update_proposals(
    history: pd.DataFrame,
    proposals_path: str | Path = PROPOSALS_FILE,
    policy_path: str | Path = POLICY_FILE,
    now: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    reference = _utc_now(now)
    diagnostics = analyze_markets(history, now=reference)
    proposals = load_proposals(proposals_path)
    policy = load_policy(policy_path)
    existing = set(proposals["ProposalID"].astype(str))
    additions: list[dict[str, Any]] = []
    for _, row in diagnostics.iterrows():
        if row["Estado"] not in {"ALERTA", "CRITICA"}:
            continue
        active_rule = policy.get("markets", {}).get(str(row["MercadoCodigo"]), {})
        active_until = pd.to_datetime(active_rule.get("expires_at"), utc=True, errors="coerce")
        if pd.notna(active_until) and reference < active_until:
            continue
        proposal_id = _proposal_id(row)
        if proposal_id in existing:
            continue
        same = proposals[proposals["MercadoCodigo"].astype(str).eq(str(row["MercadoCodigo"]))]
        if same["Estado"].astype(str).eq("PENDIENTE").any():
            continue
        observing = same[same["Estado"].astype(str).eq("OBSERVANDO")]
        if not observing.empty:
            revisit = pd.to_datetime(observing["RevisarDespuesUTC"], utc=True, errors="coerce").max()
            if pd.notna(revisit) and reference < revisit:
                continue
        additions.append({
            "ProposalID": proposal_id,
            "MercadoCodigo": row["MercadoCodigo"], "Mercado": row["Mercado"],
            "VentanaInicio": row["VentanaInicio"], "VentanaFin": row["VentanaFin"],
            "N": row["N"], "DiasActivos": row["DiasActivos"], "Aciertos": row["Aciertos"],
            "TasaAcierto": row["TasaAcierto"], "ProbMedia": row["ProbMedia"],
            "Brecha": row["Brecha"], "Brier": row["Brier"], "Severidad": row["Estado"],
            "AccionPropuesta": row["AccionPropuesta"], "Motivo": row["Motivo"],
            "Estado": "PENDIENTE", "CreadoEnUTC": reference.isoformat(),
            "DecididoEnUTC": "", "RevisarDespuesUTC": "",
        })
        existing.add(proposal_id)
    if additions:
        additions_frame = pd.DataFrame(additions, columns=PROPOSAL_COLUMNS)
        proposals = additions_frame if proposals.empty else pd.concat([proposals, additions_frame], ignore_index=True)
        _atomic_csv(proposals[PROPOSAL_COLUMNS], proposals_path)
    return diagnostics, proposals


def load_policy(path: str | Path = POLICY_FILE) -> dict[str, Any]:
    default = {"schema_version": 1, "updated_at": "", "markets": {}}
    target = Path(path)
    if not target.exists():
        return default
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return {**default, **payload} if isinstance(payload.get("markets", {}), dict) else default
    except Exception:
        return default


def decide_proposal(
    proposal_id: str,
    decision: str,
    proposals_path: str | Path = PROPOSALS_FILE,
    policy_path: str | Path = POLICY_FILE,
    decisions_path: str | Path = DECISIONS_FILE,
    now: Any = None,
) -> dict[str, Any]:
    """Confirma el ajuste o posterga la decision siete dias."""
    reference = _utc_now(now)
    decision = str(decision).upper()
    if decision not in {"APLICAR", "OBSERVAR_7_DIAS"}:
        raise ValueError("Decision no valida")
    proposals = load_proposals(proposals_path)
    matches = proposals.index[proposals["ProposalID"].astype(str).eq(str(proposal_id))]
    if len(matches) != 1:
        raise ValueError("Propuesta no encontrada")
    index = matches[0]
    proposal = proposals.loc[index]
    if str(proposal["Estado"]) != "PENDIENTE":
        raise ValueError("La propuesta ya fue decidida")
    policy = load_policy(policy_path)
    code = str(proposal["MercadoCodigo"])
    before = dict(policy.get("markets", {}).get(code, {}))
    after = before
    mode = "OBSERVACION"
    if decision == "OBSERVAR_7_DIAS":
        proposals.at[index, "Estado"] = "OBSERVANDO"
        proposals.at[index, "RevisarDespuesUTC"] = (reference + pd.Timedelta(days=7)).isoformat()
    else:
        base = BASE_GREEN_RULES.get(code, BASE_GREEN_RULES["H1_GOALS_OU15"])
        if str(proposal["AccionPropuesta"]) == "PAUSAR_VERDES_7_DIAS":
            mode = "PAUSA"
            after = {
                "mode": mode, "expires_at": (reference + pd.Timedelta(days=7)).isoformat(),
                "proposal_id": proposal_id, "applied_at": reference.isoformat(),
                "reason": str(proposal["Motivo"]),
            }
        else:
            mode = "ENDURECER"
            gap = abs(min(0.0, _safe_float(proposal["Brecha"], -0.12)))
            probability_delta = float(np.clip(gap / 4, 0.02, 0.05))
            after = {
                "mode": mode,
                "min_probability": min(0.90, base["probability"] + probability_delta),
                "min_lcb": min(0.85, base["lcb"] + 0.03),
                "min_reliability": min(0.90, base["reliability"] + 0.03),
                "min_support": int(base["support"] + 10),
                "expires_at": (reference + pd.Timedelta(days=14)).isoformat(),
                "proposal_id": proposal_id, "applied_at": reference.isoformat(),
                "reason": str(proposal["Motivo"]),
            }
        policy.setdefault("markets", {})[code] = after
        policy["updated_at"] = reference.isoformat()
        _atomic_json(policy, policy_path)
        proposals.at[index, "Estado"] = "APLICADO"
    proposals.at[index, "DecididoEnUTC"] = reference.isoformat()
    _atomic_csv(proposals[PROPOSAL_COLUMNS], proposals_path)

    decisions = _load_csv(decisions_path, DECISION_COLUMNS)
    material = f"{proposal_id}|{decision}|{reference.isoformat()}"
    record = {
        "DecisionID": hashlib.sha256(material.encode()).hexdigest()[:18],
        "ProposalID": proposal_id, "MercadoCodigo": code, "Decision": decision, "Modo": mode,
        "PoliticaAntes": json.dumps(before, ensure_ascii=False, sort_keys=True),
        "PoliticaDespues": json.dumps(after, ensure_ascii=False, sort_keys=True),
        "Motivo": str(proposal["Motivo"]), "DecididoEnUTC": reference.isoformat(),
    }
    record_frame = pd.DataFrame([record], columns=DECISION_COLUMNS)
    decisions = record_frame if decisions.empty else pd.concat([decisions, record_frame], ignore_index=True)
    _atomic_csv(decisions[DECISION_COLUMNS], decisions_path)
    return after


def revert_market(
    code: str,
    policy_path: str | Path = POLICY_FILE,
    decisions_path: str | Path = DECISIONS_FILE,
    now: Any = None,
) -> None:
    reference = _utc_now(now)
    policy = load_policy(policy_path)
    before = dict(policy.get("markets", {}).get(code, {}))
    policy.setdefault("markets", {}).pop(code, None)
    policy["updated_at"] = reference.isoformat()
    _atomic_json(policy, policy_path)
    decisions = _load_csv(decisions_path, DECISION_COLUMNS)
    material = f"rollback|{code}|{reference.isoformat()}"
    record = {
        "DecisionID": hashlib.sha256(material.encode()).hexdigest()[:18],
        "ProposalID": before.get("proposal_id", ""), "MercadoCodigo": code,
        "Decision": "REVERTIR", "Modo": "SIN_AJUSTE",
        "PoliticaAntes": json.dumps(before, ensure_ascii=False, sort_keys=True),
        "PoliticaDespues": "{}", "Motivo": "Reversion manual",
        "DecididoEnUTC": reference.isoformat(),
    }
    record_frame = pd.DataFrame([record], columns=DECISION_COLUMNS)
    decisions = record_frame if decisions.empty else pd.concat([decisions, record_frame], ignore_index=True)
    _atomic_csv(decisions[DECISION_COLUMNS], decisions_path)


def _recompute_best(markets: pd.DataFrame) -> pd.DataFrame:
    result = markets.copy()
    result["MejorOpcion"] = False
    keys = [name for name in ("EventID", "KickoffUTC", "Local", "Visitante") if name in result]
    if not keys:
        return result
    for _, group in result.groupby(keys, dropna=False):
        candidates = group[group["SemaforoFinal"].astype(str).eq("VERDE")]
        if candidates.empty:
            continue
        def numeric_column(name: str) -> pd.Series:
            source = candidates[name] if name in candidates else pd.Series(0.0, index=candidates.index)
            return pd.to_numeric(source, errors="coerce").fillna(0)

        conservative = numeric_column("PConservadora")
        reliability = numeric_column("Fiabilidad")
        support = numeric_column("Soporte")
        score = 0.45 * conservative + 0.35 * reliability + 0.20 * (support / 100).clip(upper=1)
        result.at[score.idxmax(), "MejorOpcion"] = True
    return result


def apply_policy(
    markets: pd.DataFrame,
    policy: dict[str, Any] | None = None,
    now: Any = None,
) -> pd.DataFrame:
    """Aplica ajustes confirmados; nunca cambia amarillo/rojo a verde."""
    if markets is None or markets.empty:
        return markets
    reference = _utc_now(now)
    policy = policy or load_policy()
    result = markets.copy()
    if "SemaforoFinal" not in result:
        result["SemaforoFinal"] = result.get("Semaforo", "ROJO")
    if "SemaforoPreAdaptativo" not in result:
        result["SemaforoPreAdaptativo"] = result["SemaforoFinal"]
    if "AjusteAdaptativo" not in result:
        result["AjusteAdaptativo"] = "SIN AJUSTE"
    for index, row in result.iterrows():
        if str(row.get("SemaforoFinal", "ROJO")).upper() != "VERDE":
            continue
        rule = policy.get("markets", {}).get(market_code(row))
        if not isinstance(rule, dict):
            continue
        expires = pd.to_datetime(rule.get("expires_at"), utc=True, errors="coerce")
        if pd.notna(expires) and reference >= expires:
            continue
        mode = str(rule.get("mode", "")).upper()
        degrade = mode == "PAUSA"
        if mode == "ENDURECER":
            checks = [
                _safe_float(row.get("Probabilidad")) >= _safe_float(rule.get("min_probability"), 1),
                _safe_float(row.get("PConservadora")) >= _safe_float(rule.get("min_lcb"), 1),
                _safe_float(row.get("Fiabilidad")) >= _safe_float(rule.get("min_reliability"), 1),
                _safe_float(row.get("Soporte"), 0) >= _safe_float(rule.get("min_support"), 9999),
            ]
            degrade = not all(checks)
        if degrade:
            result.at[index, "SemaforoFinal"] = "AMARILLO"
            result.at[index, "Semaforo"] = "AMARILLO"
            result.at[index, "AjusteAdaptativo"] = (
                "🐾 PAUSA PREVENTIVA CONFIRMADA" if mode == "PAUSA"
                else "🐾 VERDE ENDURECIDO POR AUDITORIA"
            )
    return _recompute_best(result)


def active_policy_rows(policy: dict[str, Any] | None = None, now: Any = None) -> pd.DataFrame:
    policy = policy or load_policy()
    reference = _utc_now(now)
    rows = []
    for code, rule in policy.get("markets", {}).items():
        expires = pd.to_datetime(rule.get("expires_at"), utc=True, errors="coerce")
        if pd.notna(expires) and expires <= reference:
            continue
        rows.append({
            "MercadoCodigo": code, "Mercado": MARKET_LABELS.get(code, code),
            "Modo": rule.get("mode", ""), "Vence": rule.get("expires_at", ""),
            "Motivo": rule.get("reason", ""),
        })
    return pd.DataFrame(rows)
