"""Actualizacion no interactiva de los archivos que consume Streamlit."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path

import pandas as pd

import bet_builder_v8_1_robust as base
import bet_forecaster_v10 as v10
import gatuno_audit as audit
import adaptive_monitor as adaptive
import model_monitor as quality_monitor


DATA_DIR = Path("app_data_v10")


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    os.replace(temporary, path)


def filter_not_started(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or "KickoffUTC" not in frame:
        return frame
    kickoff = pd.to_datetime(frame["KickoffUTC"], utc=True, errors="coerce")
    return frame[kickoff.notna() & (kickoff > pd.Timestamp.now(tz="UTC"))].reset_index(drop=True)


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    history, closure = audit.resolve_pending()
    matches, markets, metrics, start, end = v10.run_v10()
    matches = filter_not_started(matches)
    markets = filter_not_started(markets)
    markets = audit.adaptive_safety_gate(markets, history)
    markets = adaptive.apply_policy(markets, adaptive.load_policy())
    history, recording = audit.record_predictions(markets)
    adaptive.update_proposals(history)
    atomic_csv(matches, DATA_DIR / "latest_matches.csv")
    atomic_csv(markets, DATA_DIR / "latest_markets.csv")
    atomic_csv(metrics, DATA_DIR / "latest_validation.csv")
    try:
        quality_monitor.registrar_metricas(metrics, DATA_DIR / "model_metrics_log.csv")
    except Exception:
        pass
    metadata = {
        "generated_at": datetime.now(base.TZ_PERU).isoformat(),
        "window_start": str(pd.Timestamp(start).date()),
        "window_end": str(pd.Timestamp(end).date()),
        "matches": int(len(matches)),
        "markets": int(len(markets)),
        "version": v10.VERSION,
        "audit_closed": int(closure.get("cerrados", 0)),
        "audit_inserted": int(recording.get("insertados", 0)),
    }
    meta_target = DATA_DIR / "meta.json"
    meta_temporary = meta_target.with_suffix(".json.tmp")
    meta_temporary.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(meta_temporary, meta_target)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
