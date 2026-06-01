from pathlib import Path

import pytest

from crypto_predictor.storage.features_db import init_db, write_snapshot, read_snapshot


def test_init_creates_feature_snapshot_table(tmp_path: Path):
    db = tmp_path / "features.db"
    init_db(db)
    import sqlite3
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "feature_snapshot" in tables
    conn.close()


def test_write_and_read_roundtrip(tmp_path: Path):
    db = tmp_path / "features.db"
    init_db(db)
    write_snapshot(db, "BTCUSDT", "2026-06-02T06:00:00Z",
                   {"ret_1h_z": 0.5, "funding_z": -1.2})
    out = read_snapshot(db, "BTCUSDT", "2026-06-02T06:00:00Z")
    assert out == {"ret_1h_z": 0.5, "funding_z": -1.2}


def test_read_returns_empty_when_missing(tmp_path: Path):
    db = tmp_path / "features.db"
    init_db(db)
    assert read_snapshot(db, "BTCUSDT", "2026-06-02T06:00:00Z") == {}
