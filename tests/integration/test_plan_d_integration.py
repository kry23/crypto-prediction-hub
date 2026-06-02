"""Plan D end-to-end: validator + rolling metrics on real BTC data."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_predictor.storage.predictions_db import init_db
from crypto_predictor.validation.validator import validate_pending_predictions
from crypto_predictor.validation.rolling_metrics import update_rolling_metrics

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done",
)
def test_plan_d_validator_processes_btc_prediction(tmp_path: Path):
    """Validator runs on real BTC data. Status will be 'correct'/'incorrect' if
    data covers the validation window, or 'expired' if data is too stale.
    Either outcome demonstrates the wire-up works."""
    db = tmp_path / "predictions.db"
    init_db(db)
    # Insert a pending prediction with created_at well within the ingested data window
    # (>30 days ago to ensure 1h bars cover the full 24h horizon)
    asof = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    conn = sqlite3.connect(db)
    conn.execute("""
        INSERT INTO predictions (id, symbol, horizon_hours, prediction,
            p_direction, target_value, composite_score, confidence_flag,
            regime, formula_version, calibration_version, status, created_at)
        VALUES ('itest_btc', 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02, 0.013,
                'NORMAL', 'BULL', 'v1.5', 'v1.5.4', 'pending', ?)
    """, (asof.isoformat(),))
    conn.commit()
    conn.close()

    n = validate_pending_predictions(
        predictions_db=db, history_root=HISTORY_ROOT,
        now=datetime.now(timezone.utc),
    )
    assert n == 1
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT status FROM predictions WHERE id='itest_btc'"
    ).fetchone()
    conn.close()
    # Status should be a closed value (not 'pending') — either correct/incorrect (real data) or expired
    assert row[0] in ("correct", "incorrect", "expired")


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done",
)
def test_plan_d_rolling_metrics_after_validator(tmp_path: Path):
    """Insert closed predictions directly, run update_rolling_metrics, verify rows."""
    db = tmp_path / "predictions.db"
    init_db(db)
    now = datetime.now(timezone.utc)
    conn = sqlite3.connect(db)
    for i in range(7):
        validated_at = (now - timedelta(hours=1 + i)).isoformat()
        conn.execute("""
            INSERT INTO predictions (id, symbol, horizon_hours, prediction,
                p_direction, target_value, composite_score, confidence_flag,
                regime, formula_version, calibration_version, status,
                actual_outcome, validated_at, created_at)
            VALUES (?, 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02, 0.013,
                    'NORMAL', 'BULL', 'v1.5', 'v1.5.4',
                    ?, ?, ?, ?)
        """, (f"itest{i}",
              "correct" if i < 5 else "incorrect",
              0.025 if i < 5 else -0.01,
              validated_at,
              (now - timedelta(hours=25 + i)).isoformat()))
    conn.commit()
    conn.close()

    n_metrics = update_rolling_metrics(
        predictions_db=db, now=now,
    )
    assert n_metrics > 0
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT hit_rate, n_predictions FROM metrics_rolling "
        "WHERE window='7d' AND regime='BULL' AND direction='long'"
    ).fetchone()
    conn.close()
    assert row is not None
    # 5/7 = 0.714 hit rate
    assert abs(row[0] - 5/7) < 0.001
    assert row[1] == 7
