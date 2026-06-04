"""Unit tests for scripts/migrate_sqlite_to_postgres.py.

These tests cover:
  - Type uplift helper (spec §3 type uplift table)
  - Per-table dry-run row counts (parity logic, no PG required)
  - CLI dry-run smoke against synthetic source DBs

End-to-end PG insert behavior is exercised by Step 28 of the cutover runbook,
not here; psycopg is a lazy import so dry-run mode does NOT require it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.migrate_sqlite_to_postgres import (
    migrate_coin_btc_corr_table,
    migrate_global_cache_table,
    migrate_predictions_features_table,
    migrate_predictions_table,
    migrate_sentiment_cache_table,
    pg_type_for_sqlite_value,
    run_migration,
)


# ---------------------------------------------------------------------------
# Type uplift helper
# ---------------------------------------------------------------------------

def test_pg_type_uplift_iso_string_to_timestamptz():
    assert pg_type_for_sqlite_value(
        "created_at", "2026-06-04T06:00:00+00:00"
    ) == "TIMESTAMPTZ"
    assert pg_type_for_sqlite_value(
        "validated_at", "2026-06-04T06:30:00+00:00"
    ) == "TIMESTAMPTZ"
    assert pg_type_for_sqlite_value(
        "timestamp", "2026-06-04T06:30:00+00:00"
    ) == "TIMESTAMPTZ"


def test_pg_type_uplift_probability_columns():
    assert pg_type_for_sqlite_value("p_direction", 0.65) == "NUMERIC(10, 8)"
    assert pg_type_for_sqlite_value("composite_score", 0.013) == "NUMERIC(10, 8)"
    assert pg_type_for_sqlite_value("brier", 0.21) == "NUMERIC(10, 8)"


def test_pg_type_uplift_enum_columns():
    assert pg_type_for_sqlite_value("status", "correct") == "VARCHAR(20)"
    assert pg_type_for_sqlite_value("mode", "shadow") == "VARCHAR(20)"
    assert pg_type_for_sqlite_value("regime", "CHOP") == "VARCHAR(20)"
    assert pg_type_for_sqlite_value("confidence_flag", "NORMAL") == "VARCHAR(20)"
    assert pg_type_for_sqlite_value(
        "feature_completeness", "degraded"
    ) == "VARCHAR(20)"


def test_pg_type_uplift_price_like_columns():
    assert pg_type_for_sqlite_value("target_value", 0.02) == "NUMERIC(20, 8)"
    assert pg_type_for_sqlite_value("actual_outcome", 0.018) == "NUMERIC(20, 8)"
    assert pg_type_for_sqlite_value("raw_value", 1.5) == "NUMERIC(20, 8)"


def test_pg_type_uplift_integer_counts():
    assert pg_type_for_sqlite_value("horizon_hours", 24) == "INTEGER"
    assert pg_type_for_sqlite_value("occurrences", 5) == "INTEGER"
    assert pg_type_for_sqlite_value("n_predictions", 340) == "INTEGER"
    assert pg_type_for_sqlite_value("wins", 12) == "INTEGER"


def test_pg_type_uplift_unknown_column_falls_back_to_text():
    """Free-text fallback is the spec's universal default (§3)."""
    assert pg_type_for_sqlite_value("future_column_2030", "anything") == "TEXT"
    assert pg_type_for_sqlite_value("evaluation", "free text blob") == "TEXT"


# ---------------------------------------------------------------------------
# Per-table dry-run row counts
# ---------------------------------------------------------------------------

def _make_predictions_db(path: Path, n_rows: int = 2) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "CREATE TABLE predictions (id TEXT PRIMARY KEY, "
            "p_direction REAL, status TEXT)"
        )
        for i in range(n_rows):
            conn.execute(
                "INSERT INTO predictions VALUES (?, ?, ?)",
                (f"row_{i}", 0.5 + 0.01 * i, "pending"),
            )
        conn.commit()
    finally:
        conn.close()


