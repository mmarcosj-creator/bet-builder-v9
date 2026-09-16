"""Actualizacion no interactiva de los archivos que consume Streamlit."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import pandas as pd

import bet_builder_v8_1_robust as base
import bet_forecaster_v10 as v10


DATA_DIR = Path("app_data_v10")


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    matches, markets, metrics, start, end = v10.run_v10()
    matches.to_csv(DATA_DIR / "latest_matches.csv", index=False, encoding="utf-8-sig")
    markets.to_csv(DATA_DIR / "latest_markets.csv", index=False, encoding="utf-8-sig")
    metrics.to_csv(DATA_DIR / "latest_validation.csv", index=False, encoding="utf-8-sig")
    metadata = {
        "generated_at": datetime.now(base.TZ_PERU).isoformat(),
        "window_start": str(pd.Timestamp(start).date()),
        "window_end": str(pd.Timestamp(end).date()),
        "matches": int(len(matches)),
        "markets": int(len(markets)),
        "version": v10.VERSION,
    }
    (DATA_DIR / "meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
