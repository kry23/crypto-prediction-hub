"""Port the three SQLite databases (predictions, sentiment_cache, global_cache)
into a single PostgreSQL database during the v1.0 cutover.

Idempotent: re-running with the same source and target is safe; existing rows
are skipped via ON CONFLICT DO NOTHING.

Run during cutover (Step 20 of the cutover runbook):
    python scripts/migrate_sqlite_to_postgres.py \\
        --predictions ./predictions.db \\
        --sentiment ./data/sentiment_cache.db \\
        --global ./data/global_cache.db \\
        --pg postgresql://crypto_predictor:PASSWORD@127.0.0.1:5432/crypto_predictor

Dry-run mode (no PG required) — prints a parity report of source row counts:
    python scripts/migrate_sqlite_to_postgres.py \\
        --predictions ./predictions.db \\
        --sentiment ./data/sentiment_cache.db \\
        --global ./data/global_cache.db \\
        --pg "" \\
        --dry-run

Type uplift rules (spec §3):
    ISO 8601 timestamp TEXT -> TIMESTAMPTZ
    Price-like REAL         -> NUMERIC(20, 8)
    Probability REAL        -> NUMERIC(10, 8)
    Enum-like TEXT          -> VARCHAR(20)
    Integer counts          -> INTEGER or BIGINT
    Free-text TEXT          -> TEXT
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

import structlog

# Project root onto sys.path so this script works when invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.logging_config import configure_logging  # noqa: E402

log = structlog.get_logger(__name__)

# Per-column type uplift map (column_name -> PG type). Single source of truth
# for the cutover; mirrored from spec §3 type uplift rules table.
TYPE_UPLIFT: dict[str, str] = {
    # ISO 8601 timestamps -> TIMESTAMPTZ
    "created_at": "TIMESTAMPTZ",
    "validated_at": "TIMESTAMPTZ",
    "first_seen": "TIMESTAMPTZ",
    "last_seen": "TIMESTAMPTZ",
    "started_at": "TIMESTAMPTZ",
    "completed_at": "TIMESTAMPTZ",
    "updated_at": "TIMESTAMPTZ",
    "timestamp": "TIMESTAMPTZ",
    "asof": "TIMESTAMPTZ",
    "date": "TIMESTAMPTZ",
    # Probabilities -> NUMERIC(10, 8)
    "p_direction": "NUMERIC(10, 8)",
    "composite_score": "NUMERIC(10, 8)",
    "brier": "NUMERIC(10, 8)",
    "mae": "NUMERIC(10, 8)",
    "hit_rate": "NUMERIC(10, 8)",
    "win_rate": "NUMERIC(10, 8)",
    # Price-like / signed fractional values -> NUMERIC(20, 8)
    "target_value": "NUMERIC(20, 8)",
    "actual_outcome": "NUMERIC(20, 8)",
    "error_margin": "NUMERIC(20, 8)",
    "topk_alpha": "NUMERIC(20, 8)",
    "topk_alpha_btc": "NUMERIC(20, 8)",
    "avg_pnl_percent": "NUMERIC(20, 8)",
    "raw_value": "NUMERIC(20, 8)",
    "z_value": "NUMERIC(20, 8)",
    # Sentiment / global context scalars (signed, bounded) -> NUMERIC(10, 6)
    "news_sent_24h": "NUMERIC(10, 6)",
    "social_sent_24h": "NUMERIC(10, 6)",
    "sent_velocity": "NUMERIC(10, 6)",
    "news_volume_z": "NUMERIC(10, 6)",
    "btc_dom_trend_7d": "NUMERIC(10, 6)",
    "eth_btc_trend_7d": "NUMERIC(10, 6)",
    "total_mcap_z": "NUMERIC(10, 6)",
    "sector_btc": "NUMERIC(10, 6)",
    "sector_eth": "NUMERIC(10, 6)",
    "sector_defi": "NUMERIC(10, 6)",
    "sector_l1": "NUMERIC(10, 6)",
    "btc_30d_return": "NUMERIC(10, 6)",
    "btc_funding_avg": "NUMERIC(10, 6)",
    "corr_30d": "NUMERIC(10, 6)",
    "global_mcap_trend": "NUMERIC(10, 6)",
    # Enum-like TEXT -> VARCHAR(20) (CHECK constraints applied in the schema bootstrap)
    "status": "VARCHAR(20)",
    "mode": "VARCHAR(20)",
    "regime": "VARCHAR(20)",
    "confidence_flag": "VARCHAR(20)",
    "feature_completeness": "VARCHAR(20)",
    "recommendation": "VARCHAR(20)",
    "direction": "VARCHAR(10)",
    "window": "VARCHAR(10)",
    "prediction": "VARCHAR(10)",
    "global_mcap_trend_label": "VARCHAR(20)",
    "job": "VARCHAR(40)",
    # Integer counts -> INTEGER
    "horizon_hours": "INTEGER",
    "occurrences": "INTEGER",
    "wins": "INTEGER",
    "losses": "INTEGER",
    "n_predictions": "INTEGER",
    "n_correct": "INTEGER",
    "n_errors": "INTEGER",
}


def pg_type_for_sqlite_value(column_name: str, sample_value: object) -> str:
    """Return the target PG type for a SQLite column based on the spec
    type-uplift table. Falls back to TEXT for unknown columns (safe default —
    free-text is the universal fallback per spec §3)."""
    if column_name in TYPE_UPLIFT:
        return TYPE_UPLIFT[column_name]
    return "TEXT"


# ---------------------------------------------------------------------------
# Per-table copy helpers
# ---------------------------------------------------------------------------
# Each helper:
#   1. Reads all rows from the SQLite source table.
#   2. If dry_run or pg_conn is None, returns the row count without inserting.
#   3. Otherwise INSERTs into PG using ON CONFLICT (<pk>) DO NOTHING for
#      idempotency, and returns the source row count.
#
# We return the SOURCE row count (not the rowcount actually inserted) so the
# parity report reflects what we read from SQLite; the runbook smoke step
# compares this against `SELECT COUNT(*) FROM <table>` in PG.

# (table_name, primary_key_columns) — used for ON CONFLICT clause.
_TABLE_PKS: dict[str, tuple[str, ...]] = {
    "predictions": ("id",),
    "predictions_features": ("prediction_id", "feature_name"),
    "calibration_maps": ("version", "regime"),
    "regime_log": ("date",),
    "metrics_rolling": ("window", "regime", "direction"),
    "patterns": ("name",),
    "runs": ("run_id",),
    "sentiment_cache": ("symbol", "timestamp"),
    "global_cache": ("timestamp",),
    "coin_btc_corr": ("symbol", "timestamp"),
}

# Reserved SQL keyword columns that must be double-quoted on the PG side.
_PG_QUOTED_COLUMNS: frozenset[str] = frozenset({"window"})


def _quote_col(col: str) -> str:
    if col in _PG_QUOTED_COLUMNS:
        return f'"{col}"'
    return col


def _read_table(src_db: Path, table: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Return (column_names, rows) for `table` in `src_db`. Empty lists if the
    table is missing — callers treat that as zero rows (e.g. fresh local DB)."""
    conn = sqlite3.connect(str(src_db))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table,),
        )
        if cur.fetchone() is None:
            return [], []
        cur = conn.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return cols, rows
    finally:
        conn.close()


