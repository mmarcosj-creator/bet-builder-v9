"""Auditoria temporal reproducible de V10 con una muestra aleatoria de 100."""

from __future__ import annotations

import json
from pathlib import Path

import bet_builder_v8_1_robust as base
import bet_forecaster_v10 as v10


OUTPUT = Path("self_test_output")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    history = base.descargar_historico_total()
    dataset, _ = v10.build_feature_dataset(history)
    bundle = v10.train_models(dataset)
    detail, summary = v10.temporal_backtest_sample(
        dataset,
        n_matches=100,
        random_seed=20260916,
    )

    bundle.metrics.to_csv(OUTPUT / "validacion_temporal.csv", index=False, encoding="utf-8-sig")
    detail.to_csv(OUTPUT / "muestra_100_detalle.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUTPUT / "muestra_100_resumen.csv", index=False, encoding="utf-8-sig")
    metadata = {
        "version": v10.VERSION,
        "historical_matches": int(len(history)),
        "feature_rows": int(len(dataset)),
        "trained_through": str(bundle.trained_through),
        "sample_matches": int(detail[["Fecha", "Local", "Visitante"]].drop_duplicates().shape[0]),
        "note": "No se calcula ganancia sin cuotas reales historicas completas.",
    }
    (OUTPUT / "meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
