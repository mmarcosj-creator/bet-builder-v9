"""Contexto competitivo y control de rotacion para Bet Builder V9.3.

La capa es deliberadamente conservadora: una competicion prestigiosa no
implica por si sola que juegue el once principal. Se combinan fase, descanso,
carga, siguiente compromiso y estado de la alineacion. Los datos ausentes
reducen confianza; nunca se convierten en una supuesta confirmacion.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd


CONTEXT_VERSION = "V9.3-CONTEXT-ROTATION"

# Mercados cuyo resultado cambia especialmente cuando faltan atacantes,
# extremos/laterales o cambia de forma amplia el once.
ROTATION_SENSITIVE = {
    "FAV_WIN",
    "FAV_MINUS15",
    "FAV_GOALS2",
    "FAV_C5",
    "FAV_C6",
    "FAV_C8",
    "H1_GOAL",
    "H1_FAV_PLUS05",
    "H1_GOALS_1_2",
    "H1_CORNERS_3",
}

# Estos nichos quedan en laboratorio después de la auditoria V9.2.
SUSPENDED_TEMPLATES = {
    "BTTS_CONTROL",
    "RANGO_CORNER_CONTROL",
    "EMPATE_CERRADO",
    "EMPATE_CORNER_BAJO",
    "DOMINIO_SIN_GOLEADA",
    "CORNER_ALTO_GOL_BAJO",
    "FAV_CORNER_BTTS",
}

EXPERIMENTAL_CODES = {
    "H1_CORNERS_3",
    "FAV_C4_7",
    "TOTAL_C_7_12",
    "H1_GOALS_1_2",
}


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.lower()).strip()


def extract_stage_text(event, competition=None):
    """Extrae texto de fase/ronda de estructuras ESPN cambiantes."""
    competition = competition or {}
    values = []

    def add(value):
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, (int, float)) and not pd.isna(value):
            values.append(str(value))

    for obj in (event or {}, competition or {}):
        if not isinstance(obj, dict):
            continue
        for key in (
            "name", "shortName", "abbreviation", "description", "detail",
            "shortDetail", "headline", "phase", "stage", "round", "leg",
            "type", "seasonType",
        ):
            value = obj.get(key)
            if isinstance(value, dict):
                for sub in ("name", "text", "description", "detail", "type"):
                    add(value.get(sub))
            else:
                add(value)

    for note in competition.get("notes") or []:
        if isinstance(note, dict):
            add(note.get("headline"))
            add(note.get("text"))
            add(note.get("type"))
        else:
            add(note)

    status = (event.get("status") or {}).get("type") or {}
    add(status.get("detail"))
    add(status.get("shortDetail"))

    # Mantiene el orden, elimina duplicados.
    return " | ".join(dict.fromkeys(values))


def stage_profile(comp_key, comp_type, stage_text):
    """Puntua importancia observada; no confunde torneo con alineacion."""
    text = _norm(stage_text)
    base = {
        "UCL": 78,
        "LIB": 80,
        "UEL": 75,
        "SUD": 76,
        "CDB": 70,
    }.get(str(comp_key), 65 if str(comp_type).upper() == "LIGA" else 60)

    stage = "NO_IDENTIFICADA"
    knockout = False
    score = base

    if re.search(r"semi|semifinal", text):
        stage, score, knockout = "SEMIFINAL", 94, True
    elif re.search(r"quarter|cuartos|cuarto de final", text):
        stage, score, knockout = "CUARTOS", 90, True
    elif re.search(r"round of 16|octavos|r16|last 16", text):
        stage, score, knockout = "OCTAVOS", 86, True
    elif re.search(r"\b(final|finals)\b", text):
        stage, score, knockout = "FINAL", 100, True
    elif re.search(r"play[ -]?off|knockout|eliminator", text):
        stage, score, knockout = "ELIMINATORIA", 84, True
    elif re.search(r"group|grupo|league phase|fase liga", text):
        stage, score = "GRUPOS_LIGA", max(base, 76)
    elif re.search(r"qualif|clasific|prelim", text):
        stage, score = "CLASIFICACION", 72
    elif str(comp_type).upper() == "LIGA":
        stage, score = "LIGA", 65
    elif str(comp_key) == "CDB":
        stage, score = "COPA_NO_IDENTIFICADA", 62

    second_leg = bool(re.search(r"second leg|2nd leg|vuelta|leg 2", text))
    if second_leg and knockout:
        score = min(100, score + 2)

    return {
        "stage": stage,
        "importance": int(score),
        "knockout": knockout,
        "second_leg": second_leg,
        "identified": stage != "NO_IDENTIFICADA",
    }


def parse_confirmed_lineups(summary, home_id="", away_id=""):
    """Lee titulares ESPN cuando existen; no inventa continuidad."""
    out = {
        "status": "NO_DISPONIBLE",
        "home_starters": [],
        "away_starters": [],
        "home_count": 0,
        "away_count": 0,
    }
    rosters = (summary or {}).get("rosters") or []
    for block in rosters:
        team = block.get("team") or {}
        team_id = str(team.get("id") or block.get("teamId") or "")
        side = str(block.get("homeAway") or "").lower()
        starters = []
        for item in block.get("roster") or block.get("athletes") or []:
            athlete = item.get("athlete") or item
            if not bool(item.get("starter") or item.get("isStarter")):
                continue
            name = athlete.get("displayName") or athlete.get("fullName")
            if name:
                starters.append(str(name))
        if team_id == str(home_id) or side == "home":
            out["home_starters"] = starters
        elif team_id == str(away_id) or side == "away":
            out["away_starters"] = starters

    out["home_count"] = len(out["home_starters"])
    out["away_count"] = len(out["away_starters"])
    if out["home_count"] >= 10 and out["away_count"] >= 10:
        out["status"] = "CONFIRMADA"
    elif out["home_count"] or out["away_count"]:
        out["status"] = "PARCIAL"
    return out


def load_lineup_history(path):
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def archive_confirmed_lineups(path, fixture, lineup):
    """Guarda observaciones prospectivas; nunca reescribe el pasado."""
    if lineup.get("status") != "CONFIRMADA":
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    history = load_lineup_history(path)
    event_id = str(fixture.get("EventID", ""))
    date = str(pd.Timestamp(fixture.get("Date")).date())
    additions = [
        {
            "event_id": event_id,
            "date": date,
            "team": str(fixture.get("HomeOriginal", fixture.get("HomeTeam", ""))),
            "starters": list(lineup.get("home_starters") or []),
        },
        {
            "event_id": event_id,
            "date": date,
            "team": str(fixture.get("AwayOriginal", fixture.get("AwayTeam", ""))),
            "starters": list(lineup.get("away_starters") or []),
        },
    ]
    keys = {(str(x.get("event_id", "")), _norm(x.get("team", ""))) for x in history}
    changed = False
    for row in additions:
        key = (row["event_id"], _norm(row["team"]))
        if key not in keys and len(row["starters"]) >= 10:
            history.append(row)
            keys.add(key)
            changed = True
    if changed:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def lineup_strength_profile(history, team, starters, date, current_event_id=""):
    """Compara el XI con la alineacion modal de hasta cinco partidos previos."""
    target = pd.Timestamp(date)
    eligible = []
    for row in history or []:
        if _norm(row.get("team")) != _norm(team):
            continue
        if str(row.get("event_id", "")) == str(current_event_id):
            continue
        d = pd.to_datetime(row.get("date"), errors="coerce")
        if pd.isna(d) or pd.Timestamp(d) >= target:
            continue
        names = [_norm(x) for x in row.get("starters") or [] if _norm(x)]
        if len(names) >= 10:
            eligible.append((pd.Timestamp(d), names))
    eligible.sort(key=lambda x: x[0], reverse=True)
    eligible = eligible[:5]

    result = {
        "status": "SIN_BASELINE",
        "baseline_matches": len(eligible),
        "continuity": np.nan,
        "key_coverage": np.nan,
        "changes": np.nan,
    }
    current = {_norm(x) for x in starters or [] if _norm(x)}
    if len(eligible) < 3 or len(current) < 10:
        return result

    counts = defaultdict(int)
    for _, names in eligible:
        for name in set(names):
            counts[name] += 1
    ordered = sorted(counts, key=lambda name: (-counts[name], name))
    reference = set(ordered[:11])
    key_players = set(ordered[:5])
    overlap = len(current & reference)
    continuity = overlap / max(1, len(reference))
    key_coverage = len(current & key_players) / max(1, len(key_players))

    if continuity < 0.64 or key_coverage < 0.60:
        status = "ROTACION_ALTA"
    elif continuity < 0.82 or key_coverage < 0.80:
        status = "ROTACION_MEDIA"
    else:
        status = "ONCE_HABITUAL"

    result.update({
        "status": status,
        "continuity": float(continuity),
        "key_coverage": float(key_coverage),
        "changes": int(max(0, 11 - overlap)),
    })
    return result


def exact_selection_signature(codes):
    """Firma estable para impedir cotizar una combinacion distinta."""
    clean = [str(code).strip().upper() for code in codes if str(code).strip()]
    payload = "|".join(clean)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def build_calendar_index(history, fixtures):
    """Indice pasado+futuro para detectar el siguiente compromiso."""
    index = defaultdict(list)

    def add(team, row, source):
        if not team:
            return
        profile = stage_profile(
            row.get("CompKey", ""),
            row.get("TipoCompeticion", ""),
            row.get("StageText", ""),
        )
        index[_norm(team)].append({
            "date": pd.Timestamp(row.get("Date")),
            "comp_key": str(row.get("CompKey", "")),
            "competition": str(row.get("Competicion", row.get("CompKey", ""))),
            "event_id": str(row.get("EventID", "")),
            "importance": profile["importance"],
            "stage": profile["stage"],
            "source": source,
        })

    if history is not None:
        for _, row in history.iterrows():
            add(row.get("HomeTeam"), row, "HISTORICO")
            add(row.get("AwayTeam"), row, "HISTORICO")
    if fixtures is not None:
        for _, row in fixtures.iterrows():
            add(row.get("HomeOriginal", row.get("HomeTeam")), row, "CALENDARIO")
            add(row.get("AwayOriginal", row.get("AwayTeam")), row, "CALENDARIO")

    for team in index:
        index[team].sort(key=lambda x: (x["date"], x["event_id"]))
    return index


def next_match(calendar_index, team, date, current_event_id=""):
    target = pd.Timestamp(date)
    future = []
    for event in calendar_index.get(_norm(team), []):
        if event["date"] <= target:
            continue
        if current_event_id and event["event_id"] == str(current_event_id):
            continue
        future.append(event)
    if not future:
        return None
    event = min(future, key=lambda x: x["date"])
    result = dict(event)
    result["days"] = int((event["date"] - target).days)
    return result


def _team_rotation_score(load, next_event, current_importance, current_knockout):
    score = 0
    reasons = []
    rest = load.get("DaysRest", np.nan)
    m7 = int(load.get("Matches7", 0) or 0)
    m14 = int(load.get("Matches14", 0) or 0)

    if pd.notna(rest) and rest <= 3:
        score += 20
        reasons.append(f"descanso {rest:.0f}d")
    if m7 >= 2:
        score += 10
        reasons.append(f"{m7} partidos/7d")
    if m14 >= 4:
        score += 15
        reasons.append(f"{m14} partidos/14d")

    if next_event and next_event["days"] <= 4:
        gap = next_event["importance"] - current_importance
        score += 12
        reasons.append(
            f"siguiente en {next_event['days']}d ({next_event['competition']})"
        )
        if gap >= 10:
            score += min(25, 10 + gap // 2)
            reasons.append(f"siguiente +{gap} importancia")

    if current_knockout and current_importance >= 84:
        score -= 12
        reasons.append("eliminatoria prioritaria")

    phase = str(load.get("Phase", ""))
    if phase == "COLD_START":
        score += 10
        reasons.append("temporada con muestra minima")
    elif phase == "EARLY":
        score += 5
        reasons.append("temporada temprana")

    return max(0, int(score)), reasons


def evaluate_fixture_context(
    fixture,
    home_team,
    away_team,
    home_load,
    away_load,
    fav_type,
    calendar_index,
    lineup_status="NO_DISPONIBLE",
    lineup_home=None,
    lineup_away=None,
):
    profile = stage_profile(
        fixture.get("CompKey", ""),
        fixture.get("TipoCompeticion", ""),
        fixture.get("StageText", ""),
    )
    event_id = str(fixture.get("EventID", ""))
    nh = next_match(calendar_index, fixture.get("HomeOriginal", home_team), fixture["Date"], event_id)
    na = next_match(calendar_index, fixture.get("AwayOriginal", away_team), fixture["Date"], event_id)

    hs, hr = _team_rotation_score(home_load, nh, profile["importance"], profile["knockout"])
    aws, ar = _team_rotation_score(away_load, na, profile["importance"], profile["knockout"])

    lineup_home = lineup_home or {"status": "SIN_BASELINE", "baseline_matches": 0}
    lineup_away = lineup_away or {"status": "SIN_BASELINE", "baseline_matches": 0}
    for side, lineup_profile in (("home", lineup_home), ("away", lineup_away)):
        extra = 0
        if lineup_profile.get("status") == "ROTACION_ALTA":
            extra = 40
        elif lineup_profile.get("status") == "ROTACION_MEDIA":
            extra = 20
        if side == "home":
            hs += extra
            if extra:
                hr.append(f"once local: {lineup_profile['status'].lower()}")
        else:
            aws += extra
            if extra:
                ar.append(f"once visita: {lineup_profile['status'].lower()}")

    fav_score = hs if fav_type == "HOME" else aws
    max_score = max(hs, aws)

    if max_score >= 45:
        risk, factor = "ALTO", 0.78
    elif max_score >= 25:
        risk, factor = "MEDIO", 0.90
    else:
        risk, factor = "BAJO", 0.98

    if not profile["identified"]:
        factor *= 0.95
    if lineup_status == "CONFIRMADA":
        factor = min(1.0, factor + 0.04)
    elif lineup_status == "PARCIAL":
        factor *= 0.97
    else:
        factor *= 0.94

    return {
        "stage": profile["stage"],
        "importance": profile["importance"],
        "knockout": profile["knockout"],
        "rotation_risk": risk,
        "rotation_score_home": hs,
        "rotation_score_away": aws,
        "rotation_score_fav": fav_score,
        "context_factor": float(np.clip(factor, 0.65, 1.0)),
        "lineup_status": lineup_status,
        "lineup_home": lineup_home,
        "lineup_away": lineup_away,
        "next_home": nh,
        "next_away": na,
        "note": "; ".join(dict.fromkeys(hr + ar)) or "sin alerta fuerte de calendario",
    }


def candidate_guard(template_name, legs, context):
    sensitive = len(set(legs) & ROTATION_SENSITIVE)
    experimental = bool(set(legs) & EXPERIMENTAL_CODES)
    reasons = []
    blocked = False

    if template_name in SUSPENDED_TEMPLATES:
        blocked = True
        reasons.append("plantilla suspendida por auditoria")
    if len(legs) > 3 or sum(2 if code in {"FAV_C4_7", "TOTAL_C_7_12", "H1_GOALS_1_2"} else 1 for code in legs) > 3:
        blocked = True
        reasons.append("mas de 3 selecciones reales")
    if context["rotation_risk"] == "ALTO" and sensitive:
        blocked = True
        reasons.append("mercado sensible con rotacion alta")
    elif context["rotation_risk"] == "MEDIO" and sensitive >= 2:
        blocked = True
        reasons.append("dos mercados sensibles con rotacion media")
    if experimental:
        reasons.append("mercado experimental")

    return {
        "blocked": blocked,
        "sensitive_legs": sensitive,
        "experimental": experimental,
        "reason": "; ".join(reasons),
    }


def priority_status(row):
    """La prioridad alta exige evidencia, contexto y lineas exactas."""
    if bool(row.get("ContextBlocked", False)):
        return "DESCARTAR_CONTEXTO"
    if bool(row.get("MercadoExperimental", False)):
        return "LABORATORIO"
    if int(row.get("NumeroPatas", 99)) > 3:
        return "LABORATORIO"
    if str(row.get("EstadoAlineacion", "")) != "CONFIRMADA":
        return "ESPERAR_ALINEACION"
    if min(
        int(row.get("BaselineOnceLocal", 0) or 0),
        int(row.get("BaselineOnceVisitante", 0) or 0),
    ) < 3:
        return "VIGILAR_SIN_BASELINE_XI"
    if "ROTACION_ALTA" in {
        str(row.get("EstadoOnceLocal", "")),
        str(row.get("EstadoOnceVisitante", "")),
    }:
        return "DESCARTAR_ROTACION_XI"
    if float(row.get("Fiabilidad", 0)) < 0.72:
        return "VIGILAR"
    if float(row.get("Soporte", 0)) < 60 or float(row.get("SoporteEfectivo", 0)) < 35:
        return "VIGILAR"
    if str(row.get("RiesgoRotacion", "")) == "ALTO":
        return "DESCARTAR_CONTEXTO"
    return "COTIZAR"