def _insert_rows(pg_conn, table: str, columns: list[str],
                 rows: list[tuple[Any, ...]]) -> int:
    """Batch INSERT rows into PG with ON CONFLICT (<pk>) DO NOTHING. Returns
    the number of rows the cursor reports as written (best-effort)."""
    if not rows:
        return 0
    pk = _TABLE_PKS.get(table)
    if pk is None:
        raise ValueError(f"No PK registered for table {table!r}")
    col_list = ", ".join(_quote_col(c) for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    pk_list = ", ".join(_quote_col(c) for c in pk)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({pk_list}) DO NOTHING"
    )
    with pg_conn.cursor() as cur:
        cur.executemany(sql, rows)
        inserted = cur.rowcount if cur.rowcount is not None else 0
    pg_conn.commit()
    return inserted


def _copy_table(src_db: Path, table: str, *, dry_run: bool, pg_conn) -> int:
    """Generic copy: read SQLite -> INSERT into PG. Returns source row count."""
    cols, rows = _read_table(src_db, table)
    if dry_run or pg_conn is None:
        if not cols:
            log.info("migrate_table_skipped_missing", table=table, src=str(src_db))
        else:
            log.info("migrate_dry_run", table=table, rows=len(rows))
        return len(rows)
    if not cols:
        log.info("migrate_table_skipped_missing", table=table, src=str(src_db))
        return 0
    inserted = _insert_rows(pg_conn, table, cols, rows)
    log.info("migrate_table_done", table=table,
             source_rows=len(rows), inserted_rows=inserted)
    return len(rows)


# Public per-table wrappers -- thin shims so the runbook & tests can call them
# by name and so the parity report uses stable labels.

def migrate_predictions_table(src_db: Path, *, dry_run: bool = False,
                              pg_conn: Any = None) -> int:
    """Read predictions table from SQLite, INSERT into PG (or count for dry_run).
    Returns the number of rows processed."""
    return _copy_table(src_db, "predictions", dry_run=dry_run, pg_conn=pg_conn)


def migrate_predictions_features_table(src_db: Path, *, dry_run: bool = False,
                                       pg_conn: Any = None) -> int:
    return _copy_table(src_db, "predictions_features",
                       dry_run=dry_run, pg_conn=pg_conn)


def migrate_calibration_maps_table(src_db: Path, *, dry_run: bool = False,
                                   pg_conn: Any = None) -> int:
    return _copy_table(src_db, "calibration_maps",
                       dry_run=dry_run, pg_conn=pg_conn)


