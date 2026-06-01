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
