from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_predictor.patterns.pattern_detector import detect_and_upsert_patterns
from crypto_predictor.storage.predictions_db import init_db


def _insert_pred(conn, pid, status, prediction, regime, flag,
                  validated_at_iso):
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status,
            validated_at, created_at)
        VALUES (?, 'X', 24, ?, 0.7, 0.03, 0.021, ?, ?, 'v1.5', 'v1.5.4',
                ?, ?, ?)
    """, (pid, prediction, flag, regime, status,
          validated_at_iso, validated_at_iso))


def test_detect_patterns_populates_table(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    now = datetime(2026, 6, 2, tzinfo=timezone.utc)
    # 10 HIGH_CONV BULL — 7 correct (70%)
    for i in range(10):
        _insert_pred(conn, f"hc{i}",
                     "correct" if i < 7 else "incorrect",
                     "up", "BULL", "HIGH_CONV",
                     (now - timedelta(hours=24 + i)).isoformat())
    conn.commit()
    conn.close()

    n_patterns = detect_and_upsert_patterns(predictions_db=db, now=now)
    assert n_patterns >= 1

    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT name, win_rate, recommendation FROM patterns"
    ).fetchall()
    conn.close()
    names = {r[0] for r in rows}
    assert any("HIGH_CONV" in n and "BULL" in n for n in names)
    # The 70% pattern should be SEEK
    seek_rows = [r for r in rows if r[2] == "SEEK"]
    assert any(abs(r[1] - 0.7) < 0.01 for r in seek_rows)