def migrate_regime_log_table(src_db: Path, *, dry_run: bool = False,
                             pg_conn: Any = None) -> int:
    return _copy_table(src_db, "regime_log", dry_run=dry_run, pg_conn=pg_conn)


def migrate_metrics_rolling_table(src_db: Path, *, dry_run: bool = False,
                                  pg_conn: Any = None) -> int:
    return _copy_table(src_db, "metrics_rolling",
                       dry_run=dry_run, pg_conn=pg_conn)


def migrate_patterns_table(src_db: Path, *, dry_run: bool = False,
                           pg_conn: Any = None) -> int:
    return _copy_table(src_db, "patterns", dry_run=dry_run, pg_conn=pg_conn)


def migrate_runs_table(src_db: Path, *, dry_run: bool = False,
                       pg_conn: Any = None) -> int:
    return _copy_table(src_db, "runs", dry_run=dry_run, pg_conn=pg_conn)


def migrate_sentiment_cache_table(src_db: Path, *, dry_run: bool = False,
                                  pg_conn: Any = None) -> int:
    return _copy_table(src_db, "sentiment_cache",
                       dry_run=dry_run, pg_conn=pg_conn)


def migrate_global_cache_table(src_db: Path, *, dry_run: bool = False,
                               pg_conn: Any = None) -> int:
    return _copy_table(src_db, "global_cache",
                       dry_run=dry_run, pg_conn=pg_conn)


def migrate_coin_btc_corr_table(src_db: Path, *, dry_run: bool = False,
                                pg_conn: Any = None) -> int:
    return _copy_table(src_db, "coin_btc_corr",
                       dry_run=dry_run, pg_conn=pg_conn)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _open_pg(url: str):
    """Lazy import psycopg so dry-run mode doesn't require it installed."""
    import psycopg  # noqa: PLC0415 — intentional lazy import

    return psycopg.connect(url)


def run_migration(*, predictions_db: Path, sentiment_db: Path,
                  global_db: Path, pg_conn: Any,
                  dry_run: bool = False) -> dict[str, int]:
    """Run every per-table migrator in the order PG FKs expect. Returns a
    {table_name: source_row_count} parity report."""
    summary: dict[str, int] = {}
    # predictions.db tables — predictions first (FK target for *_features)
    summary["predictions"] = migrate_predictions_table(
        predictions_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    summary["predictions_features"] = migrate_predictions_features_table(
        predictions_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    summary["calibration_maps"] = migrate_calibration_maps_table(
        predictions_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    summary["regime_log"] = migrate_regime_log_table(
        predictions_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    summary["metrics_rolling"] = migrate_metrics_rolling_table(
        predictions_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    summary["patterns"] = migrate_patterns_table(
        predictions_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    summary["runs"] = migrate_runs_table(
        predictions_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    # sentiment_cache.db
    summary["sentiment_cache"] = migrate_sentiment_cache_table(
        sentiment_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    # global_cache.db
    summary["global_cache"] = migrate_global_cache_table(
        global_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    summary["coin_btc_corr"] = migrate_coin_btc_corr_table(
        global_db, dry_run=dry_run, pg_conn=pg_conn,
    )
    return summary


def _print_parity_report(summary: dict[str, int]) -> None:
    print("\nParity report:")
    total = 0
    for table, n in summary.items():
        print(f"  {table:24} {n:>8} rows")
        total += n
    print(f"  {'TOTAL':24} {total:>8} rows")


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Port the v0.x SQLite DBs into PostgreSQL for v1.0 cutover.",
    )
    parser.add_argument("--predictions", type=Path, required=True,
                        help="Path to predictions.db (SQLite)")
    parser.add_argument("--sentiment", type=Path, required=True,
                        help="Path to data/sentiment_cache.db (SQLite)")
    parser.add_argument("--global", type=Path, required=True, dest="global_db",
                        help="Path to data/global_cache.db (SQLite)")
    parser.add_argument("--pg", type=str, required=True,
                        help="DATABASE_URL for the target PG (empty string allowed "
                             "with --dry-run)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip PG connection; only report source row counts")
    args = parser.parse_args(argv)

    for path, label in (
        (args.predictions, "predictions"),
        (args.sentiment, "sentiment"),
        (args.global_db, "global"),
    ):
        if not path.exists():
            log.error("source_db_missing", label=label, path=str(path))
            return 1

    if args.dry_run:
        pg_conn = None
    else:
        if not args.pg:
            log.error("pg_url_required_when_not_dry_run")
            return 2
        try:
            pg_conn = _open_pg(args.pg)
        except Exception as e:  # pragma: no cover — exercised in cutover smoke
            log.error("pg_connect_failed", error=str(e))
            return 3

    try:
        summary = run_migration(
            predictions_db=args.predictions,
            sentiment_db=args.sentiment,
            global_db=args.global_db,
            pg_conn=pg_conn,
            dry_run=args.dry_run,
        )
    finally:
        if pg_conn is not None:
            pg_conn.close()

    log.info("migration_complete", dry_run=args.dry_run, **summary)
    _print_parity_report(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
