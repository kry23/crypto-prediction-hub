"""Close pending predictions against realized returns."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import structlog

from crypto_predictor.scoring.returns import actual_return

log = structlog.get_logger(__name__)


def validate_pending_predictions(*, predictions_db: Path,
                                  history_root: Path,
                                  now: datetime) -> int:
    """Close pending predictions whose horizon has elapsed. Returns count closed."""
    conn = sqlite3.connect(str(predictions_db))
    try:
        rows = conn.execute(
            "SELECT id, symbol, horizon_hours, prediction, target_value, created_at "
            "FROM predictions WHERE status = 'pending'"
        ).fetchall()
        n_closed = 0
        for pred_id, symbol, horizon_hours, prediction, target_value, created_at in rows:
            created_dt = datetime.fromisoformat(created_at)
            elapsed = now - created_dt
            if elapsed < timedelta(hours=horizon_hours):
                continue

            actual = actual_return(
                root=history_root, symbol=symbol,
                start_time=created_dt, horizon_hours=horizon_hours,
            )
            if actual is None:
                conn.execute(
                    "UPDATE predictions SET status='expired', validated_at=? "
                    "WHERE id=?",
                    (now.isoformat(), pred_id),
                )
                n_closed += 1
                continue

            correct = (
                (prediction == "up" and actual > 0)
                or (prediction == "down" and actual < 0)
            )
            error_margin = abs(target_value - actual) if target_value else None
            evaluation = (
                f"dir={'OK' if correct else 'FAIL'}; "
                f"actual={actual:+.4f}; predicted={target_value:+.4f}"
            )
            conn.execute(
                "UPDATE predictions SET status=?, actual_outcome=?, "
                "error_margin=?, evaluation=?, validated_at=? WHERE id=?",
                ("correct" if correct else "incorrect",
                 actual, error_margin, evaluation, now.isoformat(),
                 pred_id),
            )
            n_closed += 1
        conn.commit()
        return n_closed
    finally:
        conn.close()
