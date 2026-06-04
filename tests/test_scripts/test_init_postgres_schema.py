"""Unit tests for scripts/init_postgres_schema.py and the canonical
migrations/001_initial_schema.sql.

The live ``apply_migration`` path is exercised against a real Postgres during
cutover (Step 19 of the runbook), so these tests focus on:

  * the PG-free helpers (``list_migrations``, dry-run summary),
  * structural invariants of the schema SQL (all 17 tables present, every
    CREATE TABLE / CREATE INDEX is idempotent).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.init_postgres_schema import list_migrations, run_init


# ---------------------------------------------------------------------------
# list_migrations
# ---------------------------------------------------------------------------

def test_list_migrations_returns_sql_files_in_lexical_order(tmp_path: Path) -> None:
    (tmp_path / "002_later.sql").write_text("-- later", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("-- first", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored", encoding="utf-8")

    out = list_migrations(tmp_path)

    versions = [v for v, _, _ in out]
    assert versions == ["001_first", "002_later"]


def test_list_migrations_computes_sha256(tmp_path: Path) -> None:
    (tmp_path / "001_x.sql").write_text("hello", encoding="utf-8")

    out = list_migrations(tmp_path)

    assert len(out) == 1
    version, sha, path = out[0]
    assert version == "001_x"
    assert path.name == "001_x.sql"
    assert sha == hashlib.sha256(b"hello").hexdigest()


def test_list_migrations_ignores_non_sql_files(tmp_path: Path) -> None:
    (tmp_path / "001_real.sql").write_text("-- real", encoding="utf-8")
    (tmp_path / "999_notes.txt").write_text("not a migration", encoding="utf-8")
    (tmp_path / "README.md").write_text("# nope", encoding="utf-8")

    out = list_migrations(tmp_path)

    assert [v for v, _, _ in out] == ["001_real"]


def test_list_migrations_raises_when_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list_migrations(tmp_path / "does_not_exist")


# ---------------------------------------------------------------------------
# run_init dry-run path (no PG required)
# ---------------------------------------------------------------------------

def test_run_init_dry_run_lists_every_migration(tmp_path: Path) -> None:
    (tmp_path / "001_a.sql").write_text("-- a", encoding="utf-8")
    (tmp_path / "002_b.sql").write_text("-- b", encoding="utf-8")

    summary = run_init(pg_url="", migrations_dir=tmp_path, dry_run=True)

    assert summary == {"applied": ["001_a", "002_b"], "skipped": []}


def test_run_init_requires_pg_url_when_not_dry_run(tmp_path: Path) -> None:
    (tmp_path / "001_a.sql").write_text("-- a", encoding="utf-8")

    with pytest.raises(ValueError):
        run_init(pg_url="", migrations_dir=tmp_path, dry_run=False)


# ---------------------------------------------------------------------------
# Canonical schema file: structural invariants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _REPO_ROOT / "migrations" / "001_initial_schema.sql"


def test_real_schema_file_parses_as_text() -> None:
    """Smoke: the canonical 001_initial_schema.sql exists and is readable."""
    assert _SCHEMA_PATH.exists(), f"missing schema file: {_SCHEMA_PATH}"
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE" in content

    # Spot-check that the 17 tables (incl. the tracker) are present:
    expected_tables = [
        "_migrations",
        # predictions.db migrated
        "predictions", "predictions_features", "calibration_maps",
        "regime_log", "metrics_rolling", "patterns", "runs",
        # sentiment_cache.db migrated
        "sentiment_cache",
        # global_cache.db migrated
        "global_cache", "coin_btc_corr",
        # new mart tables
        "prices_1m", "whale_txs", "news_feed", "manual_annotations",
        "portfolio_holdings", "exchange_balances", "claude_chat_log",
    ]
    for t in expected_tables:
        assert f"CREATE TABLE IF NOT EXISTS {t}" in content, f"missing: {t}"


def test_schema_idempotent_markers() -> None:
    """Every CREATE TABLE / CREATE INDEX must include IF NOT EXISTS so the
    bootstrap is safe to re-run on a populated DB."""
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    for line in content.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        # Skip comments / blank lines.
        if not stripped or stripped.startswith("--"):
            continue
        if upper.startswith("CREATE TABLE ") and "IF NOT EXISTS" not in upper:
            raise AssertionError(f"non-idempotent CREATE TABLE: {line!r}")
        if upper.startswith("CREATE INDEX ") and "IF NOT EXISTS" not in upper:
            raise AssertionError(f"non-idempotent CREATE INDEX: {line!r}")


def test_schema_quotes_window_reserved_word() -> None:
    """`window` is a PG reserved keyword and must be double-quoted everywhere
    it appears as an identifier inside metrics_rolling."""
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    # Must appear quoted (column declaration + PK use).
    assert '"window"' in content
    # Must NOT appear as a bare column name inside the metrics_rolling DDL.
    # (Cheap structural check: scan the table block.)
    start = content.find("CREATE TABLE IF NOT EXISTS metrics_rolling")
    assert start >= 0
    end = content.find(");", start)
    block = content[start:end]
    for line in block.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("window "):
            raise AssertionError(
                f"metrics_rolling has unquoted `window` column: {line!r}"
            )


def test_schema_has_expected_indexes() -> None:
    """Spot-check a handful of indexes called out in the spec/plan."""
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    expected_indexes = [
        # migrated indexes
        "idx_pred_symbol", "idx_pred_status", "idx_pred_created",
        "idx_pred_regime", "idx_predictions_mode",
        "idx_predictions_completeness",
        # new-table indexes from the spec
        "idx_prices_1m_ts", "idx_whale_txs_ts",
        "idx_news_feed_ts", "idx_news_feed_category", "idx_news_feed_symbols",
        "idx_manual_annotations_symbol", "idx_manual_annotations_open",
        "idx_portfolio_asset", "idx_exchange_balances_ts",
        "idx_claude_chat_log_session",
    ]
    for idx in expected_indexes:
        assert idx in content, f"missing index: {idx}"


def test_schema_has_check_constraints() -> None:
    """Spec §3 implies CHECK constraints on enum-like columns."""
    content = _SCHEMA_PATH.read_text(encoding="utf-8").upper()
    # mode, feature_completeness, status, confidence_flag, regime, prediction
    assert "MODE IN ('LIVE', 'SHADOW', 'BACKTEST')" in content
    assert "FEATURE_COMPLETENESS IN ('FULL', 'DEGRADED')" in content
    assert "STATUS IN ('PENDING', 'CORRECT', 'INCORRECT'" in content
    assert "CONFIDENCE_FLAG IN ('NORMAL', 'HIGH_CONV', 'WILD_CARD')" in content
    assert "REGIME IN ('BULL', 'CHOP', 'BEAR')" in content
    assert "PREDICTION IN ('UP', 'DOWN')" in content


def test_schema_has_foreign_keys() -> None:
    """Spec §3 declares explicit FKs from predictions_features and
    manual_annotations onto predictions(id)."""
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    # predictions_features.prediction_id -> predictions(id)
    assert "REFERENCES predictions(id)" in content
    # manual_annotations.prediction_id -> predictions(id) ON DELETE SET NULL
    assert "ON DELETE SET NULL" in content


def test_schema_has_partial_index_on_open_annotations() -> None:
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    assert "WHERE closed_at IS NULL" in content


def test_schema_has_gin_index_on_symbols_mentioned() -> None:
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    assert "USING GIN (symbols_mentioned)" in content


def test_schema_has_migrations_tracker_first() -> None:
    """The _migrations tracker must be declared before any other table so the
    bootstrap can record its own progress on a fresh DB."""
    content = _SCHEMA_PATH.read_text(encoding="utf-8")
    pos_tracker = content.find("CREATE TABLE IF NOT EXISTS _migrations")
    pos_predictions = content.find("CREATE TABLE IF NOT EXISTS predictions ")
    assert 0 <= pos_tracker < pos_predictions
