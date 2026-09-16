"""FORECASTER FUTBOL V10 PRO.

Motor de pronosticos individuales por partido.  No inventa cuotas y no
construye combinadas.  Las probabilidades se calculan con informacion
disponible antes del encuentro y se validan en orden temporal.

Mercados publicados por cada partido:
  * Resultado 1X2 (local / empate / visitante).
  * Goles del primer tiempo, linea 1.5.
  * Corners del primer tiempo, linea 4.5 (solo con cobertura real).
  * Tarjetas amarillas totales, linea 4.5.
  * Gol del local, linea 0.5.
  * Gol del visitante, linea 0.5.

La etiqueta de color describe evidencia estadistica; no es una orden de
apuesta.  Si faltan datos, el partido sigue visible, pero el mercado se marca
como NO MODELABLE / ROJO en vez de fabricar una seleccion.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import bet_builder_v8_1_robust as base
import bet_builder_v9_3_context as context93

try:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, PoissonRegressor
    from sklearn.metrics import accuracy_score, log_loss, mean_absolute_error
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
except Exception as exc:  # pragma: no cover - mensaje explicito en despliegue
    raise RuntimeError(
        "V10 necesita scikit-learn. Instala requirements.txt antes de ejecutar."
    ) from exc


VERSION = "V10.3-GATUNO-PRO"
APP_DATA_DIR = Path("app_data_v10")
LINEUP_HISTORY_PATH = APP_DATA_DIR / "lineup_history.json"

# La nacionalidad de un club se aprende de su participacion previa en una
# liga domestica. No se deduce por el nombre y no se rellena a mano: si el
# origen no puede demostrarse con datos anteriores queda como UNKNOWN.
DOMESTIC_ORIGIN = {
    "ARG": "ARG",
    "BRA": "BRA",
    "PER": "PER",
    "ESP": "ESP",
    "ENG": "ENG",
    "POR": "POR",
    "TUR": "TUR",
}
SOUTH_AMERICAN_INTERNATIONAL = {"LIB", "SUD"}
MIN_ARG_CROSS_SAMPLE = 30

MIN_HISTORY_FOR_TRAIN = 4
MAX_TEAM_RECORDS = 36
TEAM_DECAY_DAYS = 210.0
ELO_HOME_ADVANTAGE = 55.0
ELO_K = 22.0

RESULT_LABELS = {0: "LOCAL", 1: "EMPATE", 2: "VISITANTE"}

MARKET_CODES = {
    "Resultado 1X2": "RESULT_1X2",
    "Goles 1.er tiempo": "H1_GOALS_OU15",
    "Corners 1.er tiempo": "H1_CORNERS_OU45",
    "Tarjetas amarillas totales": "YELLOW_CARDS_OU45",
}

NUMERIC_FEATURES = [
    "HomeElo",
    "AwayElo",
    "EloDiff",
    "HomePPG",
    "AwayPPG",
    "PPGDiff",
    "HomeGF",
    "HomeGA",
    "AwayGF",
    "AwayGA",
    "HomeVenueGF",
    "HomeVenueGA",
    "AwayVenueGF",
    "AwayVenueGA",
    "HomeH1GF",
    "HomeH1GA",
    "AwayH1GF",
    "AwayH1GA",
    "HomeCornersFor",
    "HomeCornersAgainst",
    "AwayCornersFor",
    "AwayCornersAgainst",
    "HomeCardsFor",
    "HomeCardsAgainst",
    "AwayCardsFor",
    "AwayCardsAgainst",
    "HomeScoreRate",
    "HomeConcedeRate",
    "AwayScoreRate",
    "AwayConcedeRate",
    "HomeDaysRest",
    "AwayDaysRest",
    "HomeMatches14",
    "AwayMatches14",
    "HomeSeasonPPG",
    "AwaySeasonPPG",
    "SeasonPPGDiff",
    "HomePositionPct",
    "AwayPositionPct",
    "PositionDiff",
    "HomeSeasonGames",
    "AwaySeasonGames",
    "CompHomeGoals",
    "CompAwayGoals",
    "CompH1Goals",
    "CompCards",
    "CompHomeWinRate",
    "CompDrawRate",
    "IsCup",
    "HomeIsArgentine",
    "AwayIsArgentine",
    "ArgentineCrossLeague",
    "ArgentineCrossHome",
    "ArgentineCrossAway",
    "InternationalCrossCountry",
    "OriginKnown",
]

CATEGORICAL_FEATURES = ["CompKey", "Grupo"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass
class SequentialState:
    histories: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    elos: dict[str, float] = field(default_factory=lambda: defaultdict(lambda: 1500.0))
    standings: dict[str, dict[str, dict[str, float]]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    competition_history: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    origin_counts: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )


@dataclass
class ProbabilityModel:
    name: str
    target: str
    model: Pipeline
    kind: str
    calibrator: Any
    metrics: dict[str, Any]


@dataclass
class CountModel:
    name: str
    target: str
    model: Pipeline
    metrics: dict[str, Any]


@dataclass
class ModelBundle:
    probability_models: dict[str, ProbabilityModel]
    count_models: dict[str, CountModel]
    metrics: pd.DataFrame
    trained_through: pd.Timestamp


def _num(value: Any) -> float:
    return base.numero(value)


def _clip_probability(p: float) -> float:
    return float(np.clip(float(p), 0.005, 0.995))


def _season_id(comp_key: str, date: Any) -> str:
    start = base.season_start_for(comp_key, pd.Timestamp(date))
    return f"{comp_key}|{pd.Timestamp(start).date()}"


def _weighted_average(records: list[dict[str, Any]], key: str, now: Any) -> float:
    if not records:
        return np.nan
    target = pd.Timestamp(now)
    values: list[float] = []
    weights: list[float] = []
    recent = records[-MAX_TEAM_RECORDS:]
    for index, row in enumerate(recent):
        value = _num(row.get(key, np.nan))
        if pd.isna(value):
            continue
        age = max(0.0, float((target - pd.Timestamp(row["date"])).days))
        order_age = len(recent) - 1 - index
        weight = math.exp(-age / TEAM_DECAY_DAYS) * math.exp(-order_age / 18.0)
        values.append(float(value))
        weights.append(float(weight))
    if not weights or sum(weights) <= 0:
        return np.nan
    return float(np.average(values, weights=weights))


def _profile(records: list[dict[str, Any]], now: Any, venue: str | None = None) -> dict[str, float]:
    all_records = list(records[-MAX_TEAM_RECORDS:])
    selected = [r for r in all_records if venue is None or r.get("venue") == venue]
    overall = {
        key: _weighted_average(all_records, key, now)
        for key in (
            "gf", "ga", "ppg", "h1gf", "h1ga", "corners_for",
            "corners_against", "cards_for", "cards_against", "scored",
            "conceded",
        )
    }
    if venue is None:
        return {**overall, "n": float(len(all_records))}
    venue_values = {
        key: _weighted_average(selected, key, now)
        for key in overall
    }
    n = len(selected)
    shrink = n / (n + 5.0)
    result: dict[str, float] = {}
    for key in overall:
        ov = overall[key]
        vv = venue_values[key]
        if pd.isna(vv):
            result[key] = ov
        elif pd.isna(ov):
            result[key] = vv
        else:
            result[key] = float(shrink * vv + (1.0 - shrink) * ov)
    result["n"] = float(n)
    return result


def _competition_profile(records: list[dict[str, Any]], now: Any) -> dict[str, float]:
    recent = records[-500:]
    defaults = {
        "home_goals": 1.42,
        "away_goals": 1.16,
        "h1_goals": 1.12,
        "cards": 4.6,
        "home_win": 0.44,
        "draw": 0.27,
    }
    out = {}
    for key, default in defaults.items():
        value = _weighted_average(recent, key, now)
        out[key] = default if pd.isna(value) else float(value)
    out["n"] = float(len(recent))
    return out


def _standing_snapshot(table: dict[str, dict[str, float]], team: str) -> dict[str, float]:
    entry = table.get(team, {"games": 0.0, "points": 0.0, "gd": 0.0, "gf": 0.0})
    games = float(entry.get("games", 0.0))
    ppg = float(entry.get("points", 0.0)) / games if games > 0 else np.nan
    teams = list(table)
    if team not in teams or len(teams) < 2:
        position_pct = 0.5
    else:
        ordered = sorted(
            teams,
            key=lambda t: (
                -float(table[t].get("points", 0.0)),
                -float(table[t].get("gd", 0.0)),
                -float(table[t].get("gf", 0.0)),
                t,
            ),
        )
        rank = ordered.index(team) + 1
        position_pct = (rank - 1.0) / max(1.0, len(ordered) - 1.0)
    return {"games": games, "ppg": ppg, "position_pct": float(position_pct)}


def _rest_features(records: list[dict[str, Any]], now: Any) -> tuple[float, int]:
    if not records:
        return np.nan, 0
    target = pd.Timestamp(now)
    dates = [pd.Timestamp(r["date"]) for r in records if pd.Timestamp(r["date"]) < target]
    if not dates:
        return np.nan, 0
    rest = float((target - max(dates)).days)
    matches14 = sum(1 for d in dates if d >= target - pd.Timedelta(days=14))
    return rest, int(matches14)


def _team_origin(state: SequentialState, team: str) -> str:
    counts = state.origin_counts.get(str(team), {})
    if not counts:
        return "UNKNOWN"
    return str(max(counts, key=lambda key: (counts[key], key)))


def _origin_flags(
    state: SequentialState,
    comp_key: str,
    home: str,
    away: str,
) -> dict[str, Any]:
    home_origin = _team_origin(state, home)
    away_origin = _team_origin(state, away)
    is_international = str(comp_key) in SOUTH_AMERICAN_INTERNATIONAL
    known = home_origin != "UNKNOWN" and away_origin != "UNKNOWN"
    arg_cross = bool(
        is_international
        and known
        and ((home_origin == "ARG") ^ (away_origin == "ARG"))
    )
    return {
        "HomeOrigin": home_origin,
        "AwayOrigin": away_origin,
        "HomeIsArgentine": float(home_origin == "ARG"),
        "AwayIsArgentine": float(away_origin == "ARG"),
        "ArgentineCrossLeague": float(arg_cross),
        "ArgentineCrossHome": float(arg_cross and home_origin == "ARG"),
        "ArgentineCrossAway": float(arg_cross and away_origin == "ARG"),
        "InternationalCrossCountry": float(
            is_international and known and home_origin != away_origin
        ),
        "OriginKnown": float(known),
    }


def _feature_row(
    state: SequentialState,
    date: Any,
    comp_key: str,
    grupo: str,
    home: str,
    away: str,
) -> dict[str, Any]:
    date = pd.Timestamp(date)
    hp = _profile(state.histories.get(home, []), date)
    ap = _profile(state.histories.get(away, []), date)
    hv = _profile(state.histories.get(home, []), date, "H")
    av = _profile(state.histories.get(away, []), date, "A")
    cp = _competition_profile(state.competition_history.get(comp_key, []), date)
    hrest, hm14 = _rest_features(state.histories.get(home, []), date)
    arest, am14 = _rest_features(state.histories.get(away, []), date)
    table = state.standings.get(_season_id(comp_key, date), {})
    hs = _standing_snapshot(table, home)
    aws = _standing_snapshot(table, away)
    helo = float(state.elos.get(home, 1500.0))
    aelo = float(state.elos.get(away, 1500.0))
    comp_info = base.COMPETICIONES.get(comp_key, {})
    is_cup = float(str(comp_info.get("tipo", "")).upper() != "LIGA")
    origin = _origin_flags(state, comp_key, home, away)

    return {
        "Date": date,
        "CompKey": str(comp_key),
        "Grupo": str(grupo),
        "HomeTeam": str(home),
        "AwayTeam": str(away),
        "HomeElo": helo,
        "AwayElo": aelo,
        "EloDiff": helo - aelo,
        "HomePPG": hp["ppg"],
        "AwayPPG": ap["ppg"],
        "PPGDiff": hp["ppg"] - ap["ppg"] if pd.notna(hp["ppg"]) and pd.notna(ap["ppg"]) else np.nan,
        "HomeGF": hp["gf"],
        "HomeGA": hp["ga"],
        "AwayGF": ap["gf"],
        "AwayGA": ap["ga"],
        "HomeVenueGF": hv["gf"],
        "HomeVenueGA": hv["ga"],
        "AwayVenueGF": av["gf"],
        "AwayVenueGA": av["ga"],
        "HomeH1GF": hp["h1gf"],
        "HomeH1GA": hp["h1ga"],
        "AwayH1GF": ap["h1gf"],
        "AwayH1GA": ap["h1ga"],
        "HomeCornersFor": hp["corners_for"],
        "HomeCornersAgainst": hp["corners_against"],
        "AwayCornersFor": ap["corners_for"],
        "AwayCornersAgainst": ap["corners_against"],
        "HomeCardsFor": hp["cards_for"],
        "HomeCardsAgainst": hp["cards_against"],
        "AwayCardsFor": ap["cards_for"],
        "AwayCardsAgainst": ap["cards_against"],
        "HomeScoreRate": hp["scored"],
        "HomeConcedeRate": hp["conceded"],
        "AwayScoreRate": ap["scored"],
        "AwayConcedeRate": ap["conceded"],
        "HomeDaysRest": hrest,
        "AwayDaysRest": arest,
        "HomeMatches14": hm14,
        "AwayMatches14": am14,
        "HomeSeasonPPG": hs["ppg"],
        "AwaySeasonPPG": aws["ppg"],
        "SeasonPPGDiff": hs["ppg"] - aws["ppg"] if pd.notna(hs["ppg"]) and pd.notna(aws["ppg"]) else np.nan,
        "HomePositionPct": hs["position_pct"],
        "AwayPositionPct": aws["position_pct"],
        "PositionDiff": aws["position_pct"] - hs["position_pct"],
        "HomeSeasonGames": hs["games"],
        "AwaySeasonGames": aws["games"],
        "CompHomeGoals": cp["home_goals"],
        "CompAwayGoals": cp["away_goals"],
        "CompH1Goals": cp["h1_goals"],
        "CompCards": cp["cards"],
        "CompHomeWinRate": cp["home_win"],
        "CompDrawRate": cp["draw"],
        "IsCup": is_cup,
        **origin,
        "HomeHistoryN": len(state.histories.get(home, [])),
        "AwayHistoryN": len(state.histories.get(away, [])),
        "CompetitionHistoryN": int(cp["n"]),
    }


def _match_record(row: pd.Series, home: bool) -> dict[str, Any]:
    hg, ag = _num(row.get("FTHG")), _num(row.get("FTAG"))
    hthg, htag = _num(row.get("HTHG")), _num(row.get("HTAG"))
    hc, ac = _num(row.get("HC")), _num(row.get("AC"))
    hy, ay = _num(row.get("HY")), _num(row.get("AY"))
    if home:
        gf, ga, h1gf, h1ga = hg, ag, hthg, htag
        cf, ca, cardsf, cardsa, venue = hc, ac, hy, ay, "H"
    else:
        gf, ga, h1gf, h1ga = ag, hg, htag, hthg
        cf, ca, cardsf, cardsa, venue = ac, hc, ay, hy, "A"
    if gf > ga:
        ppg = 3.0
    elif gf == ga:
        ppg = 1.0
    else:
        ppg = 0.0
    return {
        "date": pd.Timestamp(row["Date"]),
        "venue": venue,
        "gf": gf,
        "ga": ga,
        "ppg": ppg,
        "h1gf": h1gf,
        "h1ga": h1ga,
        "corners_for": cf,
        "corners_against": ca,
        "cards_for": cardsf,
        "cards_against": cardsa,
        "scored": float(gf >= 1),
        "conceded": float(ga >= 1),
    }


def _update_standing(table: dict[str, dict[str, float]], team: str, gf: float, ga: float) -> None:
    entry = table.setdefault(team, {"games": 0.0, "points": 0.0, "gd": 0.0, "gf": 0.0})
    entry["games"] += 1.0
    entry["gf"] += gf
    entry["gd"] += gf - ga
    entry["points"] += 3.0 if gf > ga else (1.0 if gf == ga else 0.0)


def _elo_delta(home_elo: float, away_elo: float, hg: float, ag: float) -> float:
    expected = 1.0 / (1.0 + 10.0 ** (-(home_elo + ELO_HOME_ADVANTAGE - away_elo) / 400.0))
    actual = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
    multiplier = 1.0 + 0.35 * math.log1p(abs(hg - ag))
    return float(ELO_K * multiplier * (actual - expected))


def build_feature_dataset(hist: pd.DataFrame) -> tuple[pd.DataFrame, SequentialState]:
    required = {"Date", "CompKey", "Grupo", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = required - set(hist.columns)
    if missing:
        raise ValueError(f"Historico incompleto; faltan columnas: {sorted(missing)}")

    data = hist.copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
    data = data.sort_values(["Date", "CompKey", "HomeTeam"]).reset_index(drop=True)
    state = SequentialState()
    rows: list[dict[str, Any]] = []

    for date, block in data.groupby("Date", sort=True):
        pending: list[tuple[pd.Series, float]] = []
        for _, match in block.iterrows():
            home, away = str(match["HomeTeam"]), str(match["AwayTeam"])
            if min(len(state.histories[home]), len(state.histories[away])) >= MIN_HISTORY_FOR_TRAIN:
                features = _feature_row(
                    state,
                    date,
                    str(match["CompKey"]),
                    str(match["Grupo"]),
                    home,
                    away,
                )
                hg, ag = _num(match.get("FTHG")), _num(match.get("FTAG"))
                hthg, htag = _num(match.get("HTHG")), _num(match.get("HTAG"))
                hy, ay = _num(match.get("HY")), _num(match.get("AY"))
                if hg > ag:
                    result_class = 0
                elif hg == ag:
                    result_class = 1
                else:
                    result_class = 2
                features.update({
                    "Competicion": match.get("Competicion", match.get("CompKey", "")),
                    "ResultClass": result_class,
                    "Y_H1_UNDER15": float(hthg + htag <= 1) if pd.notna(hthg) and pd.notna(htag) else np.nan,
                    "Y_CARDS_OVER45": float(hy + ay >= 5) if pd.notna(hy) and pd.notna(ay) else np.nan,
                    "Y_HOME_SCORE": float(hg >= 1),
                    "Y_AWAY_SCORE": float(ag >= 1),
                    "HomeGoals": hg,
                    "AwayGoals": ag,
                    "H1Goals": hthg + htag if pd.notna(hthg) and pd.notna(htag) else np.nan,
                    "CardsTotal": hy + ay if pd.notna(hy) and pd.notna(ay) else np.nan,
                    "OddsH": _num(match.get("AvgH", match.get("B365H", np.nan))),
                    "OddsD": _num(match.get("AvgD", match.get("B365D", np.nan))),
                    "OddsA": _num(match.get("AvgA", match.get("B365A", np.nan))),
                })
                rows.append(features)
            delta = _elo_delta(float(state.elos[home]), float(state.elos[away]), _num(match["FTHG"]), _num(match["FTAG"]))
            pending.append((match, delta))

        for match, delta in pending:
            home, away = str(match["HomeTeam"]), str(match["AwayTeam"])
            hg, ag = _num(match["FTHG"]), _num(match["FTAG"])
            state.histories[home].append(_match_record(match, True))
            state.histories[away].append(_match_record(match, False))
            state.elos[home] += delta
            state.elos[away] -= delta
            domestic_origin = DOMESTIC_ORIGIN.get(str(match["CompKey"]))
            if domestic_origin:
                state.origin_counts[home][domestic_origin] += 1
                state.origin_counts[away][domestic_origin] += 1
            key = _season_id(str(match["CompKey"]), match["Date"])
            table = state.standings[key]
            _update_standing(table, home, hg, ag)
            _update_standing(table, away, ag, hg)
            hthg, htag = _num(match.get("HTHG")), _num(match.get("HTAG"))
            hy, ay = _num(match.get("HY")), _num(match.get("AY"))
            state.competition_history[str(match["CompKey"])].append({
                "date": pd.Timestamp(match["Date"]),
                "home_goals": hg,
                "away_goals": ag,
                "h1_goals": hthg + htag if pd.notna(hthg) and pd.notna(htag) else np.nan,
                "cards": hy + ay if pd.notna(hy) and pd.notna(ay) else np.nan,
                "home_win": float(hg > ag),
                "draw": float(hg == ag),
            })

    dataset = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
    if dataset.empty:
        raise RuntimeError("No hay suficientes partidos para entrenar V10.")
    return dataset, state


def _preprocessor() -> ColumnTransformer:
    numeric = Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore"
