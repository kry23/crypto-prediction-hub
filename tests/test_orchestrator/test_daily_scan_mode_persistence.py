"""Verify persist_predictions writes mode/completeness/missing_features columns."""
import sqlite3
from pathlib import Path

from crypto_predictor.storage.predictions_db import init_db


def test_persist_predictions_writes_mode_and_completeness(tmp_path: Path):
    """The prediction persistence path must persist the three new columns."""
    db = tmp_path / "predictions.db"
    init_db(db)
    pred = {
        "id": "p1", "symbol": "BTC/USDT:USDT", "horizon_hours": 24,
        "prediction": "up", "p_direction": 0.65, "target_value": 0.02,
        "composite_score": 0.013, "confidence_flag": "NORMAL",
        "regime": "BULL", "formula_version": "v1.5",
        "calibration_version": "v1.5.4", "status": "pending",
        "created_at": "2026-06-04T06:00:00+00:00",
        "mode": "shadow",
        "feature_completeness": "degraded",
        "missing_features": "sentiment,global",
    }
    from crypto_predictor.orchestrator.daily_scan import persist_predictions
    persist_predictions(predictions_db=db, predictions=[pred])
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT mode, feature_completeness, missing_features "
        "FROM predictions WHERE id='p1'"
    ).fetchone()
    conn.close()
    assert row == ("shadow", "degraded", "sentiment,global")


def test_persist_predictions_defaults_to_live_full(tmp_path: Path):
    """A prediction dict missing the new keys still inserts with safe defaults."""
    db = tmp_path / "predictions.db"
    init_db(db)
    pred = {
        "id": "p2", "symbol": "ETH/USDT:USDT", "horizon_hours": 24,
        "prediction": "down", "p_direction": 0.62, "target_value": -0.018,
        "composite_score": 0.011, "confidence_flag": "NORMAL",
        "regime": "BULL", "formula_version": "v1.5",
        "calibration_version": "v1.5.4", "status": "pending",
        "created_at": "2026-06-04T06:00:00+00:00",
        # mode + completeness intentionally absent
    }
    from crypto_predictor.orchestrator.daily_scan import persist_predictions
    persist_predictions(predictions_db=db, predictions=[pred])
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT mode, feature_completeness, missing_features "
        "FROM predictions WHERE id='p2'"
    ).fetchone()
    conn.close()
    assert row == ("live", "full", None)
