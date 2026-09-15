
# ============================================================
# BET BUILDER V9.3 CONTEXT PRO - MARKET / PRICE OPTIMIZER
# ============================================================
#
# Filosofía:
#   1. NO asumir que una combinación "vale 4.20".
#   2. Generar combinaciones compatibles con mercados comunes.
#   3. Estimar P conjunta DIRECTAMENTE con vecinos históricos.
#   4. Buscar combinaciones con perfil de precio razonable.
#   5. APOSTAR solo después de ingresar la CUOTA REAL de la casa.
#
# Requiere en el mismo repositorio:
#   bet_builder_v8_1_robust.py
#
# Usa la infraestructura robusta V8.1:
#   - 7 ligas + 5 torneos
#   - Football-Data + ESPN
#   - features prepartido sin fuga temporal
#   - fase de temporada
#   - carga / descanso
#   - altitud / clima cuando están disponibles
#
# V9.2 añade:
#   - catálogo de mercados
#   - resultado / asiático
#   - goles FT / 1T
#   - córners equipo / total
#   - tarjetas amarillas equipo / total
#   - optimizador de builders de 3-5 patas
#   - probabilidad conjunta empírica de cada builder
#   - zona de precio (evita builders demasiado "cortos")
#   - validación obligatoria con cuota real >= 4.20
#   - 12 nichos nuevos liquidables con el histórico disponible
#   - rangos de goles, córners y tarjetas observados como un solo evento
#   - diagnóstico de dependencia (lift y correlación Phi)
#   - límite inferior Wilson y penalización por búsqueda de plantillas
#   - estabilidad de régimen reciente vs. histórico anterior
#   - backtest configurable de 7, 30, 60 o 90 días
#
# IMPORTANTE:
#   - No extrae automáticamente la cuota Bet Builder de Betsafe/Betano.
#     Las casas calculan una cuota propietaria y dinámica para la combinación.
#   - La cuota se ingresa en la interfaz y recién allí se aprueba/rechaza.
# ============================================================

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

import bet_builder_v8_1_robust as base
import bet_builder_v9_3_context as context93


VERSION = "V9.3-CONTEXT-ROTATION-GUARD"

CUOTA_REAL_MIN = 4.20
ROI_OBJETIVO = 0.29

# Probabilidad aproximada que equivale a ROI +29% a cuota 4.20.
P_TARGET_420 = (1.0 + ROI_OBJETIVO) / CUOTA_REAL_MIN

# No queremos builders tan probables que casi seguro coticen muy por debajo
# de 4.20, ni builders tan remotos que sean frágiles.
P_PRICE_ZONE_LOW = 0.235
P_PRICE_ZONE_IDEAL_LOW = 0.27
P_PRICE_ZONE_IDEAL_HIGH = 0.38
P_TOO_SHORT = 0.42
P_MIN_CANDIDATE = 0.205

MIN_SUPPORT_COMBO = 32
MIN_NEFF_COMBO = 22.0
MIN_RELIABILITY = 0.58

# La auditoria prospectiva mostro que 4-5 patas multiplicaban puntos de
# fallo y facilitaban cambiar accidentalmente las lineas al copiarlas.
MAX_LEGS = 3
MAX_VARIANTS_PER_MATCH = 3
TOP_MATCHES = 30
MAX_BETS_PER_DAY = 2
MAX_BETS_PER_COMP_DAY = 1
LINEUP_HISTORY_PATH = Path("app_data_v9_3") / "lineup_history.json"

# Shrinkage para combinaciones arbitrarias.
COMBO_PRIOR_STRENGTH = 22.0
COMBO_Z_LCB = 1.28

# Penaliza el optimismo de escoger el mejor resultado entre muchas
# plantillas. Se aplica al límite conservador, no a la probabilidad central.
MULTIPLE_SEARCH_MAX_PENALTY = 0.022

# Estabilidad temporal del mismo builder.
REGIME_DAYS = 365
REGIME_MIN_N = 24
REGIME_MAX_GAP = 0.16

# Dependencia extrema con poca muestra suele ser inestable.
MAX_ABS_PHI_LOW_SAMPLE = 0.82
MIN_PAIR_SUPPORT = 28

# Temporada actual puede recalibrar un combo, pero nunca dominar.
CURRENT_BLEND_MAX = 0.25

# Para que una pata adicional realmente "mueva" el precio:
# P(combo+nueva | combo) debe estar por debajo de este valor.
MAX_CONDITIONAL_BOOSTER = 0.92
MIN_CONDITIONAL_BOOSTER = 0.40


# ============================================================
# CATÁLOGO DE MERCADOS
# ============================================================

@dataclass(frozen=True)
class MarketLeg:
    code: str
    target: str
    family: str
    risk: int          # 1 bajo ... 5 alto
    availability: str # ALTA / MEDIA / EXPERIMENTAL
    label_key: str
    book_legs: int = 1


MARKETS = {
    # Resultado / asiático
    "FAV_PLUS05": MarketLeg(
        "FAV_PLUS05", "Y_FAV_PLUS05", "RESULT", 1, "ALTA", "fav_plus05"
    ),
    "DOG_PLUS15": MarketLeg(
        "DOG_PLUS15", "Y_DOG_PLUS15", "RESULT", 1, "MEDIA", "dog_plus15"
    ),
    "DOG_PLUS05": MarketLeg(
        "DOG_PLUS05", "Y_DOG_PLUS05", "RESULT", 3, "MEDIA", "dog_plus05"
    ),
    "DRAW": MarketLeg(
        "DRAW", "Y_DRAW", "RESULT", 5, "ALTA", "draw"
    ),
    "FAV_WIN": MarketLeg(
        "FAV_WIN", "Y_FAV_WIN", "RESULT", 3, "ALTA", "fav_win"
    ),
    "FAV_MINUS15": MarketLeg(
        "FAV_MINUS15", "Y_FAV_MINUS15", "RESULT", 5, "MEDIA", "fav_minus15"
    ),

    # Goles de equipo / BTTS
    "DOG_GOAL": MarketLeg(
        "DOG_GOAL", "Y_DOG_GOAL", "TEAM_GOAL", 2, "ALTA", "dog_goal"
    ),
    "FAV_GOAL": MarketLeg(
        "FAV_GOAL", "Y_FAV_GOAL", "TEAM_GOAL", 1, "ALTA", "fav_goal"
    ),
    "BTTS": MarketLeg(
        "BTTS", "Y_BTTS", "TEAM_GOAL", 3, "ALTA", "btts"
    ),
    "FAV_GOALS2": MarketLeg(
        "FAV_GOALS2", "Y_FAV_GOALS2", "FAV_TEAM_GOALS", 3, "ALTA", "fav_goals2"
    ),
    "DOG_UNDER15": MarketLeg(
        "DOG_UNDER15", "Y_DOG_UNDER15", "DOG_TEAM_GOALS", 1, "ALTA", "dog_under15"
    ),

    # Córners
    "FAV_C3": MarketLeg(
        "FAV_C3", "Y_FAV_C3", "FAV_CORNERS", 1, "ALTA", "fav_c3"
    ),
    "FAV_C4": MarketLeg(
        "FAV_C4", "Y_FAV_C4", "FAV_CORNERS", 2, "ALTA", "fav_c4"
    ),
    "FAV_C5": MarketLeg(
        "FAV_C5", "Y_FAV_C5", "FAV_CORNERS", 4, "ALTA", "fav_c5"
    ),
    "FAV_C6": MarketLeg(
        "FAV_C6", "Y_FAV_C6", "FAV_CORNERS", 3, "ALTA", "fav_c6"
    ),
    "FAV_C8": MarketLeg(
        "FAV_C8", "Y_FAV_C8", "FAV_CORNERS", 5, "ALTA", "fav_c8"
    ),
    "FAV_C4_7": MarketLeg(
        "FAV_C4_7", "Y_FAV_C4_7", "FAV_CORNERS_RANGE", 3, "MEDIA", "fav_c4_7", 2
    ),
    "DOG_C2": MarketLeg(
        "DOG_C2", "Y_DOG_C2", "DOG_CORNERS", 1, "ALTA", "dog_c2"
    ),
    "DOG_C3": MarketLeg(
        "DOG_C3", "Y_DOG_C3", "DOG_CORNERS", 2, "ALTA", "dog_c3"
    ),
    "TOTAL_C7": MarketLeg(
        "TOTAL_C7", "Y_TOTAL_C7", "TOTAL_CORNERS", 1, "ALTA", "total_c7"
    ),
    "TOTAL_C8": MarketLeg(
        "TOTAL_C8", "Y_TOTAL_C8", "TOTAL_CORNERS", 2, "ALTA", "total_c8"
    ),
    "TOTAL_C9": MarketLeg(
        "TOTAL_C9", "Y_TOTAL_C9", "TOTAL_CORNERS", 3, "ALTA", "total_c9"
    ),
    "TOTAL_C_U8": MarketLeg(
        "TOTAL_C_U8", "Y_TOTAL_C_U8", "TOTAL_CORNERS", 4, "ALTA", "total_c_u8"
    ),
    "TOTAL_C_U10": MarketLeg(
        "TOTAL_C_U10", "Y_TOTAL_C_U10", "TOTAL_CORNERS", 2, "ALTA", "total_c_u10"
    ),
    "TOTAL_C_U12": MarketLeg(
        "TOTAL_C_U12", "Y_TOTAL_C_U12", "TOTAL_CORNERS", 1, "ALTA", "total_c_u12"
    ),
    "TOTAL_C_7_12": MarketLeg(
        "TOTAL_C_7_12", "Y_TOTAL_C_7_12", "TOTAL_CORNERS_RANGE", 2, "MEDIA", "total_c_7_12", 2
    ),

    # Totales de gol
    "UNDER55": MarketLeg(
        "UNDER55", "Y_UNDER55", "TOTAL_GOALS", 1, "ALTA", "under55"
    ),
    "UNDER45": MarketLeg(
        "UNDER45", "Y_UNDER45", "TOTAL_GOALS", 2, "ALTA", "under45"
    ),
    "OVER15": MarketLeg(
        "OVER15", "Y_OVER15", "TOTAL_GOALS", 2, "ALTA", "over15"
    ),
    "OVER05": MarketLeg(
        "OVER05", "Y_OVER05", "TOTAL_GOALS", 1, "ALTA", "over05"
    ),
    "UNDER35": MarketLeg(
        "UNDER35", "Y_UNDER35", "TOTAL_GOALS", 3, "ALTA", "under35"
    ),
    "UNDER25": MarketLeg(
        "UNDER25", "Y_UNDER25", "TOTAL_GOALS", 4, "ALTA", "under25"
    ),
    "OVER25": MarketLeg(
        "OVER25", "Y_OVER25", "TOTAL_GOALS", 4, "ALTA", "over25"
    ),
    "GOALS_2_4": MarketLeg(
        "GOALS_2_4", "Y_GOALS_2_4", "TOTAL_GOALS_RANGE", 2, "MEDIA", "goals_2_4", 2
    ),
    "GOALS_2_5": MarketLeg(
        "GOALS_2_5", "Y_GOALS_2_5", "TOTAL_GOALS_RANGE", 2, "MEDIA", "goals_2_5", 2
    ),

    # Amarillas (se usa HY/AY, no "puntos de tarjetas")
    "CARDS3": MarketLeg(
        "CARDS3", "Y_YELLOW3", "CARDS", 1, "ALTA", "cards3"
    ),
    "CARDS4": MarketLeg(
        "CARDS4", "Y_YELLOW4", "CARDS", 2, "ALTA", "cards4"
    ),
    "CARDS5": MarketLeg(
        "CARDS5", "Y_YELLOW5", "CARDS", 4, "ALTA", "cards5"
    ),
    "FAV_Y1": MarketLeg(
        "FAV_Y1", "Y_FAV_Y1", "CARDS", 1, "MEDIA", "fav_y1"
    ),
    "DOG_Y1": MarketLeg(
        "DOG_Y1", "Y_DOG_Y1", "CARDS", 1, "MEDIA", "dog_y1"
    ),
    "CARDS_U65": MarketLeg(
        "CARDS_U65", "Y_CARDS_U65", "CARDS", 2, "ALTA", "cards_u65"
    ),
    "CARDS_U75": MarketLeg(
        "CARDS_U75", "Y_CARDS_U75", "CARDS", 1, "ALTA", "cards_u75"
    ),
    "CARDS_3_6": MarketLeg(
        "CARDS_3_6", "Y_CARDS_3_6", "CARDS_RANGE", 2, "MEDIA", "cards_3_6", 2
    ),
    "BOTH_Y1": MarketLeg(
        "BOTH_Y1", "Y_BOTH_Y1", "TEAM_CARDS", 2, "MEDIA", "both_y1", 2
    ),

    # Primer tiempo
    "H1_GOAL": MarketLeg(
        "H1_GOAL", "Y_H1_GOAL", "H1_GOALS", 2, "ALTA", "h1_goal"
    ),
    "H1_UNDER25": MarketLeg(
        "H1_UNDER25", "Y_H1_UNDER25", "H1_GOALS", 1, "ALTA", "h1_under25"
    ),
    "H1_FAV_PLUS05": MarketLeg(
        "H1_FAV_PLUS05", "Y_H1_FAV_PLUS05", "H1_RESULT", 1, "MEDIA", "h1_fav_plus05"
    ),
    "H1_GOALS_1_2": MarketLeg(
        "H1_GOALS_1_2", "Y_H1_GOALS_1_2", "H1_GOALS_RANGE", 2, "MEDIA", "h1_goals_1_2", 2
    ),
    "H1_UNDER15": MarketLeg(
        "H1_UNDER15", "Y_H1_UNDER15", "H1_GOALS", 2, "ALTA", "h1_under15"
    ),
}


