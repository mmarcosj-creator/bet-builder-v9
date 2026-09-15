"""Pruebas rápidas sin descargar datos externos."""

import numpy as np
import pandas as pd

import bet_builder_v9_3_context_optimizer as v9
import bet_builder_v9_3_context as ctx


def main():
    assert all(v9.compatible(legs) for _, legs in v9.TEMPLATES)
    assert all(code in v9.MARKETS for _, legs in v9.TEMPLATES for code in legs)
    assert v9.book_leg_count(["FAV_C4_7", "UNDER35", "CARDS_U65"]) == 4
    assert "BTTS_CONTROL" not in {name for name, _ in v9.TEMPLATES}
    assert max(v9.book_leg_count(legs) for _, legs in v9.TEMPLATES) <= 3

    rng = np.random.default_rng(92)
    n = 140
    dates = pd.date_range("2024-01-01", periods=n, freq="4D")
    fav_corners = rng.poisson(5.2, n)
    goals = rng.poisson(2.5, n)
    cards = rng.poisson(4.7, n)

    sample = pd.DataFrame({
        "Date": dates,
        "Y_FAV_C4_7": ((fav_corners >= 4) & (fav_corners <= 7)).astype(int),
        "Y_UNDER35": (goals <= 3).astype(int),
        "Y_CARDS_U65": (cards <= 6).astype(int),
    })

    knn = {
        "scope": sample,
        "neighbors": sample.tail(101).copy(),
        "weights": np.ones(101, dtype=float),
        "target_date": pd.Timestamp("2026-01-01"),
    }

    stats = v9.combo_probability(
        knn,
        ["FAV_C4_7", "UNDER35", "CARDS_U65"],
    )
    assert stats is not None
    assert 0 < stats["lcb"] <= stats["p"] < 1
    assert stats["support"] == 101
    assert stats["dependence_level"] in {"BAJA", "MEDIA", "ALTA"}

    row = {
        "P_Conjunta": 0.32,
        "P_LCB": 0.27,
        "CuotaRequerida": 4.20,
        "CuotaJustaModelo": 3.125,
        "FirmaCombinacion": ctx.exact_selection_signature(
            ["DOG_GOAL", "FAV_C4", "UNDER45"]
        ),
        "EstadoPreCuota": "COTIZAR",
        "CupoCartera": True,
    }
    assert v9.validate_real_quote(row, 4.20)["status"] == "CONFIRMAR_COMBINACION"
    assert v9.validate_real_quote(row, 4.10, True)["status"] == "DESCARTAR_CUOTA"
    assert v9.validate_real_quote(row, 4.20, True)["status"] == "VALIDA"
    assert v9.validate_real_quote(
        row, 4.20, True, "FIRMA-DISTINTA"
    )["status"] == "COMBINACION_MODIFICADA"

    profile = ctx.stage_profile("UCL", "COPA", "Semi-finals - second leg")
    assert profile["stage"] == "SEMIFINAL" and profile["importance"] >= 94
    profile = ctx.stage_profile("LIB", "COPA", "Quarter-finals - second leg")
    assert profile["stage"] == "CUARTOS" and profile["importance"] >= 90

    fixture = {
        "Date": pd.Timestamp("2026-09-15"),
        "CompKey": "ESP",
        "TipoCompeticion": "LIGA",
        "HomeOriginal": "Equipo A",
        "AwayOriginal": "Equipo B",
        "EventID": "current",
        "StageText": "Regular Season",
    }
    calendar = {
        "equipo a": [{
            "date": pd.Timestamp("2026-09-18"),
            "comp_key": "UCL", "competition": "Champions League",
            "event_id": "next", "importance": 94,
            "stage": "SEMIFINAL", "source": "CALENDARIO",
        }],
    }
    load = {"DaysRest": 3, "Matches7": 2, "Matches14": 4, "Phase": "STABLE"}
    calm = {"DaysRest": 7, "Matches7": 1, "Matches14": 2, "Phase": "STABLE"}
    c = ctx.evaluate_fixture_context(
        fixture, "Equipo A", "Equipo B", load, calm, "HOME", calendar
    )
    assert c["rotation_risk"] == "ALTO"
    assert ctx.candidate_guard(
        "FAV_DOMINIO", ["FAV_WIN", "FAV_C4", "UNDER45"], c
    )["blocked"]

    usual = [f"Jugador {i}" for i in range(1, 12)]
    history = [
        {
            "event_id": f"old{i}",
            "date": f"2026-09-0{i+1}",
            "team": "Equipo A",
            "starters": usual,
        }
        for i in range(3)
    ]
    xi = ctx.lineup_strength_profile(
        history, "Equipo A", usual, pd.Timestamp("2026-09-15"), "current"
    )
    assert xi["status"] == "ONCE_HABITUAL" and xi["continuity"] == 1.0
    rotated = ["Jugador 1", "Jugador 2", "Jugador 3"] + [
        f"Suplente {i}" for i in range(1, 9)
    ]
    xi = ctx.lineup_strength_profile(
        history, "Equipo A", rotated, pd.Timestamp("2026-09-15"), "current"
    )
    assert xi["status"] == "ROTACION_ALTA"

    print(
        f"OK {v9.VERSION}: {len(v9.MARKETS)} mercados, "
        f"{len(v9.TEMPLATES)} plantillas, P={stats['p']:.3f}, "
        f"LCB={stats['lcb']:.3f}."
    )


if __name__ == "__main__":
    main()
