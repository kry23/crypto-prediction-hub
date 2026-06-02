from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics


def _insert(conn, pid: str, status: str, prediction: str, actual: float,
            target: float, regime: str, validated_at_iso: str):
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status,
            actual_outcome, validated_at, created_at)
        VALUES (?, 'X', 24, ?, 0.6, ?, 0.018, 'NORMAL', ?, 'v1.5', 'v1.5.4',
                ?, ?, ?, ?)
    """, (pid, prediction, target, regime, status, actual,
          validated_at_iso, validated_at_iso))


def test_update_rolling_metrics_populates_table(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    # 10 'up' predictions in BULL regime, 7 correct (hit rate 70%)
    for i in range(10):
        _insert(conn, f"u{i}",
                "correct" if i < 7 else "incorrect",
                "up", 0.02 if i < 7 else -0.01,
                0.03, "BULL",
                (now - timedelta(hours=24 + i)).isoformat())
    conn.commit()
    conn.close()

    update_rolling_metrics(predictions_db=db, now=now)

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT window, regime, direction, hit_rate, n_predictions "
        "FROM metrics_rolling ORDER BY window, regime, direction"
    ).fetchall()
    conn.close()

    assert len(rows) > 0
    by_key = {(r[0], r[1], r[2]): r for r in rows}
    assert ("7d", "BULL", "long") in by_key
    win, regime, dir_, hit, n = by_key[("7d", "BULL", "long")]
    assert abs(hit - 0.7) < 0.001
    assert n == 10