# Plantillas iniciales. El optimizador puede añadir un booster si la cuota
# potencial es demasiado corta.
TEMPLATES = [
    ("NICHO_ORIGINAL", ["DOG_GOAL", "FAV_C4", "UNDER45"]),
    ("FAV_CONTROL_4C", ["FAV_PLUS05", "FAV_C4", "UNDER45"]),
    ("FAV_MARCA_CONTROL", ["FAV_GOAL", "FAV_C4", "UNDER45"]),
    ("DOG_CUBIERTO_CONTROL", ["DOG_PLUS15", "FAV_C4", "UNDER45"]),
    ("CORNERS_BILATERAL_CONTROL", ["FAV_C4", "DOG_C2", "UNDER45"]),
    ("RESULTADO_BAJO_TARJETAS", ["FAV_PLUS05", "UNDER35", "CARDS_U75"]),
    ("CONTROL_TOTAL_CORNERS", ["FAV_PLUS05", "UNDER45", "TOTAL_C_U12"]),
    ("NICHO_PRECIO_1T", ["DOG_GOAL", "FAV_C4", "UNDER45", "H1_GOAL"]),
    ("NICHO_TARJETAS", ["DOG_GOAL", "FAV_C4", "UNDER45", "CARDS4"]),
    ("NICHO_RESULTADO", ["DOG_GOAL", "FAV_C4", "UNDER45", "FAV_PLUS05"]),
    ("BLINDADO_PRECIO", ["DOG_GOAL", "FAV_C3", "UNDER55", "H1_GOAL", "CARDS3"]),
    ("RESULTADO_CORNER", ["FAV_PLUS05", "FAV_C4", "UNDER45", "H1_GOAL"]),
    ("ASIATICO_DOG", ["DOG_PLUS15", "DOG_GOAL", "FAV_C4", "UNDER45"]),
    ("FAV_DOMINIO", ["FAV_WIN", "FAV_C4", "UNDER45", "H1_GOAL"]),
    ("CORNER_TARJETAS", ["FAV_PLUS05", "FAV_C4", "CARDS4", "UNDER55"]),
    ("CORNER_TOTAL", ["FAV_PLUS05", "FAV_C4", "TOTAL_C8", "UNDER55"]),
    ("BTTS_CONTROL", ["BTTS", "FAV_PLUS05", "FAV_C4", "UNDER55"]),
    ("ASIATICO_CONTROL", ["DOG_PLUS15", "FAV_C4", "UNDER45", "H1_GOAL"]),
    ("FAV_TARJETA", ["FAV_PLUS05", "FAV_C4", "FAV_Y1", "UNDER45"]),
    ("DOG_TARJETA", ["DOG_GOAL", "FAV_C4", "DOG_Y1", "UNDER45"]),

    # Nichos V9.2. Todos se liquidan con goles/córners/amarillas FT o HT.
    ("DOMINIO_SIN_GOLEADA", ["FAV_PLUS05", "FAV_C6", "UNDER35"]),
    ("CORNER_ALTO_GOL_BAJO", ["FAV_C8", "UNDER25", "DOG_PLUS15"]),
    ("RANGO_CORNER_CONTROL", ["FAV_C4_7", "UNDER35", "CARDS_U65"]),
    ("EMPATE_CERRADO", ["DRAW", "UNDER25", "TOTAL_C_U10"]),
    ("EMPATE_CORNER_BAJO", ["DRAW", "TOTAL_C_U8", "CARDS_U75"]),
    ("FAV_CORNER_BTTS", ["BTTS", "FAV_C6", "UNDER55"]),
    ("DOS_EQUIPOS_CORNERS", ["FAV_C4", "DOG_C2", "GOALS_2_5"]),
    ("GOL_CONTROL_RANGO_C", ["GOALS_2_4", "TOTAL_C_7_12", "CARDS_U75"]),
    ("RESULTADO_RANGO_1T", ["FAV_WIN", "H1_GOALS_1_2", "UNDER45"]),
    ("DOBLE_OPORTUNIDAD_1T", ["FAV_PLUS05", "H1_GOALS_1_2", "OVER15"]),
    ("TARJETAS_ACOTADAS", ["BOTH_Y1", "CARDS_U75", "UNDER45"]),
    ("DOG_RESISTE_CONTROL", ["DOG_PLUS05", "UNDER35", "TOTAL_C_U12", "CARDS_U75"]),
]

# Universo operativo V9.3: tres selecciones reales como maximo y sin los
# nichos suspendidos tras comparar los tickets reales con la salida V9.2.
TEMPLATES = [
    (name, legs)
    for name, legs in TEMPLATES
    if name not in context93.SUSPENDED_TEMPLATES
    and sum(MARKETS[code].book_legs for code in legs) <= MAX_LEGS
]

BOOSTERS = [
    "H1_GOAL",
    "CARDS4",
    "TOTAL_C8",
    "FAV_PLUS05",
    "FAV_C5",
    "H1_FAV_PLUS05",
    "DOG_C2",
    "CARDS_U75",
    "TOTAL_C_U12",
]


# ============================================================
# LABELS
# ============================================================

def _team_label(team, home, away):
    if team == home:
        return f"{team} (LOCAL)"
    if team == away:
        return f"{team} (VISITA)"
    return team


def leg_label(code, ctx):
    home = ctx["home_display"]
    away = ctx["away_display"]
    fav = _team_label(ctx["fav_display"], home, away)
    dog = _team_label(ctx["dog_display"], home, away)

    labels = {
        "FAV_PLUS05": f"{fav}: +0.5 HÁNDICAP ASIÁTICO (GANA O EMPATA)",
        "DOG_PLUS15": f"{dog}: +1.5 HÁNDICAP ASIÁTICO",
        "DOG_PLUS05": f"{dog}: +0.5 HÁNDICAP ASIÁTICO (GANA O EMPATA)",
        "DRAW": "RESULTADO DEL PARTIDO: EMPATE",
        "FAV_WIN": f"{fav}: GANA (equiv. -0.5 asiático)",
        "FAV_MINUS15": f"{fav}: -1.5 HÁNDICAP ASIÁTICO",

        "DOG_GOAL": f"{dog}: MARCA 1+ GOL",
        "FAV_GOAL": f"{fav}: MARCA 1+ GOL",
        "BTTS": "AMBOS EQUIPOS MARCAN: SÍ",
        "FAV_GOALS2": f"{fav}: MARCA 2+ GOLES",
        "DOG_UNDER15": f"{dog}: MENOS DE 1.5 GOLES",

        "FAV_C3": f"{fav}: 3+ CÓRNERS",
        "FAV_C4": f"{fav}: 4+ CÓRNERS",
        "FAV_C5": f"{fav}: 5+ CÓRNERS",
        "FAV_C6": f"{fav}: 6+ CÓRNERS",
        "FAV_C8": f"{fav}: 8+ CÓRNERS",
        "FAV_C4_7": f"{fav}: ENTRE 4 Y 7 CÓRNERS (más 3.5 y menos 7.5)",
        "DOG_C2": f"{dog}: 2+ CÓRNERS",
        "DOG_C3": f"{dog}: 3+ CÓRNERS",
        "TOTAL_C7": "7+ CÓRNERS TOTALES",
        "TOTAL_C8": "8+ CÓRNERS TOTALES",
        "TOTAL_C9": "9+ CÓRNERS TOTALES",
        "TOTAL_C_U8": "MENOS DE 8.5 CÓRNERS TOTALES",
        "TOTAL_C_U10": "MENOS DE 10.5 CÓRNERS TOTALES",
        "TOTAL_C_U12": "MENOS DE 12.5 CÓRNERS TOTALES",
        "TOTAL_C_7_12": "ENTRE 7 Y 12 CÓRNERS TOTALES",

        "UNDER55": "MENOS DE 5.5 GOLES",
        "UNDER45": "MENOS DE 4.5 GOLES",
        "OVER15": "MÁS DE 1.5 GOLES",
        "OVER05": "MÁS DE 0.5 GOLES",
        "UNDER35": "MENOS DE 3.5 GOLES",
        "UNDER25": "MENOS DE 2.5 GOLES",
        "OVER25": "MÁS DE 2.5 GOLES",
        "GOALS_2_4": "ENTRE 2 Y 4 GOLES TOTALES",
        "GOALS_2_5": "ENTRE 2 Y 5 GOLES TOTALES",

        "CARDS3": "3+ TARJETAS AMARILLAS TOTALES",
        "CARDS4": "4+ TARJETAS AMARILLAS TOTALES",
        "CARDS5": "5+ TARJETAS AMARILLAS TOTALES",
        "FAV_Y1": f"{fav}: 1+ TARJETA AMARILLA",
        "DOG_Y1": f"{dog}: 1+ TARJETA AMARILLA",
        "CARDS_U65": "MENOS DE 6.5 TARJETAS AMARILLAS TOTALES",
        "CARDS_U75": "MENOS DE 7.5 TARJETAS AMARILLAS TOTALES",
        "CARDS_3_6": "ENTRE 3 Y 6 TARJETAS AMARILLAS TOTALES",
        "BOTH_Y1": "AMBOS EQUIPOS: 1+ TARJETA AMARILLA",

        "H1_GOAL": "1+ GOL EN EL PRIMER TIEMPO",
        "H1_UNDER25": "MENOS DE 2.5 GOLES EN EL PRIMER TIEMPO",
        "H1_FAV_PLUS05": f"{fav}: +0.5 EN 1T (NO PIERDE EL 1T)",
        "H1_GOALS_1_2": "1T: ENTRE 1 Y 2 GOLES (más 0.5 y menos 2.5)",
        "H1_UNDER15": "1T: MENOS DE 1.5 GOLES",
    }

    return labels.get(code, code)


