
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

import bet_builder_v9_3_context_optimizer as v9
import bet_builder_v8_1_robust as base

DATA_DIR = Path("app_data_v9_3")
DATA_DIR.mkdir(exist_ok=True)

DATA_FILE = DATA_DIR / "latest_v9_3.csv"
META_FILE = DATA_DIR / "meta_v9_3.json"

def main():
    df, start, end = v9.run_v9()

    df.to_csv(
        DATA_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    meta = {
        "generated_at": datetime.now(base.TZ_PERU).isoformat(),
        "window_start": str(pd.Timestamp(start).date()),
        "window_end": str(pd.Timestamp(end).date()),
        "rows": int(len(df)),
        "version": v9.VERSION,
    }

    META_FILE.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
