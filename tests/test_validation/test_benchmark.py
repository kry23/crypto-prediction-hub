from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.rolling_metrics import (
    compute_top_k_alpha, update_rolling_metrics,
)


def test_compute_top_k_alpha_positive_when_topk_beats():
    universe = [0.0, 0.0, 0.0, 0.0, 0.0]
    top_k = [0.05, 0.04, 0.03]
    alpha = compute_top_k_alpha(top_k, universe)
    assert alpha > 0


def test_update_rolling_metrics_populates_topk_alpha(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    for i, actual in enumerate([0.05, 0.04, 0.03, -0.01, -0.02]):
        conn.execute("""
            INSERT INTO predictions (id, symbol, horizon_hours, prediction,
                p_direction, target_value, composite_score, confidence_flag,
                regime, formula_version, calibration_version, status,
                actual_outcome, validated_at, created_at)
            VALUES (?, 'X', 24, 'up', 0.7, 0.04, 0.028, 'NORMAL', 'BULL',
                    'v1.5', 'v1.5.4', 'correct', ?, ?, ?)
        """, (f"p{i}", actual,
              (now - timedelta(hours=24 + i)).isoformat(),
              (now - timedelta(hours=24 + i)).isoformat()))
    conn.commit()
    conn.close()

    update_rolling_metrics(predictions_db=db, now=now)

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT topk_alpha FROM metrics_rolling "
        "WHERE window='7d' AND regime='BULL' AND direction='long'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is not None