def test_migrate_predictions_dry_run_returns_row_count(tmp_path: Path):
    src = tmp_path / "src.db"
    _make_predictions_db(src, n_rows=2)
    assert migrate_predictions_table(src, dry_run=True) == 2


def test_migrate_predictions_empty_table_returns_zero(tmp_path: Path):
    src = tmp_path / "src.db"
    conn = sqlite3.connect(str(src))
    conn.execute(
        "CREATE TABLE predictions (id TEXT PRIMARY KEY, p_direction REAL)"
    )
    conn.commit()
    conn.close()
    assert migrate_predictions_table(src, dry_run=True) == 0


def test_migrate_predictions_features_dry_run_returns_row_count(tmp_path: Path):
    src = tmp_path / "src.db"
    conn = sqlite3.connect(str(src))
    conn.execute(
        "CREATE TABLE predictions_features ("
        "prediction_id TEXT NOT NULL, feature_name TEXT NOT NULL, "
        "raw_value REAL, z_value REAL, "
        "PRIMARY KEY (prediction_id, feature_name))"
    )
    conn.executemany(
        "INSERT INTO predictions_features VALUES (?, ?, ?, ?)",
        [
            ("a", "rsi", 55.0, 0.1),
            ("a", "macd", 0.002, -0.3),
            ("b", "rsi", 60.0, 0.4),
        ],
    )
    conn.commit()
    conn.close()
    assert migrate_predictions_features_table(src, dry_run=True) == 3


def test_migrate_sentiment_cache_dry_run(tmp_path: Path):
    src = tmp_path / "sentiment.db"
    conn = sqlite3.connect(str(src))
    conn.execute(
        "CREATE TABLE sentiment_cache ("
        "symbol TEXT, timestamp TEXT, "
        "news_sent_24h REAL, social_sent_24h REAL, "
        "sent_velocity REAL, news_volume_z REAL, "
        "PRIMARY KEY (symbol, timestamp))"
    )
    conn.executemany(
        "INSERT INTO sentiment_cache VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("BTC/USDT:USDT", "2026-06-04T00:00:00+00:00", 0.1, 0.2, 0.0, 0.5),
            ("ETH/USDT:USDT", "2026-06-04T00:00:00+00:00", -0.1, 0.0, 0.1, 0.3),
        ],
    )
    conn.commit()
    conn.close()
    assert migrate_sentiment_cache_table(src, dry_run=True) == 2


def test_migrate_global_cache_dry_run(tmp_path: Path):
    src = tmp_path / "global.db"
    conn = sqlite3.connect(str(src))
    conn.execute(
        "CREATE TABLE global_cache ("
        "timestamp TEXT PRIMARY KEY, "
        "btc_dom_trend_7d REAL, eth_btc_trend_7d REAL, total_mcap_z REAL, "
        "sector_btc REAL, sector_eth REAL, sector_defi REAL, sector_l1 REAL)"
    )
    conn.execute(
        "INSERT INTO global_cache VALUES "
        "('2026-06-04T00:00:00+00:00', 0.01, -0.02, 0.5, 0.1, 0.0, -0.1, 0.2)"
    )
    conn.commit()
    conn.close()
    assert migrate_global_cache_table(src, dry_run=True) == 1


def test_migrate_table_missing_returns_zero(tmp_path: Path):
    """If a source DB exists but the table is missing (fresh dev DB), the
    migrator returns 0 instead of crashing."""
    src = tmp_path / "empty.db"
    conn = sqlite3.connect(str(src))
    # create the DB file but no tables
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()
    assert migrate_coin_btc_corr_table(src, dry_run=True) == 0


# ---------------------------------------------------------------------------
# Full migration parity report (dry-run)
# ---------------------------------------------------------------------------