# ============================================================
# DATASET V9
# ============================================================

def _binary(cond, available=True):
    return int(bool(cond)) if available else np.nan


def construir_dataset_v9(hist):
    """
    Crea resultados binarios históricos para todos los mercados.
    Features se calculan ANTES de actualizar la fecha, evitando leakage.
    """
    estados = defaultdict(list)
    rows = []

    orden = hist.sort_values(
        ["Date", "CompKey", "HomeTeam"]
    ).copy()

    for fecha, bloque in orden.groupby("Date", sort=True):
        for _, row in bloque.iterrows():
            hs = base.snapshot(estados[row["HomeTeam"]])
            aws = base.snapshot(estados[row["AwayTeam"]])

            fav = base.detectar_favorito_mercado(row)

            if fav is None:
                fav = base.favorito_modelo(hs, aws)

            feat = base.crear_features(
                row,
                hs,
                aws,
                fav=fav,
            )

            if feat is None or fav is None:
                continue

            hg = base.numero(row.get("FTHG", np.nan))
            ag = base.numero(row.get("FTAG", np.nan))

            if pd.isna(hg) or pd.isna(ag):
                continue

            hc = base.numero(row.get("HC", np.nan))
            ac = base.numero(row.get("AC", np.nan))
            hy = base.numero(row.get("HY", np.nan))
            ay = base.numero(row.get("AY", np.nan))
            hthg = base.numero(row.get("HTHG", np.nan))
            htag = base.numero(row.get("HTAG", np.nan))

            fav_home = fav["tipo"] == "HOME"

            if fav_home:
                fg, dg = hg, ag
                fc, dc = hc, ac
                fy, dy = hy, ay
                fht, dht = hthg, htag
            else:
                fg, dg = ag, hg
                fc, dc = ac, hc
                fy, dy = ay, hy
                fht, dht = htag, hthg

            margin = fg - dg
            total_goals = hg + ag

            corners_available = pd.notna(hc) and pd.notna(ac)
            cards_available = pd.notna(hy) and pd.notna(ay)
            h1_available = pd.notna(hthg) and pd.notna(htag)

            total_c = (hc + ac) if corners_available else np.nan
            total_y = (hy + ay) if cards_available else np.nan
            h1_goals = (hthg + htag) if h1_available else np.nan

            out = {
                "Date": row["Date"],
                "CompKey": row["CompKey"],
                "Grupo": row["Grupo"],
                "Competicion": row["Competicion"],
                "HomeTeam": row["HomeTeam"],
                "AwayTeam": row["AwayTeam"],
                "Referee": row.get("Referee", ""),
                **feat,

                # Resultado / asiático
                "Y_FAV_PLUS05": _binary(margin >= 0),
                "Y_DOG_PLUS15": _binary(margin <= 1),
                "Y_DOG_PLUS05": _binary(margin <= 0),
                "Y_DRAW": _binary(margin == 0),
                "Y_FAV_WIN": _binary(margin >= 1),
                "Y_FAV_MINUS15": _binary(margin >= 2),

                # Goles de equipo
                "Y_DOG_GOAL": _binary(dg >= 1),
                "Y_FAV_GOAL": _binary(fg >= 1),
                "Y_BTTS": _binary(hg >= 1 and ag >= 1),
                "Y_FAV_GOALS2": _binary(fg >= 2),
                "Y_DOG_UNDER15": _binary(dg <= 1),

                # Córners
                "Y_FAV_C3": _binary(fc >= 3, corners_available),
                "Y_FAV_C4": _binary(fc >= 4, corners_available),
                "Y_FAV_C5": _binary(fc >= 5, corners_available),
                "Y_FAV_C6": _binary(fc >= 6, corners_available),
                "Y_FAV_C8": _binary(fc >= 8, corners_available),
                "Y_FAV_C4_7": _binary(4 <= fc <= 7, corners_available),
                "Y_DOG_C2": _binary(dc >= 2, corners_available),
                "Y_DOG_C3": _binary(dc >= 3, corners_available),
                "Y_TOTAL_C7": _binary(total_c >= 7, corners_available),
                "Y_TOTAL_C8": _binary(total_c >= 8, corners_available),
                "Y_TOTAL_C9": _binary(total_c >= 9, corners_available),
                "Y_TOTAL_C_U8": _binary(total_c <= 8, corners_available),
                "Y_TOTAL_C_U10": _binary(total_c <= 10, corners_available),
                "Y_TOTAL_C_U12": _binary(total_c <= 12, corners_available),
                "Y_TOTAL_C_7_12": _binary(7 <= total_c <= 12, corners_available),

                # Goles FT
                "Y_UNDER55": _binary(total_goals <= 5),
                "Y_UNDER45": _binary(total_goals <= 4),
                "Y_OVER15": _binary(total_goals >= 2),
                "Y_OVER05": _binary(total_goals >= 1),
                "Y_UNDER35": _binary(total_goals <= 3),
                "Y_UNDER25": _binary(total_goals <= 2),
                "Y_OVER25": _binary(total_goals >= 3),
                "Y_GOALS_2_4": _binary(2 <= total_goals <= 4),
                "Y_GOALS_2_5": _binary(2 <= total_goals <= 5),

                # Amarillas
                "Y_YELLOW3": _binary(total_y >= 3, cards_available),
                "Y_YELLOW4": _binary(total_y >= 4, cards_available),
                "Y_YELLOW5": _binary(total_y >= 5, cards_available),
                "Y_FAV_Y1": _binary(fy >= 1, cards_available),
                "Y_DOG_Y1": _binary(dy >= 1, cards_available),
                "Y_CARDS_U65": _binary(total_y <= 6, cards_available),
                "Y_CARDS_U75": _binary(total_y <= 7, cards_available),
                "Y_CARDS_3_6": _binary(3 <= total_y <= 6, cards_available),
                "Y_BOTH_Y1": _binary(fy >= 1 and dy >= 1, cards_available),

                # Primer tiempo
                "Y_H1_GOAL": _binary(h1_goals >= 1, h1_available),
                "Y_H1_UNDER25": _binary(h1_goals <= 2, h1_available),
                "Y_H1_FAV_PLUS05": _binary(fht >= dht, h1_available),
                "Y_H1_GOALS_1_2": _binary(1 <= h1_goals <= 2, h1_available),
                "Y_H1_UNDER15": _binary(h1_goals <= 1, h1_available),
            }

            rows.append(out)

        # Actualizar después de calcular todo el bloque del mismo día.
        for _, row in bloque.iterrows():
            base.agregar_estado(estados, row)

    ds = pd.DataFrame(rows)

    if ds.empty:
        raise RuntimeError("Dataset V9 vacío")

    return (
        ds.sort_values("Date").reset_index(drop=True),
        estados,
    )


# ============================================================
# KNN: devuelve vecinos + pesos para combinaciones arbitrarias
# ============================================================

def knn_context(train, x, fecha_objetivo, comp_key, grupo):
    t = base.seleccionar_train(train, comp_key, grupo)
    t = t.dropna(subset=base.FEATURES)

    if len(t) < base.K_MINIMO:
        return None

    if len(t) > base.MAX_TRAIN:
        t = t.tail(base.MAX_TRAIN)

    X = t[base.FEATURES].astype(float).to_numpy()
    xv = np.array(
        [float(x[c]) for c in base.FEATURES],
        dtype=float,
    )

    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    sd[(~np.isfinite(sd)) | (sd < 1e-6)] = 1.0

    Z = (X - mu) / sd
    zv = (xv - mu) / sd

    fw = np.array(
        [base.FEATURE_WEIGHTS[c] for c in base.FEATURES],
        dtype=float,
    )

    dist = np.sqrt(
        np.nanmean(((Z - zv) ** 2) * fw, axis=1)
    )

    k = min(base.K_VECINOS, len(t))
    idx = np.argsort(dist)[:k]

    vecinos = t.iloc[idx].copy()
    d = dist[idx]

    w_sim = np.clip(
        1.0 / (0.30 + d),
        0.12,
        3.0,
    )

    age = (
        pd.Timestamp(fecha_objetivo)
        - pd.to_datetime(vecinos["Date"])
    ).dt.days.to_numpy(dtype=float)

    age = np.maximum(age, 0.0)
    w_rec = np.exp(-age / 360.0)

    weights = w_sim * w_rec

    return {
        "scope": t,
        "neighbors": vecinos,
        "weights": weights,
        "target_date": pd.Timestamp(fecha_objetivo),
    }


def _joint_series(df, target_cols):
    if not target_cols:
        return np.array([], dtype=float), np.array([], dtype=bool)

    mat = np.column_stack(
        [
            pd.to_numeric(df[c], errors="coerce").to_numpy(dtype=float)
            for c in target_cols
        ]
    )

    valid = np.all(np.isfinite(mat), axis=1)

    y = np.full(len(df), np.nan, dtype=float)

    if valid.any():
        y[valid] = np.all(
            mat[valid] >= 0.5,
            axis=1,
        ).astype(float)

    return y, valid


def _wilson_lower(p, n, z=COMBO_Z_LCB):
    """Límite inferior Wilson, más estable que p-z*SE en muestras pequeñas."""
    if pd.isna(p) or pd.isna(n) or n <= 0:
        return np.nan

    p = float(np.clip(p, 0.0, 1.0))
    n = float(max(n, 1.0))
    z2 = z * z
    center = p + z2 / (2.0 * n)
    radius = z * math.sqrt(
        max(p * (1.0 - p) / n + z2 / (4.0 * n * n), 0.0)
    )
    return float(max(0.0, (center - radius) / (1.0 + z2 / n)))


def _weighted_phi(a, b, w):
    valid = np.isfinite(a) & np.isfinite(b) & np.isfinite(w) & (w > 0)

    if int(valid.sum()) < MIN_PAIR_SUPPORT:
        return np.nan, int(valid.sum())

    aa = a[valid].astype(float)
    bb = b[valid].astype(float)
    ww = w[valid].astype(float)
    sw = float(ww.sum())

    if sw <= 0:
        return np.nan, int(valid.sum())

    ma = float(np.dot(ww, aa) / sw)
    mb = float(np.dot(ww, bb) / sw)
    va = float(np.dot(ww, (aa - ma) ** 2) / sw)
    vb = float(np.dot(ww, (bb - mb) ** 2) / sw)

    if va <= 1e-9 or vb <= 1e-9:
        return np.nan, int(valid.sum())

    cov = float(np.dot(ww, (aa - ma) * (bb - mb)) / sw)
    return float(np.clip(cov / math.sqrt(va * vb), -1.0, 1.0)), int(valid.sum())


