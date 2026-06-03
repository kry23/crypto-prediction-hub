import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from crypto_predictor.calibration.drift import DriftStatus
from crypto_predictor.scheduler.jobs import _job_recalibrate
from crypto_predictor.storage.predictions_db import init_db


def test_recalibrate_sends_telegram_when_drift(tmp_path, monkeypatch):
    db = tmp_path / "predictions.db"
    init_db(db)
    # Insert 10 closed predictions with high Brier (probs all 1.0, half wrong → Brier = 0.5)
    now = datetime(2026, 6, 3, tzinfo=timezone.utc)
    conn = sqlite3.connect(db)
    for i in range(10):
        validated_at = (now - timedelta(hours=1 + i)).isoformat()
        status = "correct" if i < 5 else "incorrect"
        conn.execute("""
            INSERT INTO predictions (id, symbol, horizon_hours, prediction,
                p_direction, target_value, composite_score, confidence_flag,
                regime, formula_version, calibration_version, status,
                validated_at, created_at)
            VALUES (?, 'BTC', 24, 'up', 1.0, 0.02, 0.013, 'NORMAL', 'BULL',
                    'v1.5', 'v1.5.4', ?, ?, ?)
        """, (f"p{i}", status, validated_at, validated_at))
    conn.commit()
    conn.close()

    # Point project_root to tmp_path
    monkeypatch.setenv("CRYPTO_PREDICTOR_ROOT", str(tmp_path))
    # Create secrets file with Telegram credentials
    secrets_path = tmp_path / "data" / "secrets.env"
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    secrets_path.write_text("TELEGRAM_BOT_TOKEN=FAKE\nTELEGRAM_CHAT_ID=123\n",
                             encoding="utf-8")

    with patch("crypto_predictor.scheduler.jobs.send_message") as mock_send:
        _job_recalibrate()
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert "DRIFT" in kwargs["text"]
