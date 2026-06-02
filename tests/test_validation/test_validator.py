# tests/test_validation/test_validator.py
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.validator import validate_pending_predictions


def _seed_ohlcv_with_pump(root: Path, sym: str, asof_ms: int):
    """Seed 1h bars so that price at asof+24h is 2% higher than at asof."""
    rows = []
    for i in range(72):
        ts = asof_ms - 24 * 3600 * 1000 + i * 3600 * 1000
        # Step price up by 2% exactly 24 bars in
        p = 100.0 * (1.02 if i >= 48 else 1.0)
        rows.append({"timestamp": ts, "open": p, "high": p * 1.01,
                     "low": p * 0.99, "close": p, "volume": 1000})
    write_ohlcv(root, sym, "1h", pd.DataFrame(rows))


def test_validator_closes_correct_up_prediction(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    sym = "BTC-USDT-SWAP"
    asof_dt = datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc)
    asof_ms = int(asof_dt.timestamp() * 1000)
    _seed_ohlcv_with_pump(tmp_path, sym, asof_ms)

    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('test1', ?, 24, 'up', 0.78, 0.02, 0.016, 'HIGH_CONV',
                'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (sym, asof_dt.isoformat()))
    conn.commit()
    conn.close()

    now = asof_dt + timedelta(hours=25)
    n_closed = validate_pending_predictions(
        predictions_db=db, history_root=tmp_path, now=now,
    )
    assert n_closed == 1

    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status, actual_outcome, validated_at FROM predictions WHERE id='test1'"
    ).fetchone()
    conn.close()
    assert row[0] == "correct"
    # Price moved ~+2%, so actual_outcome log(1.02) ≈ 0.0198
    assert abs(row[1] - math.log(1.02)) < 0.001
    assert row[2] is not None


def test_validator_marks_expired_when_data_missing(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    sym = "ABC-USDT-SWAP"  # NO ohlcv seeded
    asof_dt = datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc)
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('test2', ?, 24, 'up', 0.6, 0.03, 0.018, 'NORMAL',
                'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (sym, asof_dt.isoformat()))
    conn.commit()
    conn.close()

    now = asof_dt + timedelta(hours=25)
    n_closed = validate_pending_predictions(
        predictions_db=db, history_root=tmp_path, now=now,
    )
    # Missing data: status becomes 'expired'
    assert n_closed == 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status FROM predictions WHERE id='test2'"
    ).fetchone()
    conn.close()
    assert row[0] == "expired"


def test_validator_leaves_too_recent_predictions_alone(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    asof_dt = datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc)
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('test3', 'X', 24, 'up', 0.6, 0.03, 0.018, 'NORMAL',
                'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (asof_dt.isoformat(),))
    conn.commit()
    conn.close()
    now = asof_dt + timedelta(hours=12)  # only 12h elapsed
    n_closed = validate_pending_predictions(
        predictions_db=db, history_root=tmp_path, now=now,
    )
    assert n_closed == 0
