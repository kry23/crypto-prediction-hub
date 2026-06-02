"""Show rolling track record from the predictions database."""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(os.environ.get(
        "CRYPTO_PREDICTOR_ROOT",
        Path(__file__).resolve().parents[1],
    ))
    db = project_root / "predictions.db"
    if not db.exists():
        print(f"No predictions.db at {db}")
        return 1
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT window, regime, direction, hit_rate, mae, n_predictions, updated_at "
            "FROM metrics_rolling ORDER BY window, regime, direction"
        ).fetchall()
        if not rows:
            print("No metrics_rolling rows yet. Run validate_pending + weekly_metrics first.")
            return 0
        print("Rolling track record:")
        print(f"{'Window':<6} {'Regime':<6} {'Dir':<6} {'Hit':<8} {'MAE':<8} {'n':<6} {'Updated':<25}")
        for window, regime, direction, hit, mae, n, updated in rows:
            print(f"{window:<6} {regime:<6} {direction:<6} "
                  f"{hit*100:>6.1f}% {(mae or 0)*100:>6.2f}% {n:<6} {updated}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
