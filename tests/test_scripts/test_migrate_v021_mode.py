import sqlite3
from pathlib import Path

import pytest

from crypto_predictor.storage.predictions_db import init_db
from scripts.migrate_v021_mode import migrate_to_v021


def test_migration_adds_three_columns(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)  # pre-v0.2.1 schema
    migrate_to_v021(db)
    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}
    conn.close()
    assert "mode" in cols
    assert "feature_completeness" in cols
    assert "missing_features" in cols


def test_migration_backfills_existing_rows_as_live_full(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO predictions (id, symbol, horizon_hours, prediction, "
        "p_direction, target_value, composite_score, confidence_flag, regime, "
        "formula_version, calibration_version, status, created_at) "
        "VALUES ('x', 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02, 0.013, 'NORMAL', "
        "'BULL', 'v1.5', 'v1.5.4', 'pending', '2026-06-01T11:30:00+00:00')"
    )
    conn.commit()
    conn.close()
    migrate_to_v021(db)
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT mode, feature_completeness, missing_features "
        "FROM predictions WHERE id='x'"
    ).fetchone()
    conn.close()
    assert row == ("live", "full", None)


def test_migration_backfills_2026_06_02_cohort_as_degraded(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO predictions (id, symbol, horizon_hours, prediction, "
        "p_direction, target_value, composite_score, confidence_flag, regime, "
        "formula_version, calibration_version, status, created_at) "
        "VALUES ('cohort', 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02, 0.013, "
        "'NORMAL', 'BULL', 'v1.5', 'v1.5.4', 'correct', "
        "'2026-06-02T11:30:00.515+00:00')"
    )
    conn.execute(
        "INSERT INTO predictions (id, symbol, horizon_hours, prediction, "
        "p_direction, target_value, composite_score, confidence_flag, regime, "
        "formula_version, calibration_version, status, created_at) "
        "VALUES ('dryrun_btc_up', 'BTC/USDT:USDT', 24, 'up', 0.65, 0.02, 0.013, "
        "'NORMAL', 'BULL', 'v1.5', 'v1.5.4', 'expired', "
        "'2026-06-02T11:30:00+00:00')"
    )
    conn.commit()
    conn.close()
    migrate_to_v021(db)
    conn = sqlite3.connect(str(db))
    cohort = conn.execute(
        "SELECT feature_completeness, missing_features FROM predictions "
        "WHERE id='cohort'"
    ).fetchone()
    dryrun = conn.execute(
        "SELECT feature_completeness, missing_features FROM predictions "
        "WHERE id='dryrun_btc_up'"
    ).fetchone()
    conn.close()
    assert cohort == ("degraded", "sentiment,global")
    assert dryrun == ("full", None)  # dryrun excluded from backfill


def test_migration_is_idempotent(tmp_path: Path):
    db = tmp_path / "predictions.db"
    init_db(db)
    migrate_to_v021(db)
    migrate_to_v021(db)  # second call should not raise
    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}
    conn.close()
    assert "mode" in cols