def test_run_migration_dry_run_returns_summary(tmp_path: Path):
    pred = tmp_path / "predictions.db"
    sent = tmp_path / "sentiment_cache.db"
    glob = tmp_path / "global_cache.db"

    # predictions.db with two tables populated
    conn = sqlite3.connect(str(pred))
    conn.execute(
        "CREATE TABLE predictions (id TEXT PRIMARY KEY, p_direction REAL)"
    )
    conn.execute("INSERT INTO predictions VALUES ('a', 0.6), ('b', 0.7)")
    conn.execute(
        "CREATE TABLE predictions_features ("
        "prediction_id TEXT, feature_name TEXT, raw_value REAL, z_value REAL, "
        "PRIMARY KEY (prediction_id, feature_name))"
    )
    conn.execute("INSERT INTO predictions_features VALUES ('a', 'rsi', 50, 0)")
    conn.commit()
    conn.close()

    # sentiment_cache.db
    conn = sqlite3.connect(str(sent))
    conn.execute(
        "CREATE TABLE sentiment_cache ("
        "symbol TEXT, timestamp TEXT, news_sent_24h REAL, social_sent_24h REAL, "
        "sent_velocity REAL, news_volume_z REAL, "
        "PRIMARY KEY (symbol, timestamp))"
    )
    conn.execute(
        "INSERT INTO sentiment_cache VALUES "
        "('BTC/USDT:USDT', '2026-06-04T00:00:00+00:00', 0.1, 0.0, 0.0, 0.0)"
    )
    conn.commit()
    conn.close()

    # global_cache.db
    conn = sqlite3.connect(str(glob))
    conn.execute(
        "CREATE TABLE global_cache ("
        "timestamp TEXT PRIMARY KEY, btc_dom_trend_7d REAL, eth_btc_trend_7d REAL, "
        "total_mcap_z REAL, sector_btc REAL, sector_eth REAL, "
        "sector_defi REAL, sector_l1 REAL)"
    )
    conn.execute(
        "INSERT INTO global_cache VALUES "
        "('2026-06-04T00:00:00+00:00', 0.01, 0.0, 0.5, 0.1, 0.0, 0.0, 0.2)"
    )
    conn.commit()
    conn.close()

    summary = run_migration(
        predictions_db=pred, sentiment_db=sent, global_db=glob,
        pg_conn=None, dry_run=True,
    )
    # All 10 expected tables in the report
    expected_tables = {
        "predictions", "predictions_features", "calibration_maps", "regime_log",
        "metrics_rolling", "patterns", "runs",
        "sentiment_cache",
        "global_cache", "coin_btc_corr",
    }
    assert set(summary.keys()) == expected_tables
    # Populated counts
    assert summary["predictions"] == 2
    assert summary["predictions_features"] == 1
    assert summary["sentiment_cache"] == 1
    assert summary["global_cache"] == 1
    # Missing tables -> 0
    assert summary["calibration_maps"] == 0
    assert summary["regime_log"] == 0
    assert summary["coin_btc_corr"] == 0


def test_cli_dry_run_with_missing_source_db_fails(tmp_path: Path):
    """CLI should bail with non-zero exit when a source DB path doesn't exist."""
    from scripts.migrate_sqlite_to_postgres import main

    rc = main([
        "--predictions", str(tmp_path / "does_not_exist.db"),
        "--sentiment", str(tmp_path / "also_missing.db"),
        "--global", str(tmp_path / "still_missing.db"),
        "--pg", "",
        "--dry-run",
    ])
    assert rc == 1


def test_cli_requires_pg_url_when_not_dry_run(tmp_path: Path, monkeypatch):
    """An empty --pg without --dry-run is a config error."""
    from scripts.migrate_sqlite_to_postgres import main

    # Create three empty SQLite files so the source-existence check passes.
    for name in ("predictions.db", "sentiment.db", "global.db"):
        p = tmp_path / name
        sqlite3.connect(str(p)).close()

    rc = main([
        "--predictions", str(tmp_path / "predictions.db"),
        "--sentiment", str(tmp_path / "sentiment.db"),
        "--global", str(tmp_path / "global.db"),
        "--pg", "",  # empty, and no --dry-run
    ])
    assert rc == 2