def dependence_diagnostics(knn, leg_codes, joint_p):
    """Mide dependencia sin suponer independencia para estimar el builder."""
    neighbors = knn["neighbors"]
    weights = np.asarray(knn["weights"], dtype=float)
    targets = [MARKETS[c].target for c in leg_codes]

    marginals = []
    for target in targets:
        values = pd.to_numeric(neighbors[target], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
        if int(valid.sum()) < MIN_PAIR_SUPPORT:
            marginals.append(np.nan)
        else:
            marginals.append(float(np.dot(weights[valid], values[valid]) / weights[valid].sum()))

    product = (
        float(np.prod(marginals))
        if marginals and np.all(np.isfinite(marginals))
        else np.nan
    )
    lift = (
        float(joint_p / product)
        if pd.notna(product) and product > 1e-9
        else np.nan
    )

    phis = []
    pair_support = []
    for i in range(len(targets)):
        ai = pd.to_numeric(neighbors[targets[i]], errors="coerce").to_numpy(dtype=float)
        for j in range(i + 1, len(targets)):
            bj = pd.to_numeric(neighbors[targets[j]], errors="coerce").to_numpy(dtype=float)
            phi, n = _weighted_phi(ai, bj, weights)
            if pd.notna(phi):
                phis.append(phi)
                pair_support.append(n)

    max_abs_phi = float(max((abs(x) for x in phis), default=0.0))
    mean_abs_phi = float(np.mean(np.abs(phis))) if phis else 0.0

    if max_abs_phi >= 0.65:
        level = "ALTA"
    elif max_abs_phi >= 0.35:
        level = "MEDIA"
    else:
        level = "BAJA"

    return {
        "marginals": marginals,
        "independent_product": product,
        "lift": lift,
        "max_abs_phi": max_abs_phi,
        "mean_abs_phi": mean_abs_phi,
        "pair_support_min": int(min(pair_support)) if pair_support else 0,
        "dependence_level": level,
    }


def regime_stability(knn, target_cols):
    """Compara el último año con el año anterior usando solo datos pasados."""
    scope = knn["scope"]
    target_date = pd.Timestamp(knn["target_date"])
    recent_start = target_date - pd.Timedelta(days=REGIME_DAYS)
    prior_start = recent_start - pd.Timedelta(days=REGIME_DAYS)

    recent = scope[(scope["Date"] >= recent_start) & (scope["Date"] < target_date)]
    prior = scope[(scope["Date"] >= prior_start) & (scope["Date"] < recent_start)]

    yr, vr = _joint_series(recent, target_cols)
    yp, vp = _joint_series(prior, target_cols)
    nr = int(vr.sum())
    npast = int(vp.sum())

    if nr < REGIME_MIN_N or npast < REGIME_MIN_N:
        return {
            "recent_rate": np.nan,
            "prior_rate": np.nan,
            "recent_n": nr,
            "prior_n": npast,
            "gap": np.nan,
            "stable": True,
            "confidence": 0.92,
        }

    pr = float(np.nanmean(yr[vr]))
    pp = float(np.nanmean(yp[vp]))
    gap = abs(pr - pp)

    return {
        "recent_rate": pr,
        "prior_rate": pp,
        "recent_n": nr,
        "prior_n": npast,
        "gap": float(gap),
        "stable": bool(gap <= REGIME_MAX_GAP),
        "confidence": float(np.clip(1.0 - 1.6 * gap, 0.65, 1.0)),
    }


def combo_probability(knn, leg_codes):
    target_cols = [MARKETS[c].target for c in leg_codes]

    vecinos = knn["neighbors"]
    weights = knn["weights"]
    scope = knn["scope"]

    y, valid = _joint_series(vecinos, target_cols)

    if valid.sum() < MIN_SUPPORT_COMBO:
        return None

    yy = y[valid]
    ww = weights[valid]

    y_base, valid_base = _joint_series(scope, target_cols)

    if valid_base.sum() < MIN_SUPPORT_COMBO:
        return None

    base_rate = float(np.nanmean(y_base[valid_base]))

    sw = float(ww.sum())

    p = (
        float(np.dot(ww, yy))
        + COMBO_PRIOR_STRENGTH * base_rate
    ) / (
        sw + COMBO_PRIOR_STRENGTH
    )

    p = float(np.clip(p, 0.01, 0.99))

    neff = (
        sw ** 2
        / max(float(np.dot(ww, ww)), 1e-9)
    )

    if neff < MIN_NEFF_COMBO:
        return None

    effective_n = max(neff + COMBO_PRIOR_STRENGTH, 1.0)
    raw_lcb = _wilson_lower(p, effective_n)
    search_penalty = min(
        MULTIPLE_SEARCH_MAX_PENALTY,
        0.0045 * math.log2(max(len(TEMPLATES) + len(BOOSTERS), 2)),
    )
    lcb = max(0.0, raw_lcb - search_penalty)
    dependence = dependence_diagnostics(knn, leg_codes, p)
    stability = regime_stability(knn, target_cols)

    return {
        "p": p,
        "lcb": float(lcb),
        "neff": float(neff),
        "support": int(valid.sum()),
        "base_rate": base_rate,
        "raw_lcb": float(raw_lcb),
        "search_penalty": float(search_penalty),
        **dependence,
        **{f"regime_{k}": v for k, v in stability.items()},
    }


# ============================================================
# TEMPORADA ACTUAL
# ============================================================

def current_combo_rate(ds, leg_codes, comp_key, grupo, date, prior_rate=0.30):
    d = pd.Timestamp(date)
    s0 = base.season_start_for(comp_key, d)

    past = ds[
        (ds["Date"] >= s0)
        & (ds["Date"] < d)
    ].copy()

    exact = past[past["CompKey"] == comp_key]
    sample = exact

    if len(sample) < 22:
        group = past[past["Grupo"] == grupo]
        if len(group) >= 55:
            sample = group

    if sample.empty:
        return np.nan, 0

    cols = [MARKETS[c].target for c in leg_codes]
    y, valid = _joint_series(sample, cols)

    n = int(valid.sum())

    if n < 12:
        return np.nan, n

    # Shrinkage hacia la tasa histórica del mismo builder. V9 usaba 30%
    # para todos los nichos, lo que sesgaba mercados muy frecuentes o raros.
    prior_rate = float(np.clip(prior_rate, 0.03, 0.97))
    p = (
        float(np.nansum(y[valid]))
        + prior_rate * 16.0
    ) / (
        n + 16.0
    )

    return float(p), n


def blend_current(p, p_current, n):
    if pd.isna(p_current) or n < 12:
        return p

    w = min(
        CURRENT_BLEND_MAX,
        0.34 * n / (n + 65.0),
    )

    return float(
        np.clip(
            (1.0 - w) * p + w * p_current,
            0.01,
            0.99,
        )
    )


# ============================================================
# COMPATIBILIDAD / REDUNDANCIA
# ============================================================

def families(legs):
    return [MARKETS[c].family for c in legs]


def book_leg_count(legs):
    return int(sum(MARKETS[c].book_legs if c in MARKETS else 1 for c in legs))


def compatible(legs):
    if len(legs) > MAX_LEGS or book_leg_count(legs) > MAX_LEGS:
        return False

    fams = families(legs)

    # Solo una línea por familia para evitar combinaciones redundantes,
    # salvo que se trate de resultado 1T + resultado FT, que son familias distintas.
    if len(fams) != len(set(fams)):
        return False

    return True


def leg_conditional_probability(knn, base_legs, new_leg):
    p0 = combo_probability(knn, base_legs)
    p1 = combo_probability(knn, base_legs + [new_leg])

    if p0 is None or p1 is None or p0["p"] <= 0:
        return np.nan

    return float(
        np.clip(
            p1["p"] / p0["p"],
            0.0,
            1.0,
        )
    )


# ============================================================
# PRECIO / RIESGO
# ============================================================

def price_zone(p):
    if p >= P_TOO_SHORT:
        return "MUY_CORTA"
    if p >= P_PRICE_ZONE_IDEAL_HIGH:
        return "CORTA"
    if p >= P_PRICE_ZONE_IDEAL_LOW:
        return "IDEAL"
    if p >= P_PRICE_ZONE_LOW:
        return "PRECIO_ALTO"
    return "RIESGO_ALTO"


def price_zone_text(zone):
    return {
        "MUY_CORTA": "Probablemente cotice muy por debajo de 4.20; conviene agregar una pata con sentido.",
        "CORTA": "Puede seguir cotizando por debajo de 4.20; hay que comprobar la casa.",
        "IDEAL": "Zona interesante para cotizar: probabilidad aún sólida y precio potencial mayor.",
        "PRECIO_ALTO": "Puede acercarse a 4.20+, pero el riesgo ya es mayor.",
        "RIESGO_ALTO": "Demasiado frágil para priorizar salvo cuota excepcional.",
    }.get(zone, zone)


def required_quote(p):
    if pd.isna(p) or p <= 0:
        return np.nan

    return max(
        CUOTA_REAL_MIN,
        (1.0 + ROI_OBJETIVO) / p,
    )


def conservative_required_quote(p, lcb):
    """
    Evita depender solo del punto estimado.
    Exige además no destruir el valor usando una probabilidad conservadora.
    """
    q_point = required_quote(p)

    if pd.isna(lcb) or lcb <= 0:
        return q_point

    # No pedimos +29% también al LCB porque sería demasiado severo.
    # Exigimos +5% con la probabilidad conservadora.
    q_lcb = 1.05 / lcb

    return max(
        CUOTA_REAL_MIN,
        q_point,
        q_lcb,
    )


def combined_risk(legs, p, lcb, reliability, phase_early=False):
    risk_points = sum(MARKETS[c].risk for c in legs)
    risk_points += max(0, book_leg_count(legs) - 3)

    if p < 0.25:
        risk_points += 2
    if lcb < 0.20:
        risk_points += 2
    if reliability < 0.65:
        risk_points += 2
    if phase_early:
        risk_points += 1

    if risk_points <= 7:
        return "BAJO-MEDIO"
    if risk_points <= 11:
        return "MEDIO"
    return "ALTO"


# ============================================================
# H1 CÓRNERS - BOOSTER OPCIONAL CON SOPORTE RECIENTE
# ============================================================

def maybe_add_h1_corner_candidate(candidate, h1_context):
    """
    Usa el estimador condicional de V8.1 solo para dos estructuras
    donde existe soporte específico:
      BASE: dog goal + fav4 + under45
      BLINDADO: dog goal + fav3 + under55

    No lo usa para cualquier builder porque eso sería asumir independencia.
    """
    legs = set(candidate["legs"])

    is_base = {"DOG_GOAL", "FAV_C4", "UNDER45"}.issubset(legs)
    is_blind = {"DOG_GOAL", "FAV_C3", "UNDER55"}.issubset(legs)

    if not (is_base or is_blind):
        return None

    if is_base:
        p_cond = h1_context.get("P_H1C3_given_BASE", np.nan)
        n = h1_context.get("H1SampleBase", 0)
    else:
        p_cond = h1_context.get("P_H1C3_given_BLINDADO", np.nan)
        n = h1_context.get("H1SampleBlindado", 0)

    if pd.isna(p_cond) or n < 10:
        return None

    p_new = candidate["p"] * p_cond

    # Penalización conservadora por no tener el mismo KNN de corners 1T.
    p_new *= 0.97

    if p_new < P_MIN_CANDIDATE:
        return None

    lcb_new = candidate["lcb"] * max(0.65, p_cond - 0.08)

    out = dict(candidate)
    out["name"] = candidate["name"] + " + 3C1T"
    out["legs"] = candidate["legs"] + ["H1_CORNERS_3"]
    out["labels"] = candidate["labels"] + ["3+ CÓRNERS TOTALES EN 1T"]
    out["p"] = float(np.clip(p_new, 0.01, 0.99))
    out["lcb"] = float(np.clip(lcb_new, 0.01, 0.99))
    out["support_h1"] = n
    out["availability_note"] = (
        "Córners 1T: verificar disponibilidad en la casa; "
        f"estimación reciente condicional N={n}."
    )
    out["zone"] = price_zone(out["p"])
    out["fair_odds"] = 1.0 / out["p"]
    out["quote_required"] = conservative_required_quote(out["p"], out["lcb"])

    return out


# ============================================================
# BOOSTER AUTOMÁTICO PARA EVITAR BUILDER DEMASIADO CORTO
# ============================================================

def add_price_booster(candidate, knn, ds, comp_key, grupo, date, ctx):
    """
    Si P es muy alta, el builder suele ser demasiado corto
    (como el ejemplo 1.67). Busca una pata no redundante que:
      - reduzca P de forma real
      - mantenga soporte
      - acerque el combo a la zona 27%-38%
    """
    if candidate["p"] < P_TOO_SHORT:
        return candidate

    best = None

    for booster in BOOSTERS:
        if booster in candidate["legs"]:
            continue

        trial_legs = candidate["legs"] + [booster]

        if not compatible(trial_legs):
            continue

        cond = leg_conditional_probability(
            knn,
            candidate["legs"],
            booster,
        )

        if pd.isna(cond):
            continue

        if not (
            MIN_CONDITIONAL_BOOSTER
            <= cond
            <= MAX_CONDITIONAL_BOOSTER
        ):
            continue

        stats = combo_probability(knn, trial_legs)

        if stats is None:
            continue

        p_current, n_current = current_combo_rate(
            ds,
            trial_legs,
            comp_key,
            grupo,
            date,
            prior_rate=stats["base_rate"],
        )

        p = blend_current(
            stats["p"],
            p_current,
            n_current,
        )

        # LCB conservador ajustado proporcionalmente.
        lcb = min(stats["lcb"], p)

        if p < P_MIN_CANDIDATE:
            continue

        target_distance = abs(p - 0.31)

        score = (
            -target_distance
            + 0.30 * lcb
            + 0.05 * (stats["neff"] / 50.0)
        )

        trial = {
            **candidate,
            "name": candidate["name"] + f" + {booster}",
            "legs": trial_legs,
            "labels": [leg_label(c, ctx) for c in trial_legs],
            "p": p,
            "lcb": lcb,
            "neff": stats["neff"],
            "support": stats["support"],
            "current_n": n_current,
            "booster_conditional": cond,
            "reliability": float(np.clip(
                candidate["reliability"]
                * min(1.0, stats["regime_confidence"] / max(candidate.get("regime_confidence", 1.0), 0.65)),
                0.0,
                1.0,
            )),
            "dependence_level": stats["dependence_level"],
            "max_abs_phi": stats["max_abs_phi"],
            "mean_abs_phi": stats["mean_abs_phi"],
            "lift": stats["lift"],
            "independent_product": stats["independent_product"],
            "regime_recent_rate": stats["regime_recent_rate"],
            "regime_prior_rate": stats["regime_prior_rate"],
            "regime_gap": stats["regime_gap"],
            "regime_stable": stats["regime_stable"],
            "regime_confidence": stats["regime_confidence"],
            "search_penalty": stats["search_penalty"],
        }

        if best is None or score > best[0]:
            best = (score, trial)

    return best[1] if best else candidate


# ============================================================
# OPTIMIZAR UN PARTIDO
# ============================================================

def _resolve_fixture_teams(fr, estados):
    names = list(estados.keys())

    home, sh = base.resolver_nombre(fr["HomeOriginal"], names)
    away, sa = base.resolver_nombre(fr["AwayOriginal"], names)

    if sh < 0.57 or sa < 0.57:
        return None

    return home, away, sh, sa


def _phase_and_reliability(schedule_index, home, away, fr, fav_type, knn_stats):
    home_load = base.workload_features(
        schedule_index,
        home,
        fr["Date"],
        fr["CompKey"],
    )

    away_load = base.workload_features(
        schedule_index,
        away,
        fr["Date"],
        fr["CompKey"],
    )

    (
        _corner_adj,
        _dog_adj,
        fatigue_conf,
        fatigue_note,
    ) = base.fatigue_adjustments(
        home_load,
        away_load,
        fav_type,
    )

    phase_conf = min(
        base.phase_confidence_factor(home_load["Phase"]),
        base.phase_confidence_factor(away_load["Phase"]),
    )

    rel_knn = min(
        1.0,
        knn_stats["neff"] / 70.0,
    )

    reliability = float(
        np.clip(
            rel_knn * fatigue_conf * phase_conf,
            0.0,
            1.0,
        )
    )

    phase_early = (
        home_load["Phase"] in ("COLD_START", "EARLY")
        or away_load["Phase"] in ("COLD_START", "EARLY")
    )

    return (
        reliability,
        phase_early,
        home_load,
        away_load,
        fatigue_note,
    )


_LINEUP_CACHE = {}
_LINEUP_CALLS = 0
MAX_LINEUP_CALLS = 40


def _fixture_lineup_context(fr):
    """Consulta alineaciones solo cerca del inicio y conserva NO_DISPONIBLE.

    Una lista de convocados no cuenta como once confirmado. Si ESPN no
    devuelve al menos diez titulares por lado, V9.3 no eleva la prioridad.
    """
    global _LINEUP_CALLS

    event_id = str(fr.get("EventID", ""))
    if not event_id or fr.get("CompKey") not in base.COMPETICIONES:
        return context93.parse_confirmed_lineups({})

    kickoff = pd.to_datetime(fr.get("KickoffUTC"), utc=True, errors="coerce")
    now = pd.Timestamp.now(tz="UTC")
    cached = _LINEUP_CACHE.get(event_id)
    if cached:
        age = now - cached["checked_at"]
        if cached["result"]["status"] == "CONFIRMADA" or age < pd.Timedelta(minutes=15):
            return cached["result"]
    # Las alineaciones suelen aparecer cerca del partido. Evita decenas de
    # llamadas inutiles para encuentros lejanos, pero permite reejecutar V9.3.
    if pd.isna(kickoff) or kickoff - now > pd.Timedelta(hours=6):
        return context93.parse_confirmed_lineups({})
    if _LINEUP_CALLS >= MAX_LINEUP_CALLS:
        return context93.parse_confirmed_lineups({})

    try:
        league = base.COMPETICIONES[fr["CompKey"]]["espn"]
        summary = base.resumen_evento_espn(league, event_id, cache_hours=0.5)
        _LINEUP_CALLS += 1
        result = context93.parse_confirmed_lineups(
            summary,
            fr.get("HomeESPNID", ""),
            fr.get("AwayESPNID", ""),
        )
    except Exception:
        result = context93.parse_confirmed_lineups({})

    _LINEUP_CACHE[event_id] = {"checked_at": now, "result": result}
    return result


def optimizar_fixture(
    fr,
    ds,
    estados,
    schedule_index,
    context_h1,
    calendar_index=None,
):
    resolved = _resolve_fixture_teams(fr, estados)

    if resolved is None:
        return []

    home, away, sh, sa = resolved

    hs = base.snapshot(estados[home])
    aws = base.snapshot(estados[away])

    if hs is None or aws is None:
        return []

    model_row = fr.copy()
    model_row["HomeTeam"] = home
    model_row["AwayTeam"] = away

    fav = base.detectar_favorito_mercado(model_row)

    if fav is None:
        fav = base.favorito_modelo(hs, aws)

    if fav is None:
        return []

    feat = base.crear_features(
        model_row,
        hs,
        aws,
        fav=fav,
    )

    if feat is None:
        return []

    comp_key = fr["CompKey"]
    info = base.COMPETICIONES[comp_key]

    train = ds[ds["Date"] < fr["Date"]]

    if len(train) < 250:
        return []

    knn = knn_context(
        train,
        feat,
        fr["Date"],
        comp_key,
        info["grupo"],
    )

    if knn is None:
        return []

    if fav["tipo"] == "HOME":
        fav_display = fr["HomeOriginal"]
        dog_display = fr["AwayOriginal"]
    else:
        fav_display = fr["AwayOriginal"]
        dog_display = fr["HomeOriginal"]

    ctx = {
        "home_display": fr["HomeOriginal"],
        "away_display": fr["AwayOriginal"],
        "fav_display": fav_display,
        "dog_display": dog_display,
    }

    h1ctx = (
        base.conditional_h1_probs(
            context_h1,
            comp_key,
            info["grupo"],
            fr["Date"],
        )
        if context_h1 is not None
        else {}
    )

    lineup = _fixture_lineup_context(fr)
    lineup_history = context93.load_lineup_history(LINEUP_HISTORY_PATH)
    lineup_home = context93.lineup_strength_profile(
        lineup_history,
        fr.get("HomeOriginal", home),
        lineup.get("home_starters", []),
        fr["Date"],
        fr.get("EventID", ""),
    )
    lineup_away = context93.lineup_strength_profile(
        lineup_history,
        fr.get("AwayOriginal", away),
        lineup.get("away_starters", []),
        fr["Date"],
        fr.get("EventID", ""),
    )
    fixture_context = context93.evaluate_fixture_context(
        fr,
        home,
        away,
        base.workload_features(schedule_index, home, fr["Date"], fr["CompKey"]),
        base.workload_features(schedule_index, away, fr["Date"], fr["CompKey"]),
        fav["tipo"],
        calendar_index or {},
        lineup_status=lineup["status"],
        lineup_home=lineup_home,
        lineup_away=lineup_away,
    )
    # Se archiva despues de construir la referencia para que el partido actual
    # nunca se use a si mismo como evidencia.
    context93.archive_confirmed_lineups(LINEUP_HISTORY_PATH, fr, lineup)

    candidates = []

    for template_name, legs in TEMPLATES:
        if not compatible(legs):
            continue

        guard = context93.candidate_guard(template_name, legs, fixture_context)
        if guard["blocked"]:
            continue

        stats = combo_probability(knn, legs)

        if stats is None:
            continue

        p_current, n_current = current_combo_rate(
            ds,
            legs,
            comp_key,
            info["grupo"],
            fr["Date"],
            prior_rate=stats["base_rate"],
        )

        p = blend_current(
            stats["p"],
            p_current,
            n_current,
        )

        lcb = min(stats["lcb"], p)

        reliability, phase_early, home_load, away_load, fatigue_note = (
            _phase_and_reliability(
                schedule_index,
                home,
                away,
                fr,
                fav["tipo"],
                stats,
            )
        )

        # Fiabilidad compuesta: semejanza de nombres, cobertura, estabilidad
        # temporal y soporte efectivo. La probabilidad central no se infla.
        name_confidence = float(np.clip(min(sh, sa), 0.0, 1.0))
        support_confidence = float(np.clip(stats["support"] / 60.0, 0.72, 1.0))
        reliability = float(np.clip(
            reliability
            * name_confidence
            * support_confidence
            * stats["regime_confidence"]
            * fixture_context["context_factor"],
            0.0,
            1.0,
        ))

        extreme_dependency = (
            stats["max_abs_phi"] > MAX_ABS_PHI_LOW_SAMPLE
            and stats["support"] < 60
        )

        if (
            p < P_MIN_CANDIDATE
            or lcb < 0.15
            or reliability < MIN_RELIABILITY
            or extreme_dependency
        ):
            continue

        candidate = {
            "name": template_name,
            "legs": list(legs),
            "labels": [leg_label(c, ctx) for c in legs],
            "p": float(p),
            "lcb": float(lcb),
            "neff": float(stats["neff"]),
            "support": int(stats["support"]),
            "current_n": int(n_current),
            "reliability": reliability,
            "phase_early": phase_early,
            "home_load": home_load,
            "away_load": away_load,
            "fatigue_note": fatigue_note,
            "availability_note": (
                "La compatibilidad exacta del Bet Builder depende del evento y la casa."
            ),
            "dependence_level": stats["dependence_level"],
            "max_abs_phi": stats["max_abs_phi"],
            "mean_abs_phi": stats["mean_abs_phi"],
            "lift": stats["lift"],
            "independent_product": stats["independent_product"],
            "regime_recent_rate": stats["regime_recent_rate"],
            "regime_prior_rate": stats["regime_prior_rate"],
            "regime_gap": stats["regime_gap"],
            "regime_stable": stats["regime_stable"],
            "regime_confidence": stats["regime_confidence"],
            "search_penalty": stats["search_penalty"],
            "fixture_context": fixture_context,
            "context_guard": guard,
            "lineup": lineup,
        }

        # Si es demasiado probable, intentar hacerla más "cotizable"
        # sin añadir patas arbitrarias.
        candidate = add_price_booster(
            candidate,
            knn,
            ds,
            comp_key,
            info["grupo"],
            fr["Date"],
            ctx,
        )

        if (
            candidate["reliability"] < MIN_RELIABILITY
            or (
                candidate.get("max_abs_phi", 0.0) > MAX_ABS_PHI_LOW_SAMPLE
                and candidate.get("support", 0) < 60
            )
        ):
            continue

        candidate["zone"] = price_zone(candidate["p"])
        candidate["fair_odds"] = 1.0 / candidate["p"]
        candidate["quote_required"] = conservative_required_quote(
            candidate["p"],
            candidate["lcb"],
        )
        candidate["risk"] = combined_risk(
            candidate["legs"],
            candidate["p"],
            candidate["lcb"],
            candidate["reliability"],
            candidate["phase_early"],
        )

        # Puntuación: buscamos equilibrio entre P, LCB, fiabilidad
        # y cercanía a la zona donde un 4.20 puede ser plausible.
        band = math.exp(
            -((candidate["p"] - 0.31) / 0.085) ** 2
        )

        leg_penalty = max(0, book_leg_count(candidate["legs"]) - 4) * 0.035

        instability_penalty = (
            0.06
            if candidate.get("regime_stable") is False
            else 0.0
        )

        candidate["score"] = (
            0.30 * candidate["p"]
            + 0.24 * candidate["lcb"]
            + 0.22 * candidate["reliability"]
            + 0.24 * band
            - leg_penalty
            - instability_penalty
        )

        candidates.append(candidate)

        # Córners 1T permanece en laboratorio: el histórico disponible no
        # permite liquidarlo homogéneamente sin sesgo de cobertura.

    # Deduplicar por conjunto de patas.
    unique = {}

    for c in candidates:
        key = tuple(sorted(c["legs"]))

        if key not in unique or c["score"] > unique[key]["score"]:
            unique[key] = c

    candidates = list(unique.values())

    # Builders demasiado cortos no se priorizan si hay otros.
    preferred = [
        c for c in candidates
        if c["zone"] in ("IDEAL", "PRECIO_ALTO", "CORTA")
        and c["p"] >= P_MIN_CANDIDATE
    ]

    if preferred:
        candidates = preferred

    candidates.sort(
        key=lambda c: (
            -c["score"],
            c["quote_required"],
            -c["lcb"],
        )
    )

    output = []

    for rank, c in enumerate(
        candidates[:MAX_VARIANTS_PER_MATCH],
        start=1,
    ):
        output.append({
            "Fecha": fr["Date"],
            "HoraPeru": fr.get("HoraPeru", ""),
            "CompKey": comp_key,
            "Competicion": info["nombre"],
            "Local": fr["HomeOriginal"],
            "Visitante": fr["AwayOriginal"],
            "Favorito": fav_display,
            "Underdog": dog_display,
            "CuotaFavorito1X2": fav.get("cuota", np.nan),
            "FuenteFavorito": fav.get("fuente", ""),
            "VarianteRank": rank,
            "Variante": c["name"],
            "P_Conjunta": c["p"],
            "P_LCB": c["lcb"],
            "CuotaJustaModelo": c["fair_odds"],
            "CuotaMinROI29": (
                (1.0 + ROI_OBJETIVO) / c["p"]
                if c["p"] > 0 else np.nan
            ),
            "CuotaRequerida": c["quote_required"],
            "CuotaReal": np.nan,
            "ZonaPrecio": c["zone"],
            "ZonaPrecioTexto": price_zone_text(c["zone"]),
            "RiesgoCombinado": c["risk"],
            "Fiabilidad": c["reliability"],
            "Soporte": c.get("support", np.nan),
            "SoporteEfectivo": c.get("neff", np.nan),
            "PartidosTemporadaMuestra": c.get("current_n", 0),
            "Patas": " | ".join(c["labels"]),
            "CodigosPatas": "|".join(c["legs"]),
            "FirmaCombinacion": context93.exact_selection_signature(c["legs"]),
            "NumeroPatas": book_leg_count(c["legs"]),
            "Dependencia": c.get("dependence_level", ""),
            "PhiMaxAbs": c.get("max_abs_phi", np.nan),
            "LiftConjunto": c.get("lift", np.nan),
            "ProductoMarginal": c.get("independent_product", np.nan),
            "TasaReciente": c.get("regime_recent_rate", np.nan),
            "TasaAnterior": c.get("regime_prior_rate", np.nan),
            "BrechaRegimen": c.get("regime_gap", np.nan),
            "RegimenEstable": c.get("regime_stable", True),
            "PenalizacionBusqueda": c.get("search_penalty", np.nan),
            "CoincidenciaNombres": min(sh, sa),
            "FaseLocal": c["home_load"]["Phase"],
            "FaseVisitante": c["away_load"]["Phase"],
            "DescansoLocal": c["home_load"]["DaysRest"],
            "DescansoVisitante": c["away_load"]["DaysRest"],
            "Carga14Local": c["home_load"]["Matches14"],
            "Carga14Visitante": c["away_load"]["Matches14"],
            "NotaFatiga": c.get("fatigue_note", ""),
            "NotaDisponibilidad": c.get("availability_note", ""),
            "FaseCompetitiva": c["fixture_context"]["stage"],
            "ImportanciaPartido": c["fixture_context"]["importance"],
            "RiesgoRotacion": c["fixture_context"]["rotation_risk"],
            "ScoreRotacionLocal": c["fixture_context"]["rotation_score_home"],
            "ScoreRotacionVisitante": c["fixture_context"]["rotation_score_away"],
            "EstadoAlineacion": c["fixture_context"]["lineup_status"],
            "TitularesLocalDetectados": c["lineup"].get("home_count", 0),
            "TitularesVisitanteDetectados": c["lineup"].get("away_count", 0),
            "EstadoOnceLocal": c["fixture_context"]["lineup_home"].get("status", ""),
            "EstadoOnceVisitante": c["fixture_context"]["lineup_away"].get("status", ""),
            "BaselineOnceLocal": c["fixture_context"]["lineup_home"].get("baseline_matches", 0),
            "BaselineOnceVisitante": c["fixture_context"]["lineup_away"].get("baseline_matches", 0),
            "ContinuidadOnceLocal": c["fixture_context"]["lineup_home"].get("continuity", np.nan),
            "ContinuidadOnceVisitante": c["fixture_context"]["lineup_away"].get("continuity", np.nan),
            "CoberturaClavesLocal": c["fixture_context"]["lineup_home"].get("key_coverage", np.nan),
            "CoberturaClavesVisitante": c["fixture_context"]["lineup_away"].get("key_coverage", np.nan),
            "FactorContexto": c["fixture_context"]["context_factor"],
            "NotaContexto": c["fixture_context"]["note"],
            "MercadosSensiblesRotacion": c["context_guard"]["sensitive_legs"],
            "MercadoExperimental": c["context_guard"]["experimental"],
            "ContextBlocked": c["context_guard"]["blocked"],
            "ScoreV9": c["score"],
            "EstadoPreCuota": "",
        })

    for row in output:
        row["EstadoPreCuota"] = context93.priority_status(row)

    return output


# ============================================================
# RUN COMPLETO
# ============================================================

def run_v9():
    inicio, fin = base.ventana_objetivo()

    hist = base.descargar_historico_total()

    ds, estados = construir_dataset_v9(hist)

    schedule_index = base.construir_schedule_index(hist)

    try:
        context_h1 = base.descargar_contexto_h1()
    except Exception:
        context_h1 = pd.DataFrame()

    # Se descarga una ventana mayor para observar el siguiente compromiso.
    # La seleccion objetivo conserva exactamente las fechas solicitadas.
    fixtures_context = base.descargar_fixtures_objetivo(
        inicio - pd.Timedelta(days=1),
        fin + pd.Timedelta(days=8),
    )
    fixtures = fixtures_context[
        (fixtures_context["Date"] >= inicio)
        & (fixtures_context["Date"] <= fin)
    ].copy()
    calendar_index = context93.build_calendar_index(hist, fixtures_context)

    rows = []

    for _, fr in fixtures.iterrows():
        try:
            rows.extend(
                optimizar_fixture(
                    fr,
                    ds,
                    estados,
                    schedule_index,
                    context_h1,
                    calendar_index,
                )
            )
        except Exception:
            # Un partido no debe tumbar toda la ventana.
            continue

    result = pd.DataFrame(rows)

    if result.empty:
        return (
            result,
            inicio,
            fin,
        )

    # Ranking de partidos usando la mejor variante de cada encuentro.
    result["MatchKey"] = (
        result["Fecha"].astype(str)
        + "|"
        + result["Competicion"].astype(str)
        + "|"
        + result["Local"].astype(str)
        + "|"
        + result["Visitante"].astype(str)
    )

    best = (
        result.sort_values(
            ["ScoreV9", "P_LCB"],
            ascending=[False, False],
        )
        .groupby("MatchKey", as_index=False)
        .first()
        .sort_values(
            ["ScoreV9", "P_LCB"],
            ascending=[False, False],
        )
        .head(TOP_MATCHES)
    )

    allowed = set(best["MatchKey"])

    result = result[
        result["MatchKey"].isin(allowed)
    ].copy()

    # Orden: partido top, luego variantes.
    match_order = {
        k: i
        for i, k in enumerate(best["MatchKey"], start=1)
    }

    result["RankingPartido"] = result["MatchKey"].map(match_order)

    # Control de cartera: como maximo dos partidos por dia y uno por
    # competicion/dia. No elimina candidatos; los marca para que el usuario
    # pueda auditar por que quedaron fuera del cupo.
    portfolio_keys = set()
    day_count = defaultdict(int)
    comp_day_count = defaultdict(int)
    for _, row in best.iterrows():
        day_key = str(pd.Timestamp(row["Fecha"]).date())
        comp_key = (day_key, str(row["Competicion"]))
        if day_count[day_key] >= MAX_BETS_PER_DAY:
            continue
        if comp_day_count[comp_key] >= MAX_BETS_PER_COMP_DAY:
            continue
        portfolio_keys.add(row["MatchKey"])
        day_count[day_key] += 1
        comp_day_count[comp_key] += 1
    result["CupoCartera"] = result["MatchKey"].isin(portfolio_keys)

    result = result.sort_values(
        ["RankingPartido", "VarianteRank"]
    ).reset_index(drop=True)

    return (
        result,
        inicio,
        fin,
    )


# ============================================================
# VALIDACIÓN DE CUOTA REAL
# ============================================================

def validate_real_quote(
    row,
    actual_quote,
    exact_confirmed=False,
    quoted_signature="",
):
    """
    Regla dura:
      actual < 4.20 -> DESCARTAR
      actual >= 4.20 pero < CuotaRequerida -> NO ALCANZA OBJETIVO
      actual >= CuotaRequerida -> VÁLIDA
    """
    q = float(actual_quote or 0.0)

    if q <= 0:
        return {
            "status": "PENDIENTE",
            "ev": np.nan,
            "ev_lcb": np.nan,
            "message": "Ingresar cuota real de la casa.",
        }

    expected_signature = str(row.get("FirmaCombinacion", "")).strip().upper()
    supplied_signature = str(quoted_signature or expected_signature).strip().upper()
    if supplied_signature != expected_signature:
        return {
            "status": "COMBINACION_MODIFICADA",
            "ev": np.nan,
            "ev_lcb": np.nan,
            "message": (
                "La combinacion cotizada no coincide con las lineas exactas "
                f"del modelo ({expected_signature})."
            ),
        }
    if not exact_confirmed:
        return {
            "status": "CONFIRMAR_COMBINACION",
            "ev": np.nan,
            "ev_lcb": np.nan,
            "message": (
                "Confirma cada seleccion exacta. +1.5 no es +1.75; "
                "6+ corners equivale a mas de 5.5, no a mas de 6.5."
            ),
        }

    pre_status = str(row.get("EstadoPreCuota", ""))
    if pre_status != "COTIZAR":
        return {
            "status": "NO_HABILITADA_CONTEXTO",
            "ev": np.nan,
            "ev_lcb": np.nan,
            "message": f"Estado previo {pre_status}: V9.3 no autoriza apostar.",
        }
    if not bool(row.get("CupoCartera", True)):
        return {
            "status": "FUERA_CUPO_CARTERA",
            "ev": np.nan,
            "ev_lcb": np.nan,
            "message": "Fuera del limite de dos apuestas por dia y una por competicion.",
        }

    p = float(row["P_Conjunta"])
    lcb = float(row["P_LCB"])
    q_req = float(row["CuotaRequerida"])

    ev = p * q - 1.0
    ev_lcb = lcb * q - 1.0

    fair = float(row.get("CuotaJustaModelo", np.nan))
    if pd.notna(fair) and fair > 0 and q / fair > 1.75:
        return {
            "status": "REVISAR_PRECIO_MAPPING",
            "ev": ev,
            "ev_lcb": ev_lcb,
            "message": (
                "La cuota real se aleja demasiado de la cuota justa del modelo. "
                "Revisar mercado, linea y tipo de handicap antes de continuar."
            ),
        }

    if q < CUOTA_REAL_MIN:
        return {
            "status": "DESCARTAR_CUOTA",
            "ev": ev,
            "ev_lcb": ev_lcb,
            "message": (
                f"Cuota {q:.2f} < {CUOTA_REAL_MIN:.2f}. "
                "No pertenece al nicho de precio."
            ),
        }

    if q < q_req:
        return {
            "status": "NO_ALCANZA_ROI",
            "ev": ev,
            "ev_lcb": ev_lcb,
            "message": (
                f"Cumple 4.20, pero el modelo exige {q_req:.2f} "
                "para el margen objetivo."
            ),
        }

    return {
        "status": "VALIDA",
        "ev": ev,
        "ev_lcb": ev_lcb,
        "message": (
            f"Cuota válida. EV modelo ≈ {ev*100:.1f}%."
        ),
    }


# ============================================================
# BACKTEST WALK-FORWARD V9 — 7 DÍAS COMPLETADOS
# ============================================================

def _historical_candidate_context(row, ds, schedule_index):
    """
    Reconstruye exactamente el contexto V9 para un partido histórico,
    usando solo filas con Date < fecha del partido.

    Esto evita usar el resultado futuro para seleccionar la apuesta.
    """
    d = pd.Timestamp(row["Date"])

    train = ds[
        ds["Date"] < d
    ].copy()

    if len(train) < 250:
        return []

    x = {
        c: row[c]
        for c in base.FEATURES
    }

    knn = knn_context(
        train,
        x,
        d,
        row["CompKey"],
        row["Grupo"],
    )

    if knn is None:
        return []

    fav_type = (
        "HOME"
        if float(
            row.get(
                "FavIsHome",
                0.0,
            )
        ) >= 0.5
        else "AWAY"
    )

    home = str(
        row["HomeTeam"]
    )
    away = str(
        row["AwayTeam"]
    )

    fav_display = (
        home
        if fav_type == "HOME"
        else away
    )

    dog_display = (
        away
        if fav_type == "HOME"
        else home
    )

    ctx = {
        "home_display": home,
        "away_display": away,
        "fav_display": fav_display,
        "dog_display": dog_display,
    }

    fr = {
        "Date": d,
        "CompKey": row["CompKey"],
    }

    candidates = []

    for template_name, legs in TEMPLATES:
        if not compatible(legs):
            continue

        stats = combo_probability(
            knn,
            legs,
        )

        if stats is None:
            continue

        p_current, n_current = (
            current_combo_rate(
                ds,
                legs,
                row["CompKey"],
                row["Grupo"],
                d,
                prior_rate=stats["base_rate"],
            )
        )

        p = blend_current(
            stats["p"],
            p_current,
            n_current,
        )

        lcb = min(
            stats["lcb"],
            p,
        )

        (
            reliability,
            phase_early,
            home_load,
            away_load,
            fatigue_note,
        ) = _phase_and_reliability(
            schedule_index,
            home,
            away,
            fr,
            fav_type,
            stats,
        )

        support_confidence = float(np.clip(stats["support"] / 60.0, 0.72, 1.0))
        reliability = float(np.clip(
            reliability * support_confidence * stats["regime_confidence"],
            0.0,
            1.0,
        ))

        extreme_dependency = (
            stats["max_abs_phi"] > MAX_ABS_PHI_LOW_SAMPLE
            and stats["support"] < 60
        )

        if (
            p < P_MIN_CANDIDATE
            or lcb < 0.15
            or reliability < MIN_RELIABILITY
            or extreme_dependency
        ):
            continue

        candidate = {
            "name": template_name,
            "legs": list(legs),
            "labels": [
                leg_label(
                    c,
                    ctx,
                )
                for c in legs
            ],
            "p": float(p),
            "lcb": float(lcb),
            "neff": float(
                stats["neff"]
            ),
            "support": int(
                stats["support"]
            ),
            "current_n": int(
                n_current
            ),
            "reliability": reliability,
            "phase_early": phase_early,
            "home_load": home_load,
            "away_load": away_load,
            "fatigue_note": fatigue_note,
            "availability_note": (
                "Backtest con mercados liquidables en el histórico."
            ),
            "dependence_level": stats["dependence_level"],
            "max_abs_phi": stats["max_abs_phi"],
            "mean_abs_phi": stats["mean_abs_phi"],
            "lift": stats["lift"],
            "independent_product": stats["independent_product"],
            "regime_recent_rate": stats["regime_recent_rate"],
            "regime_prior_rate": stats["regime_prior_rate"],
            "regime_gap": stats["regime_gap"],
            "regime_stable": stats["regime_stable"],
            "regime_confidence": stats["regime_confidence"],
            "search_penalty": stats["search_penalty"],
        }

        # Igual que producción: si el combo parece demasiado corto,
        # busca un booster histórico compatible.
        candidate = add_price_booster(
            candidate,
            knn,
            ds,
            row["CompKey"],
            row["Grupo"],
            d,
            ctx,
        )

        if (
            candidate["reliability"] < MIN_RELIABILITY
            or (
                candidate.get("max_abs_phi", 0.0) > MAX_ABS_PHI_LOW_SAMPLE
                and candidate.get("support", 0) < 60
            )
        ):
            continue

        candidate["zone"] = (
            price_zone(
                candidate["p"]
            )
        )

        candidate["fair_odds"] = (
            1.0
            / candidate["p"]
        )

        candidate[
            "quote_required"
        ] = (
            conservative_required_quote(
                candidate["p"],
                candidate["lcb"],
            )
        )

        candidate[
            "risk"
        ] = combined_risk(
            candidate["legs"],
            candidate["p"],
            candidate["lcb"],
            candidate["reliability"],
            candidate["phase_early"],
        )

        band = math.exp(
            -(
                (
                    candidate["p"]
                    - 0.31
                )
                / 0.085
            ) ** 2
        )

        leg_penalty = (
            max(
                0,
                book_leg_count(candidate["legs"])
                - 4,
            )
            * 0.035
        )

        candidate[
            "score"
        ] = (
            0.30
            * candidate["p"]
            + 0.24
            * candidate["lcb"]
            + 0.22
            * candidate[
                "reliability"
            ]
            + 0.24
            * band
            - leg_penalty
            - (0.06 if candidate.get("regime_stable") is False else 0.0)
        )

        candidates.append(
            candidate
        )

    # No añadimos córners 1T al backtest si el histórico no ofrece
    # un resultado homogéneo para liquidarlo. Así no inventamos aciertos.
    unique = {}

    for c in candidates:
        key = tuple(
            sorted(
                c["legs"]
            )
        )

        if (
            key not in unique
            or c["score"]
            > unique[key][
                "score"
            ]
        ):
            unique[key] = c

    candidates = list(
        unique.values()
    )

    preferred = [
        c
        for c in candidates
        if c["zone"]
        in (
            "IDEAL",
            "PRECIO_ALTO",
            "CORTA",
        )
        and c["p"]
        >= P_MIN_CANDIDATE
    ]

    if preferred:
        candidates = preferred

    candidates.sort(
        key=lambda c: (
            -c["score"],
            c["quote_required"],
            -c["lcb"],
        )
    )

    return candidates[
        :MAX_VARIANTS_PER_MATCH
    ]


def _settle_historical_combo(
    row,
    legs,
):
    """
    Liquida el builder con los targets del dataset histórico.

    True  = todas las patas ganaron
    False = al menos una perdió
    None  = falta información para una pata
    """
    outcomes = []

    for code in legs:
        market = MARKETS.get(
            code
        )

        if market is None:
            return None

        value = pd.to_numeric(
            pd.Series(
                [
                    row.get(
                        market.target,
                        np.nan,
                    )
                ]
            ),
            errors="coerce",
        ).iloc[0]

        if pd.isna(
            value
        ):
            return None

        outcomes.append(
            float(value)
            >= 0.5
        )

    return bool(
        all(outcomes)
    )


def _max_drawdown_from_profits(
    profits,
):
    """
    Drawdown absoluto en unidades monetarias usando beneficio acumulado.
    """
    equity = 0.0
    peak = 0.0
    max_dd = 0.0

    for p in profits:
        equity += float(p)
        peak = max(
            peak,
            equity,
        )
        dd = peak - equity
        max_dd = max(
            max_dd,
            dd,
        )

    return float(
        max_dd
    )


def _longest_losing_streak(
    results,
):
    longest = 0
    current = 0

    for r in results:
        if r == "PERDIDA":
            current += 1
            longest = max(
                longest,
                current,
            )
        else:
            current = 0

    return int(
        longest
    )


def backtest_v9_window(
    stake=100.0,
    settlement_odds=4.20,
    max_bets=30,
    end_date=None,
    days=30,
):
    """
    Backtest walk-forward configurable de 7 a 180 días.

    IMPORTANTE:
    settlement_odds es una cuota de SIMULACIÓN.
    No afirma que Betsafe/Betano ofrecieran históricamente ese precio.

    La selección sí es prepartido:
      - train: Date < partido
      - una apuesta máximo por partido
      - no se fuerzan 30
      - solo entra si CuotaRequerida <= cuota de simulación

    Retorna:
      bets_df, summary, by_comp, by_niche
    """
    stake = float(
        stake
    )

    settlement_odds = float(
        settlement_odds
    )

    max_bets = max(
        1,
        int(
            max_bets
        ),
    )

    days = int(np.clip(int(days), 7, 180))

    if end_date is None:
        now_local = datetime.now(
            base.TZ_PERU
        )

        test_end = (
            pd.Timestamp(
                now_local.date()
            )
            - pd.Timedelta(
                days=1
            )
        )
    else:
        test_end = pd.Timestamp(
            end_date
        ).normalize()

    test_start = (
        test_end
        - pd.Timedelta(
            days=days - 1
        )
    )

    hist = (
        base.descargar_historico_total()
    )

    ds, _ = (
        construir_dataset_v9(
            hist
        )
    )

    schedule_index = (
        base.construir_schedule_index(
            hist
        )
    )

    test = ds[
        (
            ds["Date"]
            >= test_start
        )
        & (
            ds["Date"]
            <= test_end
        )
    ].copy()

    rows = []

    for _, row in test.sort_values(
        [
            "Date",
            "CompKey",
            "HomeTeam",
        ]
    ).iterrows():

        candidates = (
            _historical_candidate_context(
                row,
                ds,
                schedule_index,
            )
        )

        if not candidates:
            continue

        eligible = [
            c
            for c in candidates
            if (
                c[
                    "quote_required"
                ]
                <= (
                    settlement_odds
                    + 1e-9
                )
            )
            and c[
                "zone"
            ] != "MUY_CORTA"
        ]

        if not eligible:
            continue

        # Una sola apuesta por partido, elegida por score prepartido.
        selected = sorted(
            eligible,
            key=lambda c: (
                -c["score"],
                c[
                    "quote_required"
                ],
                -c["lcb"],
            ),
        )[0]

        hit = (
            _settle_historical_combo(
                row,
                selected["legs"],
            )
        )

        if hit is None:
            continue

        profit = (
            stake
            * (
                settlement_odds
                - 1.0
            )
            if hit
            else -stake
        )

        fav_home = (
            float(
                row.get(
                    "FavIsHome",
                    0.0,
                )
            )
            >= 0.5
        )

        favorito = (
            row["HomeTeam"]
            if fav_home
            else row["AwayTeam"]
        )

        dog = (
            row["AwayTeam"]
            if fav_home
            else row["HomeTeam"]
        )

        rows.append({
            "Fecha": row[
                "Date"
            ],
            "Competicion": row[
                "Competicion"
            ],
            "Local": row[
                "HomeTeam"
            ],
            "Visitante": row[
                "AwayTeam"
            ],
            "Favorito": favorito,
            "Underdog": dog,
            "Variante": selected[
                "name"
            ],
            "Patas": " | ".join(
                selected[
                    "labels"
                ]
            ),
            "P_Modelo": selected[
                "p"
            ],
            "P_LCB": selected[
                "lcb"
            ],
            "Fiabilidad": selected[
                "reliability"
            ],
            "CuotaRequerida": selected[
                "quote_required"
            ],
            "NumeroPatas": book_leg_count(selected["legs"]),
            "Dependencia": selected.get("dependence_level", ""),
            "PhiMaxAbs": selected.get("max_abs_phi", np.nan),
            "LiftConjunto": selected.get("lift", np.nan),
            "BrechaRegimen": selected.get("regime_gap", np.nan),
            "RegimenEstable": selected.get("regime_stable", True),
            "ZonaPrecio": selected[
                "zone"
            ],
            "Riesgo": selected[
                "risk"
            ],
            "ScoreV9": selected[
                "score"
            ],
            "Resultado": (
                "GANADA"
                if hit
                else "PERDIDA"
            ),
            "Stake": stake,
            "CuotaSimulada": (
                settlement_odds
            ),
            "GananciaNeta": (
                profit
            ),
        })

    bets = pd.DataFrame(
        rows
    )

    # Si hay más de max_bets, V9 toma los de mayor score.
    if (
        not bets.empty
        and len(
            bets
        )
        > max_bets
    ):
        bets = (
            bets.sort_values(
                [
                    "ScoreV9",
                    "P_LCB",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
            .head(
                max_bets
            )
            .sort_values(
                [
                    "Fecha",
                    "Competicion",
                ]
            )
            .reset_index(
                drop=True
            )
        )

    if bets.empty:
        summary = {
            "start": str(
                test_start.date()
            ),
            "end": str(
                test_end.date()
            ),
            "bets": 0,
            "wins": 0,
            "losses": 0,
            "hit_rate": np.nan,
            "staked": 0.0,
            "gross_return": 0.0,
            "net": 0.0,
            "roi": np.nan,
            "max_drawdown": 0.0,
            "longest_losing_streak": 0,
            "settlement_odds": settlement_odds,
            "stake": stake,
            "days": days,
            "break_even": (
                1.0
                / settlement_odds
            ),
            "note": (
                "Ningún builder V9 pasó los filtros "
                "económicos a la cuota simulada elegida."
            ),
        }

        return (
            bets,
            summary,
            pd.DataFrame(),
            pd.DataFrame(),
        )

    bets = bets.sort_values(
        [
            "Fecha",
            "Competicion",
        ]
    ).reset_index(
        drop=True
    )

    wins = int(
        (
            bets[
                "Resultado"
            ]
            == "GANADA"
        ).sum()
    )

    losses = int(
        len(
            bets
        )
        - wins
    )

    staked = float(
        bets[
            "Stake"
        ].sum()
    )

    net = float(
        bets[
            "GananciaNeta"
        ].sum()
    )

    gross_return = (
        staked
        + net
    )

    roi = (
        net
        / staked
        if staked > 0
        else np.nan
    )

    hit_rate = (
        wins
        / len(
            bets
        )
        if len(
            bets
        )
        else np.nan
    )

    max_dd = (
        _max_drawdown_from_profits(
            bets[
                "GananciaNeta"
            ].tolist()
        )
    )

    losing_streak = (
        _longest_losing_streak(
            bets[
                "Resultado"
            ].tolist()
        )
    )

    summary = {
        "start": str(
            test_start.date()
        ),
        "end": str(
            test_end.date()
        ),
        "bets": int(
            len(
                bets
            )
        ),
        "wins": wins,
        "losses": losses,
        "hit_rate": float(
            hit_rate
        ),
        "staked": staked,
        "gross_return": float(
            gross_return
        ),
        "net": net,
        "roi": float(
            roi
        ),
        "max_drawdown": max_dd,
        "longest_losing_streak": losing_streak,
        "settlement_odds": settlement_odds,
        "stake": stake,
        "days": days,
        "break_even": (
            1.0
            / settlement_odds
        ),
        "note": (
            "Simulación a cuota fija de referencia. "
            "No sustituye la cuota histórica real del Bet Builder."
        ),
    }

    by_comp = (
        bets.groupby(
            "Competicion",
            dropna=False,
        )
        .agg(
            Apuestas=(
                "Resultado",
                "size",
            ),
            Ganadas=(
                "Resultado",
                lambda s: int(
                    (
                        s
                        == "GANADA"
                    ).sum()
                ),
            ),
            Apostado=(
                "Stake",
                "sum",
            ),
            Ganancia=(
                "GananciaNeta",
                "sum",
            ),
        )
        .reset_index()
    )

    by_comp[
        "HitRate"
    ] = (
        by_comp[
            "Ganadas"
        ]
        / by_comp[
            "Apuestas"
        ]
    )

    by_comp[
        "ROI"
    ] = (
        by_comp[
            "Ganancia"
        ]
        / by_comp[
            "Apostado"
        ]
    )

    by_niche = (
        bets.groupby("Variante", dropna=False)
        .agg(
            Apuestas=("Resultado", "size"),
            Ganadas=("Resultado", lambda s: int((s == "GANADA").sum())),
            Apostado=("Stake", "sum"),
            Ganancia=("GananciaNeta", "sum"),
            ProbModeloMedia=("P_Modelo", "mean"),
            LCBModeloMedia=("P_LCB", "mean"),
        )
        .reset_index()
    )

    by_niche["HitRate"] = by_niche["Ganadas"] / by_niche["Apuestas"]
    by_niche["HitRateLCB"] = [
        _wilson_lower(w / n, n, z=1.28) if n else np.nan
        for w, n in zip(by_niche["Ganadas"], by_niche["Apuestas"])
    ]
    by_niche["ROI"] = by_niche["Ganancia"] / by_niche["Apostado"]
    break_even = 1.0 / settlement_odds
    by_niche["EstadoNicho"] = np.where(
        by_niche["Apuestas"] < 20,
        "MUESTRA_BAJA",
        np.where(
            by_niche["HitRateLCB"] > break_even,
            "VALIDADO_EN_VENTANA",
            "NO_VALIDADO",
        ),
    )

    return (
        bets,
        summary,
        by_comp,
        by_niche,
    )


def backtest_v9_last_7_days(
    stake=100.0,
    settlement_odds=4.20,
    max_bets=30,
    end_date=None,
):
    """Compatibilidad con llamadas de la interfaz V9 original."""
    bets, summary, by_comp, _ = backtest_v9_window(
        stake=stake,
        settlement_odds=settlement_odds,
        max_bets=max_bets,
        end_date=end_date,
        days=7,
    )
    return bets, summary, by_comp
