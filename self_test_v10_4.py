"""Pruebas offline de las protecciones adaptativas V10.4."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

import adaptive_monitor as adaptive
import gatuno_audit as audit
import bet_builder_v8_1_robust as base


NOW = pd.Timestamp("2026-09-16T15:00:00Z")


def make_history(n: int, hits: int, code: str = "H1_CORNERS_OU45") -> pd.DataFrame:
    rows = []
    for index in range(n):
        kickoff = NOW - pd.Timedelta(days=index % 7, hours=4)
        rows.append({
            "PredictionID": f"p-{code}-{index}",
            "EventKey": f"e-{index}",
            "EventID": str(index),
            "KickoffUTC": kickoff.isoformat(),
            "Fecha": str(kickoff.date()),
            "Mercado": adaptive.MARKET_LABELS[code],
            "MercadoCodigo": code,
            "Pronostico": "MAS DE 4.5",
            "Probabilidad": 0.75,
            "SemaforoFinal": "VERDE",
            "EstadoResultado": "ACERTADO" if index < hits else "FALLADO",
            "EmitidoEnUTC": (kickoff - pd.Timedelta(hours=8)).isoformat(),
        })
    return pd.DataFrame(rows)


def market_frame(signal: str = "VERDE") -> pd.DataFrame:
    return pd.DataFrame([{
        "EventID": "future-1",
        "KickoffUTC": (NOW + pd.Timedelta(days=1)).isoformat(),
        "Local": "Gatos FC",
        "Visitante": "Felinos United",
        "Mercado": "Corners 1.er tiempo",
        "MercadoCodigo": "H1_CORNERS_OU45",
        "Pronostico": "MAS DE 4.5",
        "PronosticoCodigo": "OVER",
        "Probabilidad": 0.70,
        "PConservadora": 0.60,
        "Fiabilidad": 0.67,
        "Soporte": 60,
        "Semaforo": signal,
        "SemaforoFinal": signal,
        "MejorOpcion": signal == "VERDE",
    }])


def test_small_sample_does_not_alert() -> None:
    diagnostics = adaptive.analyze_markets(make_history(12, 2), now=NOW)
    row = diagnostics.iloc[0]
    assert row["Estado"] == "SIN_MUESTRA"
    assert row["AccionPropuesta"] == "SEGUIR_RECOLECTANDO"


def test_persistent_failure_creates_proposal() -> None:
    with TemporaryDirectory() as directory:
        proposals_path = Path(directory) / "proposals.csv"
        diagnostics, proposals = adaptive.update_proposals(
            make_history(35, 10), proposals_path=proposals_path, now=NOW
        )
        assert diagnostics.iloc[0]["Estado"] in {"ALERTA", "CRITICA"}
        assert len(proposals) == 1
        assert proposals.iloc[0]["Estado"] == "PENDIENTE"


def test_observe_keeps_policy_empty() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        proposals_path = root / "proposals.csv"
        policy_path = root / "policy.json"
        decisions_path = root / "decisions.csv"
        _, proposals = adaptive.update_proposals(make_history(35, 10), proposals_path, now=NOW)
        adaptive.decide_proposal(
            proposals.iloc[0]["ProposalID"], "OBSERVAR_7_DIAS",
            proposals_path, policy_path, decisions_path, now=NOW,
        )
        assert adaptive.load_policy(policy_path)["markets"] == {}
        stored = adaptive.load_proposals(proposals_path)
        assert stored.iloc[0]["Estado"] == "OBSERVANDO"


def test_confirmed_adjustment_only_downgrades() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        proposals_path = root / "proposals.csv"
        policy_path = root / "policy.json"
        decisions_path = root / "decisions.csv"
        _, proposals = adaptive.update_proposals(make_history(35, 10), proposals_path, now=NOW)
        adaptive.decide_proposal(
            proposals.iloc[0]["ProposalID"], "APLICAR",
            proposals_path, policy_path, decisions_path, now=NOW,
        )
        policy = adaptive.load_policy(policy_path)
        adjusted = adaptive.apply_policy(market_frame("VERDE"), policy, now=NOW)
        assert adjusted.iloc[0]["SemaforoFinal"] == "AMARILLO"
        yellow = adaptive.apply_policy(market_frame("AMARILLO"), policy, now=NOW)
        assert yellow.iloc[0]["SemaforoFinal"] == "AMARILLO"


def test_revert_removes_active_rule() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        proposals_path = root / "proposals.csv"
        policy_path = root / "policy.json"
        decisions_path = root / "decisions.csv"
        _, proposals = adaptive.update_proposals(make_history(35, 10), proposals_path, now=NOW)
        adaptive.decide_proposal(
            proposals.iloc[0]["ProposalID"], "APLICAR",
            proposals_path, policy_path, decisions_path, now=NOW,
        )
        adaptive.revert_market("H1_CORNERS_OU45", policy_path, decisions_path, now=NOW)
        assert adaptive.load_policy(policy_path)["markets"] == {}


def test_sync_changes_only_future_pending_signal() -> None:
    with TemporaryDirectory() as directory:
        history_path = Path(directory) / "history.csv"
        markets = market_frame("AMARILLO")
        history, _ = audit.record_predictions(markets, history_path, now_utc=NOW)
        # Simular que la primera instantanea era verde antes de aplicar politica.
        history["SemaforoFinal"] = "VERDE"
        audit._atomic_csv(history, history_path)
        synced = audit.sync_future_signals(markets, history_path, now_utc=NOW)
        assert synced.iloc[0]["SemaforoFinal"] == "AMARILLO"
        assert synced.iloc[0]["EstadoResultado"] == "PENDIENTE"


def test_legacy_history_migration_preserves_result() -> None:
    with TemporaryDirectory() as directory:
        legacy_path = Path(directory) / "historial_apuestas.csv"
        pd.DataFrame([{
            "EventID": "legacy-1", "Fecha": "2026-09-10", "KickoffUTC": "2026-09-10T20:00:00Z",
            "CompKey": "arg", "Competicion": "Liga", "Local": "Gatos", "Visitante": "Perros",
            "Mercado": "Resultado 1X2", "Linea": "1X2", "Pronostico": "LOCAL",
            "Probabilidad": 0.61, "Semaforo": "VERDE", "Version": "V10.3",
            "RegistradoEn": "2026-09-10T10:00:00Z", "EstadoResultado": "ACERTADO",
            "ResultadoReal": "2-0", "ResueltoEn": "2026-09-10T23:00:00Z",
        }]).to_csv(legacy_path, index=False)
        migrated = audit._migrate_legacy_history(legacy_path)
        assert len(migrated) == 1
        assert migrated.iloc[0]["EstadoResultado"] == "ACERTADO"
        assert migrated.iloc[0]["MercadoCodigo"] == "RESULT_1X2"


def test_flat_bundled_history_fallback() -> None:
    with TemporaryDirectory() as directory:
        target = Path(directory) / "historical_fallback.csv.gz"
        pd.DataFrame([{
            "Date": "2026-09-01", "HomeTeam": "Gatos", "AwayTeam": "Perros",
            "FTHG": 2, "FTAG": 1, "HTHG": 1, "HTAG": 0,
        }]).to_csv(target, index=False, compression="gzip")
        before = base.BUNDLED_HISTORY_CANDIDATES
        try:
            base.BUNDLED_HISTORY_CANDIDATES = (Path(directory) / "missing.gz", target)
            loaded = base.cargar_historico_empaquetado()
        finally:
            base.BUNDLED_HISTORY_CANDIDATES = before
        assert len(loaded) == 1
        assert loaded.iloc[0]["HomeTeam"] == "Gatos"


def test_football_data_fixture_fallback() -> None:
    sample = (
        "Div,Date,Time,HomeTeam,AwayTeam,AvgH,AvgD,AvgA\n"
        "E0,18/09/2026,20:00,Cat FC,Dog United,1.90,3.30,4.10\n"
    ).encode()
    original = base.descargar_bytes
    try:
        base.descargar_bytes = lambda *args, **kwargs: sample
        fixtures = base.descargar_fixtures_football_data(
            pd.Timestamp("2026-09-17"), pd.Timestamp("2026-09-23")
        )
    finally:
        base.descargar_bytes = original
    assert len(fixtures) == 1
    assert fixtures.iloc[0]["CompKey"] == "ENG"
    assert fixtures.iloc[0]["FuenteFixture"] == "Football-Data fixtures"


def test_espn_short_window_uses_daily_recovery() -> None:
    calls = []
    original = base.descargar_json
    try:
        def fake_json(url, timeout=None):
            calls.append(url)
            if "-" in url.split("dates=")[-1].split("&")[0]:
                raise RuntimeError("intervalo rechazado")
            if "dates=20260918" in url:
                return {"events": [{"id": "cat-match"}]}
            return {"events": []}
        base.descargar_json = fake_json
        events = base.eventos_scoreboard_espn(
            "eng.1", pd.Timestamp("2026-09-17"), pd.Timestamp("2026-09-19")
        )
    finally:
        base.descargar_json = original
    assert [event["id"] for event in events] == ["cat-match"]
    assert len(calls) == 4


def run() -> None:
    tests = [
        test_small_sample_does_not_alert,
        test_persistent_failure_creates_proposal,
        test_observe_keeps_policy_empty,
        test_confirmed_adjustment_only_downgrades,
        test_revert_removes_active_rule,
        test_sync_changes_only_future_pending_signal,
        test_legacy_history_migration_preserves_result,
        test_flat_bundled_history_fallback,
        test_football_data_fixture_fallback,
        test_espn_short_window_uses_daily_recovery,
    ]
    for test in tests:
        test()
        print(f"OK: {test.__name__}")
    print(f"\n{len(tests)} pruebas V10.4 superadas.")


if __name__ == "__main__":
    run()
