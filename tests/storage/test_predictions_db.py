from pathlib import Path

import pytest

from crypto_predictor.storage.predictions_db import init_db, get_table_names


@pytest.fixture
def tmp_db(tmp_path):
    return tmp_path / "predictions.db"


def test_init_creates_all_tables(tmp_db: Path):
    init_db(tmp_db)
    tables = get_table_names(tmp_db)
    expected = {
        "predictions",
        "predictions_features",
        "calibration_maps",
        "regime_log",
        "metrics_rolling",
        "patterns",
        "runs",
    }
    assert expected.issubset(tables), f"missing tables: {expected - tables}"


def test_init_is_idempotent(tmp_db: Path):
    init_db(tmp_db)
    init_db(tmp_db)  # second call must not raise
    assert get_table_names(tmp_db)


def test_predictions_has_expected_columns(tmp_db: Path):
    import sqlite3
    init_db(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}
    expected = {
        "id", "symbol", "horizon_hours", "prediction", "p_direction",
        "target_value", "composite_score", "confidence_flag", "regime",
        "formula_version", "calibration_version", "status", "actual_outcome",
        "error_margin", "evaluation", "created_at", "validated_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"
    conn.close()


def test_init_db_includes_mode_and_completeness_columns(tmp_path: Path):
    import sqlite3
    db = tmp_path / "test.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}
    conn.close()
    assert "mode" in cols
    assert "feature_completeness" in cols
    assert "missing_features" in cols


def test_init_db_defaults_mode_to_live(tmp_path: Path):
    import sqlite3
    db = tmp_path / "test.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO predictions (id, symbol, horizon_hours, prediction, "
        "p_direction, target_value, composite_score, confidence_flag, "
        "regime, formula_version, calibration_version, status, created_at) "
        "VALUES ('x', 'BTC/USDT:USDT', 24, 'up', 0.6, 0.02, 0.012, 'NORMAL', "
        "'BULL', 'v1.5', 'v1.5.4', 'pending', '2026-06-04T06:00:00+00:00')"
    )
    row = conn.execute(
        "SELECT mode, feature_completeness, missing_features "
        "FROM predictions WHERE id='x'"
    ).fetchone()
    conn.close()
    assert row == ("live", "full", None)


def test_init_db_creates_indexes(tmp_path: Path):
    import sqlite3
    db = tmp_path / "test.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    indexes = {row[1] for row in conn.execute(
        "SELECT * FROM sqlite_master WHERE type='index'"
    )}
    conn.close()
    assert "idx_predictions_mode" in indexes
    assert "idx_predictions_completeness" in indexes
