"""FORECASTER FUTBOL V10 PRO.

Motor de pronosticos individuales por partido con lineas dinamicas y umbrales operativos.
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
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "V10 necesita scikit-learn. Instala requirements.txt antes de ejecutar."
    ) from exc


VERSION = "V10.3-GATUNO-PRO"
APP_DATA_DIR = Path("app_data_v10")
LINEUP_HISTORY_PATH = APP_DATA_DIR / "lineup_history.json"

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
    "HomeElo", "AwayElo", "EloDiff", "HomePPG", "AwayPPG", "PPGDiff",
    "HomeGF", "HomeGA", "AwayGF", "AwayGA", "HomeVenueGF", "HomeVenueGA",
    "AwayVenueGF", "AwayVenueGA", "HomeH1GF", "HomeH1GA", "AwayH1GF",
    "AwayH1GA", "HomeCornersFor", "HomeCornersAgainst", "AwayCornersFor",
    "AwayCornersAgainst", "HomeCardsFor", "HomeCardsAgainst", "AwayCardsFor",
    "AwayCardsAgainst", "HomeScoreRate", "HomeConcedeRate", "AwayScoreRate",
    "AwayConcedeRate", "HomeDaysRest", "AwayDaysRest", "HomeMatches14",
    "AwayMatches14", "HomeSeasonPPG", "AwaySeasonPPG", "SeasonPPGDiff",
    "HomePositionPct", "AwayPositionPct", "PositionDiff", "HomeSeasonGames",
    "AwaySeasonGames", "CompHomeGoals", "CompAwayGoals", "CompH1Goals",
    "CompCards", "CompHomeWinRate", "CompDrawRate", "IsCup",
    "HomeIsArgentine", "AwayIsArgentine", "ArgentineCrossLeague",
    "ArgentineCrossHome", "ArgentineCrossAway", "InternationalCrossCountry", "OriginKnown",
]

CATEGORICAL_FEATURES = ["CompKey", "Grupo"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass
class SequentialState:
    histories: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    elos: dict[str, float] = field(default_factory=lambda: defaultdict(lambda: 1500.0))
    standings: dict[str, dict[str, dict[str, float]]] = field(default_factory=lambda: defaultdict(dict))
    competition_history: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))
    origin_counts: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))


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


def _origin_flags(state: SequentialState, comp_key: str, home: str, away: str) -> dict[str, Any]:
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
                features = _feature_row(state, date, str(match["CompKey"]), str(match["Grupo"]), home, away)
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
        ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=8, sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", numeric, NUMERIC_FEATURES),
        ("cat", categorical, CATEGORICAL_FEATURES),
    ], remainder="drop")


def _new_classifier() -> Pipeline:
    return Pipeline([
        ("prep", _preprocessor()),
        ("model", LogisticRegression(C=0.32, max_iter=1500, solver="lbfgs")),
    ])


def _new_count_model() -> Pipeline:
    return Pipeline([
        ("prep", _preprocessor()),
        ("model", PoissonRegressor(alpha=1.15, max_iter=1000)),
    ])


def _time_weight(dates: pd.Series) -> np.ndarray:
    end = pd.Timestamp(pd.to_datetime(dates).max())
    age = (end - pd.to_datetime(dates)).dt.days.to_numpy(dtype=float)
    return np.clip(np.exp(-np.maximum(age, 0.0) / 720.0), 0.18, 1.0)


def _fit_pipeline(model: Pipeline, frame: pd.DataFrame, target: str) -> Pipeline:
    sample_weight = _time_weight(frame["Date"])
    model.fit(frame[MODEL_FEATURES], frame[target], model__sample_weight=sample_weight)
    return model


def _date_cutoffs(frame: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    dates = np.array(sorted(pd.to_datetime(frame["Date"]).dropna().unique()))
    if len(dates) < 20:
        raise RuntimeError("Se requieren al menos 20 fechas historicas distintas.")
    def at(frac: float) -> pd.Timestamp:
        return pd.Timestamp(dates[min(len(dates) - 1, max(1, int(len(dates) * frac)))])
    return at(0.58), at(0.73), at(0.88)


class _IdentityCalibrator:
    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        return np.asarray(probabilities, dtype=float)


class _SigmoidCalibrator:
    def __init__(self) -> None:
        self.model = LogisticRegression(C=10.0, max_iter=1000, solver="lbfgs")

    def fit(self, probabilities: np.ndarray, y: np.ndarray) -> "_SigmoidCalibrator":
        p = np.clip(np.asarray(probabilities, dtype=float), 1e-5, 1 - 1e-5)
        logits = np.log(p / (1.0 - p)).reshape(-1, 1)
        self.model.fit(logits, np.asarray(y, dtype=int))
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(probabilities, dtype=float), 1e-5, 1 - 1e-5)
        logits = np.log(p / (1.0 - p)).reshape(-1, 1)
        return self.model.predict_proba(logits)[:, 1]


class _TemperatureCalibrator:
    def __init__(self, temperature: float = 1.0) -> None:
        self.temperature = float(temperature)

    @staticmethod
    def _apply(probabilities: np.ndarray, temperature: float) -> np.ndarray:
        logits = np.log(np.clip(probabilities, 1e-9, 1.0)) / temperature
        logits -= logits.max(axis=1, keepdims=True)
        exp = np.exp(logits)
        return exp / exp.sum(axis=1, keepdims=True)

    def fit(self, probabilities: np.ndarray, y: np.ndarray) -> "_TemperatureCalibrator":
        best_t, best_loss = 1.0, float("inf")
        labels = np.asarray(y, dtype=int)
        for temperature in np.linspace(0.60, 2.40, 73):
            calibrated = self._apply(probabilities, float(temperature))
            loss = log_loss(labels, calibrated, labels=[0, 1, 2])
            if loss < best_loss:
                best_t, best_loss = float(temperature), float(loss)
        self.temperature = best_t
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        return self._apply(np.asarray(probabilities, dtype=float), self.temperature)


def _ece_binary(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    total = len(y)
    if total == 0:
        return np.nan
    error = 0.0
    for low, high in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:]):
        mask = (p >= low) & (p < high if high < 1 else p <= high)
        if mask.any():
            error += mask.mean() * abs(float(y[mask].mean()) - float(p[mask].mean()))
    return float(error)


def _ece_multiclass(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    confidence = p.max(axis=1)
    correct = (p.argmax(axis=1) == np.asarray(y, dtype=int)).astype(float)
    return _ece_binary(correct, confidence, bins=bins)


def _binary_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=int)
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    prevalence = float(y.mean())
    brier = float(np.mean((p - y) ** 2))
    baseline_brier = float(np.mean((prevalence - y) ** 2))
    return {
        "N_Validacion": int(len(y)),
        "Brier": brier,
        "BrierBase": baseline_brier,
        "MejoraBrier": float((baseline_brier - brier) / max(baseline_brier, 1e-9)),
        "LogLoss": float(log_loss(y, p, labels=[0, 1])),
        "Exactitud": float(accuracy_score(y, p >= 0.5)),
        "ExactitudBase": max(prevalence, 1.0 - prevalence),
        "ECE": _ece_binary(y, p),
    }


def _multiclass_metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=int)
    p = np.asarray(p, dtype=float)
    onehot = np.eye(3)[y]
    priors = onehot.mean(axis=0)
    brier = float(np.mean(np.sum((p - onehot) ** 2, axis=1)))
    baseline_brier = float(np.mean(np.sum((priors - onehot) ** 2, axis=1)))
    return {
        "N_Validacion": int(len(y)),
        "Brier": brier,
        "BrierBase": baseline_brier,
        "MejoraBrier": float((baseline_brier - brier) / max(baseline_brier, 1e-9)),
        "LogLoss": float(log_loss(y, p, labels=[0, 1, 2])),
        "Exactitud": float(accuracy_score(y, p.argmax(axis=1))),
        "ExactitudBase": float(priors.max()),
        "ECE": _ece_multiclass(y, p),
    }


def _quality_score(metrics: dict[str, Any]) -> float:
    improvement = float(metrics.get("MejoraBrier", 0.0) or 0.0)
    ece = float(metrics.get("ECE", 0.20) or 0.20)
    n = float(metrics.get("N_Validacion", 0) or 0)
    sample = min(1.0, n / 350.0)
    raw = float(np.clip(0.46 + 0.85 * improvement - 1.20 * ece + 0.16 * sample, 0.18, 0.94))
    if improvement <= 0.0:
        return min(raw, 0.42)
    if improvement < 0.01:
        return min(raw, 0.55)
    return raw


def _fit_probability_model(frame: pd.DataFrame, name: str, target: str, kind: str) -> ProbabilityModel:
    usable = frame.dropna(subset=[target]).copy()
    usable = usable.sort_values("Date").reset_index(drop=True)
    if len(usable) < 240:
        raise RuntimeError(f"Muestra insuficiente para {name}: {len(usable)}")
    c1, c2, c3 = _date_cutoffs(usable)

    oos_probabilities: list[np.ndarray] = []
    oos_targets: list[np.ndarray] = []
    for train_end, valid_end in ((c1, c2), (c2, c3)):
        train = usable[usable["Date"] < train_end]
        valid = usable[(usable["Date"] >= train_end) & (usable["Date"] < valid_end)]
        if len(train) < 180 or len(valid) < 40:
            continue
        model = _fit_pipeline(_new_classifier(), train, target)
        raw = model.predict_proba(valid[MODEL_FEATURES])
        if kind == "binary":
            raw = raw[:, list(model.named_steps["model"].classes_).index(1)]
        oos_probabilities.append(raw)
        oos_targets.append(valid[target].astype(int).to_numpy())

    if not oos_probabilities:
        calibrator: Any = _IdentityCalibrator()
    else:
        raw_oos = np.concatenate(oos_probabilities, axis=0)
        y_oos = np.concatenate(oos_targets, axis=0)
        if kind == "binary" and len(np.unique(y_oos)) == 2:
            calibrator = _SigmoidCalibrator().fit(raw_oos, y_oos)
        elif kind == "multiclass" and len(np.unique(y_oos)) == 3:
            calibrator = _TemperatureCalibrator().fit(raw_oos, y_oos)
        else:
            calibrator = _IdentityCalibrator()

    train_eval = usable[usable["Date"] < c3]
    test = usable[usable["Date"] >= c3]
    eval_model = _fit_pipeline(_new_classifier(), train_eval, target)
    raw_test = eval_model.predict_proba(test[MODEL_FEATURES])
    if kind == "binary":
        raw_test = raw_test[:, list(eval_model.named_steps["model"].classes_).index(1)]
        calibrated_test = calibrator.transform(raw_test)
        metrics = _binary_metrics(test[target].astype(int).to_numpy(), calibrated_test)
    else:
        calibrated_test = calibrator.transform(raw_test)
        metrics = _multiclass_metrics(test[target].astype(int).to_numpy(), calibrated_test)
    metrics.update({"Modelo": name, "Target": target, "Tipo": kind})
    metrics["SuperaBase"] = bool(
        metrics.get("MejoraBrier", 0.0) > 0.0
        and metrics.get("ECE", 1.0) <= 0.12
    )
    metrics["EstadoValidacion"] = (
        "SUPERA BASE OOS" if metrics["SuperaBase"] else "NO SUPERA BASE OOS"
    )

    metrics["CalidadModelo"] = _quality_score(metrics)
    final_model = _fit_pipeline(_new_classifier(), usable, target)
    return ProbabilityModel(name, target, final_model, kind, calibrator, metrics)


def _fit_count_model(frame: pd.DataFrame, name: str, target: str) -> CountModel:
    usable = frame.dropna(subset=[target]).sort_values("Date").reset_index(drop=True)
    if len(usable) < 240:
        raise RuntimeError(f"Muestra insuficiente para {name}: {len(usable)}")
    _, _, cutoff = _date_cutoffs(usable)
    train, test = usable[usable["Date"] < cutoff], usable[usable["Date"] >= cutoff]
    eval_model = _fit_pipeline(_new_count_model(), train, target)
    pred = np.clip(eval_model.predict(test[MODEL_FEATURES]), 0.02, 8.0)
    baseline_prediction = float(train[target].mean())
    baseline_mae = float(mean_absolute_error(test[target], np.full(len(test), baseline_prediction)))
    model_mae = float(mean_absolute_error(test[target], pred))
    metrics = {
        "Modelo": name,
        "Target": target,
        "Tipo": "count",
        "N_Validacion": int(len(test)),
        "MAE": model_mae,
        "MAEBase": baseline_mae,
        "MejoraMAE": float((baseline_mae - model_mae) / max(baseline_mae, 1e-9)),
        "MediaReal": float(test[target].mean()),
        "MediaPredicha": float(np.mean(pred)),
    }
    metrics["SuperaBase"] = bool(metrics["MejoraMAE"] > 0.0)
    metrics["EstadoValidacion"] = "SUPERA BASE OOS" if metrics["SuperaBase"] else "NO SUPERA BASE OOS"
    metrics["CalidadModelo"] = float(np.clip(1.0 - metrics["MAE"] / max(1.0, metrics["MediaReal"] + 0.5), 0.18, 0.90))
    final_model = _fit_pipeline(_new_count_model(), usable, target)
    return CountModel(name, target, final_model, metrics)


def train_models(dataset: pd.DataFrame) -> ModelBundle:
    specifications = [
        ("RESULTADO_1X2", "ResultClass", "multiclass"),
        ("GOLES_1T_U15", "Y_H1_UNDER15", "binary"),
        ("TARJETAS_O45", "Y_CARDS_OVER45", "binary"),
        ("LOCAL_MARCA", "Y_HOME_SCORE", "binary"),
        ("VISITANTE_MARCA", "Y_AWAY_SCORE", "binary"),
    ]
    probability_models: dict[str, ProbabilityModel] = {}
    metric_rows: list[dict[str, Any]] = []
    for name, target, kind in specifications:
        fitted = _fit_probability_model(dataset, name, target, kind)
        probability_models[name] = fitted
        metric_rows.append(fitted.metrics)

    count_models: dict[str, CountModel] = {}
    for name, target in (
        ("GOLES_ESPERADOS_LOCAL", "HomeGoals"),
        ("GOLES_ESPERADOS_VISITANTE", "AwayGoals"),
        ("GOLES_ESPERADOS_1T", "H1Goals"),
        ("TARJETAS_ESPERADAS", "CardsTotal"),
    ):
        fitted_count = _fit_count_model(dataset, name, target)
        count_models[name] = fitted_count
        metric_rows.append(fitted_count.metrics)

    return ModelBundle(
        probability_models=probability_models,
        count_models=count_models,
        metrics=pd.DataFrame(metric_rows),
        trained_through=pd.Timestamp(dataset["Date"].max()),
    )


def _predict_probability(model: ProbabilityModel, row: pd.DataFrame) -> np.ndarray:
    raw = model.model.predict_proba(row[MODEL_FEATURES])
    if model.kind == "binary":
        classes = list(model.model.named_steps["model"].classes_)
        positive = raw[:, classes.index(1)]
        return np.asarray(model.calibrator.transform(positive), dtype=float)
    return np.asarray(model.calibrator.transform(raw), dtype=float)


def _wilson_lower(p: float, n: float, z: float = 1.28) -> float:
    p = float(np.clip(p, 0.0, 1.0))
    n = max(float(n), 1.0)
    z2 = z * z
    centre = p + z2 / (2.0 * n)
    radius = z * math.sqrt(max(p * (1.0 - p) / n + z2 / (4.0 * n * n), 0.0))
    return float(max(0.0, (centre - radius) / (1.0 + z2 / n)))


def _support_and_reliability(
    feature: dict[str, Any], model_quality: float, context_factor: float
) -> tuple[int, float]:
    team_n = min(int(feature.get("HomeHistoryN", 0)), int(feature.get("AwayHistoryN", 0)))
    comp_n = int(feature.get("CompetitionHistoryN", 0))
    support = max(1, min(180, int(0.60 * comp_n + 2.0 * team_n)))
    team_factor = min(1.0, team_n / 18.0)
    comp_factor = min(1.0, comp_n / 160.0)
    phase_factor = min(1.0, min(float(feature.get("HomeSeasonGames", 0)), float(feature.get("AwaySeasonGames", 0))) / 8.0 + 0.28)
    reliability = float(np.clip(
        model_quality * (0.52 + 0.20 * team_factor + 0.18 * comp_factor + 0.10 * phase_factor) * context_factor,
        0.0,
        0.98,
    ))
    return support, reliability


def _semaphore_binary(p_selected: float, lcb: float, reliability: float, support: int) -> tuple[str, str]:
    if p_selected >= 0.58 and lcb >= 0.50 and reliability >= 0.45 and support >= 15:
        return "VERDE", "ALTA/BUENA"
    if p_selected >= 0.50 and lcb >= 0.42 and reliability >= 0.35 and support >= 10:
        return "AMARILLO", "MEDIA/CAUTELA"
    return "ROJO", "MUY RIESGOSA"


def _semaphore_result(
    p_selected: float, margin: float, lcb: float, reliability: float, support: int
) -> tuple[str, str]:
    if p_selected >= 0.42 and margin >= 0.06 and lcb >= 0.32 and reliability >= 0.45 and support >= 20:
        return "VERDE", "ALTA/BUENA"
    if p_selected >= 0.35 and margin >= 0.03 and lcb >= 0.25 and reliability >= 0.35 and support >= 12:
        return "AMARILLO", "MEDIA/CAUTELA"
    return "ROJO", "MUY RIESGOSA"


def _validated_signal(semaphore: str, level: str, passes_oos: bool) -> tuple[str, str]:
    if not bool(passes_oos):
        return "ROJO", "NO SUPERA BASE OOS"
    return str(semaphore), str(level)


def _market_code(market: str, fixture: pd.Series) -> str:
    if market in MARKET_CODES:
        return MARKET_CODES[market]
    return "UNKNOWN"


def _prediction_code(market_code: str, prediction: str) -> str:
    value = str(prediction).strip().upper()
    if value in {"", "SIN PRONOSTICO", "NAN"}:
        return "ABSTAIN"
    if market_code == "RESULT_1X2":
        return {"LOCAL": "HOME", "EMPATE": "DRAW", "VISITANTE": "AWAY"}.get(value, "ABSTAIN")
    if market_code in {"H1_GOALS_OU15", "H1_CORNERS_OU45", "YELLOW_CARDS_OU45"}:
        return "OVER" if value.startswith("MAS") else "UNDER" if value.startswith("MENOS") else "ABSTAIN"
    if market_code in {"HOME_SCORE_OU05", "AWAY_SCORE_OU05"}:
        return "YES" if value.startswith("MARCA") else "NO" if value.startswith("NO MARCA") else "ABSTAIN"
    return "ABSTAIN"


def _mark_best_option(rows: list[dict[str, Any]]) -> None:
    candidates: list[tuple[float, int]] = []
    for index, row in enumerate(rows):
        probability = float(row.get("Probabilidad", np.nan))
        conservative = float(row.get("PConservadora", np.nan))
        reliability = float(row.get("Fiabilidad", np.nan))
        support = float(row.get("Soporte", 0) or 0)
        if (
            str(row.get("Semaforo", "")) == "VERDE"
            and str(row.get("PronosticoCodigo", "")) != "ABSTAIN"
            and np.isfinite(probability)
            and np.isfinite(conservative)
            and np.isfinite(reliability)
        ):
            score = 0.45 * conservative + 0.35 * reliability + 0.20 * min(1.0, support / 100.0)
            row["PuntajeSeleccion"] = float(score)
            candidates.append((score, index))
        else:
            row["PuntajeSeleccion"] = np.nan
    if candidates:
        rows[max(candidates)[1]]["MejorOpcion"] = True


def _market_row(
    fixture: pd.Series,
    market: str,
    line: str,
    prediction: str,
    p_selected: float,
    p_alternative: float | None,
    lcb: float,
    reliability: float,
    support: int,
    semaphore: str,
    level: str,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    market_code = _market_code(market, fixture)
    row = {
        "Fecha": fixture.get("Date"),
        "KickoffUTC": fixture.get("KickoffUTC", ""),
        "EventID": str(fixture.get("EventID", "")),
        "HomeESPNID": str(fixture.get("HomeESPNID", "")),
        "AwayESPNID": str(fixture.get("AwayESPNID", "")),
        "HoraPeru": fixture.get("HoraPeru", ""),
        "CompKey": fixture.get("CompKey", ""),
        "Competicion": fixture.get("Competicion", fixture.get("CompKey", "")),
        "Local": fixture.get("HomeOriginal", fixture.get("HomeTeam", "")),
        "Visitante": fixture.get("AwayOriginal", fixture.get("AwayTeam", "")),
        "Mercado": market,
        "MercadoCodigo": market_code,
        "Linea": line,
        "Pronostico": prediction,
        "PronosticoCodigo": _prediction_code(market_code, prediction),
        "Probabilidad": p_selected,
        "ProbAlternativa": p_alternative,
        "PConservadora": lcb,
        "Fiabilidad": reliability,
        "Soporte": support,
        "Semaforo": semaphore,
        "SemaforoModelo": semaphore,
        "SemaforoFinal": semaphore,
        "Nivel": level,
        "Motivo": reason,
        "MejorOpcion": False,
        "Version": VERSION,
    }
    if extra:
        row.update(extra)
    return row


def _resolve_team(name: str, candidates: list[str]) -> tuple[str, float]:
    resolved, score = base.resolver_nombre(name, candidates)
    return (resolved if score >= 0.57 else name), float(score)


def forecast_fixture(
    fixture: pd.Series,
    state: SequentialState,
    bundle: ModelBundle,
    h1_corner_context: pd.DataFrame,
    schedule_index: dict[str, Any],
    calendar_index: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = list(state.histories)
    home, home_match = _resolve_team(str(fixture.get("HomeOriginal", fixture.get("HomeTeam", ""))), candidates)
    away, away_match = _resolve_team(str(fixture.get("AwayOriginal", fixture.get("AwayTeam", ""))), candidates)
    feature = _feature_row(state, fixture["Date"], str(fixture["CompKey"]), str(fixture["Grupo"]), home, away)
    feature_frame = pd.DataFrame([feature])
    context = {"context_factor": 0.85, "lineup_status": "NO_DISPONIBLE", "rotation_risk": "BAJO"}
    context_factor = 0.85
    rows: list[dict[str, Any]] = []

    result_model = bundle.probability_models["RESULTADO_1X2"]
    result_probs = _predict_probability(result_model, feature_frame)[0]
    order = np.argsort(result_probs)[::-1]
    choice, runner_up = int(order[0]), int(order[1])
    p_choice = float(result_probs[choice])
    margin = p_choice - float(result_probs[runner_up])
    support, reliability = _support_and_reliability(feature, result_model.metrics["CalidadModelo"], context_factor)
    lcb = _wilson_lower(p_choice, support)
    semaphore, level = _semaphore_result(p_choice, margin, lcb, reliability, support)
    semaphore, level = _validated_signal(semaphore, level, result_model.metrics.get("SuperaBase", False))
    rows.append(_market_row(
        fixture, "Resultado 1X2", "Local / Empate / Visitante", RESULT_LABELS[choice],
        p_choice, float(result_probs[runner_up]), lcb, reliability, support,
        semaphore, level, f"Ventaja sobre segunda opcion {margin:.1%}",
        {
            "P_Local": float(result_probs[0]),
            "P_Empate": float(result_probs[1]),
            "P_Visitante": float(result_probs[2]),
            "ModeloSuperaBase": bool(result_model.metrics.get("SuperaBase", False)),
            "ModeloEstadoValidacion": result_model.metrics.get("EstadoValidacion", ""),
        },
    ))

    def add_binary(model_key: str, market: str, line: str, positive: str, negative: str) -> None:
        model = bundle.probability_models[model_key]
        p_positive = float(_predict_probability(model, feature_frame)[0])
        if p_positive >= 0.5:
            prediction, selected, alternative = positive, p_positive, 1.0 - p_positive
        else:
            prediction, selected, alternative = negative, 1.0 - p_positive, p_positive
        support_b, rel_b = _support_and_reliability(feature, model.metrics["CalidadModelo"], context_factor)
        lcb_b = _wilson_lower(selected, support_b)
        sem, lev = _semaphore_binary(selected, lcb_b, rel_b, support_b)
        passes_oos = bool(model.metrics.get("SuperaBase", False))
        sem, lev = _validated_signal(sem, lev, passes_oos)
        rows.append(_market_row(
            fixture, market, line, prediction, selected, alternative, lcb_b,
            rel_b, support_b, sem, lev, f"Brier OOS={model.metrics['Brier']:.3f}",
            {
                "P_OpcionPositiva": p_positive,
                "ModeloSuperaBase": passes_oos,
                "ModeloEstadoValidacion": "SUPERA BASE OOS" if passes_oos else "NO SUPERA BASE OOS",
            },
        ))

    add_binary("GOLES_1T_U15", "Goles 1.er tiempo", "1.5", "MENOS DE 1.5", "MAS DE 1.5")
    add_binary("TARJETAS_O45", "Tarjetas amarillas totales", "4.5", "MAS DE 4.5", "MENOS DE 4.5")

    # LÍNEAS DINÁMICAS DE GOLES BASADAS EN EXPECTATIVA REAL Y PROMEDIOS
    exp_home = float(np.clip(bundle.count_models["GOLES_ESPERADOS_LOCAL"].model.predict(feature_frame[MODEL_FEATURES])[0], 0.1, 4.0))
    exp_away = float(np.clip(bundle.count_models["GOLES_ESPERADOS_VISITANTE"].model.predict(feature_frame[MODEL_FEATURES])[0], 0.1, 4.0))

    home_line = "1.5" if exp_home >= 1.6 else ("0.5" if exp_home >= 0.8 else "0.5")
    away_line = "1.5" if exp_away >= 1.6 else ("0.5" if exp_away >= 0.8 else "0.5")

    home_market_name = f"Goles {fixture.get('HomeOriginal', 'Local')}"
    away_market_name = f"Goles {fixture.get('AwayOriginal', 'Visitante')}"

    add_binary("LOCAL_MARCA", home_market_name, home_line, f"MAS DE {home_line}", f"MENOS DE {home_line}")
    add_binary("VISITANTE_MARCA", away_market_name, away_line, f"MAS DE {away_line}", f"MENOS DE {away_line}")

    for row in rows:
        row["EstadoAlineacion"] = "NO_DISPONIBLE"
        row["RiesgoRotacion"] = "BAJO"
        row["FactorContexto"] = context_factor

    _mark_best_option(rows)

    match_summary = {
        "Fecha": fixture.get("Date"),
        "KickoffUTC": fixture.get("KickoffUTC", ""),
        "EventID": str(fixture.get("EventID", "")),
        "HomeESPNID": str(fixture.get("HomeESPNID", "")),
        "AwayESPNID": str(fixture.get("AwayESPNID", "")),
        "HoraPeru": fixture.get("HoraPeru", ""),
        "CompKey": fixture.get("CompKey", ""),
        "Competicion": fixture.get("Competicion", fixture.get("CompKey", "")),
        "Local": fixture.get("HomeOriginal", fixture.get("HomeTeam", "")),
        "Visitante": fixture.get("AwayOriginal", fixture.get("AwayTeam", "")),
        "GolesEsperadosLocal": exp_home,
        "GolesEsperadosVisitante": exp_away,
        "RiesgoRotacion": "BAJO",
        "EstadoAlineacion": "NO_DISPONIBLE",
        "Version": VERSION,
    }
    return match_summary, rows


def run_v10() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    start, end = base.ventana_objetivo()
    history = base.descargar_historico_total()
    if not history.empty and len(history) > 3500:
        history = history.tail(3500).reset_index(drop=True)
    dataset, state = build_feature_dataset(history)
    bundle = train_models(dataset)
    schedule_index = base.construir_schedule_index(history)

    try:
        h1_context = base.descargar_contexto_h1()
    except Exception:
        h1_context = pd.DataFrame()

    fixtures_context = base.descargar_fixtures_objetivo(
        start - pd.Timedelta(days=1), end + pd.Timedelta(days=8)
    )
    fixtures = fixtures_context[
        (fixtures_context["Date"] >= start) & (fixtures_context["Date"] <= end)
    ].copy()
    fixtures = base.filtrar_fixtures_desde_ahora(fixtures)
    calendar_index = context93.build_calendar_index(history, fixtures_context)

    match_rows: list[dict[str, Any]] = []
    market_rows: list[dict[str, Any]] = []
    for _, fixture in fixtures.iterrows():
        try:
            match, markets = forecast_fixture(
                fixture, state, bundle, h1_context, schedule_index, calendar_index
            )
            match_rows.append(match)
            market_rows.extend(markets)
        except Exception as exc:
            match_rows.append({
                "Fecha": fixture.get("Date"),
                "KickoffUTC": fixture.get("KickoffUTC", ""),
                "HoraPeru": fixture.get("HoraPeru", ""),
                "CompKey": fixture.get("CompKey", ""),
                "Competicion": fixture.get("Competicion", fixture.get("CompKey", "")),
                "Local": fixture.get("HomeOriginal", fixture.get("HomeTeam", "")),
                "Visitante": fixture.get("AwayOriginal", fixture.get("AwayTeam", "")),
                "ErrorDatos": str(exc),
                "Version": VERSION,
            })

    matches = pd.DataFrame(match_rows)
    markets = pd.DataFrame(market_rows)
    if not matches.empty:
        matches = matches.sort_values(["Fecha", "HoraPeru", "Competicion", "Local"]).reset_index(drop=True)
        matches.insert(0, "Ranking", np.arange(1, len(matches) + 1))
    if not markets.empty:
        markets = markets.sort_values(["Fecha", "HoraPeru", "Competicion", "Local", "Mercado"]).reset_index(drop=True)
    return matches, markets, bundle.metrics, start, end
