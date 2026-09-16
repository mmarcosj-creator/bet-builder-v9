"""Pruebas offline de las protecciones críticas de V10.3 Gatuno PRO."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import bet_forecaster_v10 as v10
import gatuno_audit as audit


def sample_markets(kickoff: str = "2099-01-01T18:00:00Z") -> pd.DataFrame:
    common = {
        "Fecha": "2099-01-01",
        "KickoffUTC": kickoff,
        "EventID": "999001",
        "HomeESPNID": "10",
        "AwayESPNID": "20",
        "HoraPeru": "13:00",
        "CompKey": "ARG",
        "Competicion": "Prueba",
        "Local": "Gatos FC",
        "Visitante": "Felinos United",
        "Linea": "0.5",
        "Probabilidad": 0.74,
        "PConservadora": 0.65,
        "Fiabilidad": 0.76,
        "Soporte": 88,
        "ModeloSuperaBase": True,
        "Semaforo": "VERDE",
        "SemaforoModelo": "VERDE",
        "SemaforoFinal": "VERDE",
        "EstadoAlineacion": "CONFIRMADA",
        "RiesgoRotacion": "BAJO",
        "Version": v10.VERSION,
    }
    return pd.DataFrame([
        {**common, "Mercado": "Resultado 1X2", "MercadoCodigo": "RESULT_1X2", "Pronostico": "LOCAL", "PronosticoCodigo": "HOME"},
        {**common, "Mercado": "Goles Gatos FC", "MercadoCodigo": "HOME_SCORE_OU05", "Pronostico": "MARCA 1+", "PronosticoCodigo": "YES"},
    ])


def test_oos_guard() -> None:
    assert v10._validated_signal("VERDE", "ALTA", False) == ("ROJO", "NO SUPERA BASE OOS")
    assert v10._validated_signal("AMARILLO", "MEDIA", True) == ("AMARILLO", "MEDIA")


def test_immutable_history() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "history.csv"
        markets = sample_markets()
        first, first_stats = audit.record_predictions(
            markets, path=path, now_utc=pd.Timestamp("2098-12-31T00:00:00Z")
        )
        second_input = markets.copy()
        second_input["Pronostico"] = "VISITANTE"
        second_input["PronosticoCodigo"] = "AWAY"
        second, second_stats = audit.record_predictions(
            second_input, path=path, now_utc=pd.Timestamp("2098-12-31T01:00:00Z")
        )
        assert first_stats["insertados"] == 2
        assert second_stats["insertados"] == 0
        assert len(first) == len(second) == 2
        assert second.iloc[0]["PronosticoCodigo"] == "HOME"

        transitioned = markets.copy()
        transitioned["SemaforoFinal"] = "AMARILLO"
        transitioned["Semaforo"] = "AMARILLO"
        third, third_stats = audit.record_predictions(
            transitioned, path=path, now_utc=pd.Timestamp("2098-12-31T02:00:00Z")
        )
        assert third_stats["insertados"] == 2
        assert len(third) == 4


def test_grading_all_markets() -> None:
    observed = {
        "HomeGoals": 2,
        "AwayGoals": 1,
        "H1Goals": 1,
        "H1Corners": 5,
        "YellowCards": 6,
    }
    cases = [
        ("RESULT_1X2", "HOME", "ACERTADO"),
        ("H1_GOALS_OU15", "UNDER", "ACERTADO"),
        ("H1_CORNERS_OU45", "OVER", "ACERTADO"),
        ("YELLOW_CARDS_OU45", "OVER", "ACERTADO"),
        ("HOME_SCORE_OU05", "YES", "ACERTADO"),
        ("AWAY_SCORE_OU05", "YES", "ACERTADO"),
    ]
    for market, prediction, expected in cases:
        status, _ = audit._grade(
            pd.Series({"MercadoCodigo": market, "PronosticoCodigo": prediction}), observed
        )
        assert status == expected


def test_safety_gate_and_best_option() -> None:
    markets = sample_markets()
    markets.loc[1, "ModeloSuperaBase"] = False
    gated = audit.adaptive_safety_gate(markets, pd.DataFrame())
    assert gated.loc[1, "SemaforoFinal"] == "ROJO"
    assert int(gated["MejorOpcion"].sum()) == 1

    unconfirmed = sample_markets()
    unconfirmed["EstadoAlineacion"] = "NO_DISPONIBLE"
    gated_unconfirmed = audit.adaptive_safety_gate(unconfirmed, pd.DataFrame())
    assert set(gated_unconfirmed["SemaforoFinal"]) == {"AMARILLO"}
    assert not gated_unconfirmed["MejorOpcion"].any()


def test_audit_no_fake_zero() -> None:
    history = pd.DataFrame([{"EstadoResultado": "PENDIENTE"}])
    summary, _ = audit.audit_summary(history)
    assert summary["evaluated"] == 0
    assert np.isnan(summary["green_accuracy"])
    assert "SIN RESULTADOS EVALUADOS" in summary["message"]


def main() -> None:
    tests = [
        test_oos_guard,
        test_immutable_history,
        test_grading_all_markets,
        test_safety_gate_and_best_option,
        test_audit_no_fake_zero,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} pruebas críticas superadas — {v10.VERSION}")


if __name__ == "__main__":
    main()
