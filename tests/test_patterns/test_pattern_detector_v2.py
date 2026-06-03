import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_predictor.patterns.pattern_detector import detect_feature_patterns
from crypto_predictor.storage.predictions_db import init_db


def test_detect_feature_patterns_finds_high_win_combos(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    conn = sqlite3.connect(db)
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    # 10 predictions: all with funding_z < -2 and oi_growth_z > 1, 8 correct (80%)
    for i in range(10):
        pred_id = f"p{i}"
        validated_at = (now - timedelta(hours=24 + i)).isoformat()
        status = "correct" if i < 8 else "incorrect"
        conn.execute("""
            INSERT INTO predictions (id, symbol, horizon_hours, prediction,
                p_direction, target_value, composite_score, confidence_flag,
                regime, formula_version, calibration_version, status,
                validated_at, created_at)
            VALUES (?, 'X', 24, 'up', 0.78, 0.05, 0.039, 'NORMAL', 'BULL',
                    'v1.5', 'v1.5.4', ?, ?, ?)
        """, (pred_id, status, validated_at, validated_at))
        conn.execute(
            "INSERT INTO predictions_features VALUES (?, 'funding_z', -2.5, NULL)",
            (pred_id,),
        )
        conn.execute(
            "INSERT INTO predictions_features VALUES (?, 'oi_growth_z', 1.5, NULL)",
            (pred_id,),
        )
    conn.commit()
    conn.close()

    n = detect_feature_patterns(predictions_db=db, now=now)
    assert n >= 1
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT name, win_rate, recommendation FROM patterns WHERE name LIKE 'feat:%'"
    ).fetchall()
    conn.close()
    assert len(rows) >= 1
    assert any(r[1] >= 0.7 for r in rows)
